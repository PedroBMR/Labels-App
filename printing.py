# printing.py
# -*- coding: utf-8 -*-
"""
Rotinas relacionadas à impressão das etiquetas.

Destaques:
- Alternância de templates por nome (ex.: "60x80", "100x30").
- Tamanho/direction a partir de templates.json.
- (Novo) Se o templates.json trouxer também posições dos campos (titulo/saida/...),
  essas posições serão usadas. Se não houver, usa o fallback embutido em LAYOUTS.
- Envio via spool do Windows (win32print). Salva logs úteis.

Estrutura esperada em assets/templates.json (exemplo):
{
  "60x80": {
    "largura_mm": 60, "altura_mm": 80, "gap_mm": 2, "direction": 1,
    "titulo": {"x":20,"y":20,"font":"5","xm":3,"ym":3},
    ...
    "logo_y": 360, "logo_largura": 280
  },
  "100x30": { ... }
}
Se as posições não estiverem no JSON, o código usa LAYOUTS abaixo.
"""

from __future__ import annotations

import copy
import importlib
import json
import logging
import time
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from typing import TypedDict

from printing_utils import (
    FONT_BASE_W,
    adjust_logo_position,
    sanitize_text,
    text_width_dots,
)


def _get_win32print():
    mod = globals().get("win32print")
    if mod is None:
        mod = importlib.import_module("win32print")
        globals()["win32print"] = mod
    return mod


def __getattr__(name: str):
    if name == "win32print":
        return _get_win32print()
    raise AttributeError(f"module {__name__} has no attribute {name}")


def melhorar_logo(*args, **kwargs):
    utils = importlib.import_module("utils")
    return utils.melhorar_logo(*args, **kwargs)


def recurso_caminho(*args, **kwargs):
    utils = importlib.import_module("utils")
    return utils.recurso_caminho(*args, **kwargs)


@lru_cache(maxsize=1)
def _load_templates_json() -> dict[str, dict]:
    path = recurso_caminho("templates.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _logger():
    return importlib.import_module("log").logger


def carregar_config():
    return importlib.import_module("persistence").carregar_config()


def salvar_config(cfg):
    return importlib.import_module("persistence").salvar_config(cfg)

DOTS_MM: int = 8   # ~203 dpi
ENCODING: str = "cp1252"  # TSPL espera 8-bit (latin-1/cp1252)

# -------------------- templates (tamanho/direction) --------------------
_DEFAULT_TEMPLATE_DIM = {
    "100x30": {"largura_mm": 100, "altura_mm": 30, "gap_mm": 2, "direction": 1},
    "60x80": {"largura_mm": 60, "altura_mm": 80, "gap_mm": 2, "direction": 0},
}


@dataclass
class Template:
    largura_mm: int
    altura_mm: int
    gap_mm: int
    direction: int
    layout: Layout


class TemplateManager:
    def _load_templates_dim(self) -> dict[str, dict]:
        """Carrega templates.json. Aceita tanto dimensões quanto posições.
        Se houver falha, retorna fallback somente com dimensões."""
        try:
            templates = _load_templates_json()
            _logger().info(
                "Templates carregados de %s: %s",
                recurso_caminho("templates.json"),
                ", ".join(templates.keys()),
            )
            return templates
        except Exception:
            _logger().exception(
                "Falha ao carregar templates.json; usando dimensões padrão."
            )
            return _DEFAULT_TEMPLATE_DIM.copy()

    def recarregar_templates(self) -> None:
        """Força recarga do templates.json (dimensões e, se existir, posições)."""
        _load_templates_json.cache_clear()
        self._load_templates_dim()

    def _resolver_nome_template(
        self, nome: str, d: dict[str, dict]
    ) -> tuple[str, dict]:
        """Resolve nome considerando normalização e aliases."""
        modelo = d.get(nome)
        if modelo:
            return nome, modelo
        n_alvo = _norm_key(nome)
        for k, v in d.items():
            if _norm_key(k) == n_alvo:
                return k, v
        if n_alvo in ALIASES:
            alvo = ALIASES[n_alvo]
            modelo = d.get(alvo)
            if modelo:
                return alvo, modelo
            for k, v in d.items():
                if _norm_key(k) == _norm_key(alvo):
                    return k, v
        if _DEFAULT_LAYOUT_KEY in d:
            return _DEFAULT_LAYOUT_KEY, d[_DEFAULT_LAYOUT_KEY]
        k = next(iter(d))
        return k, d[k]

    def _extrair_layout_do_json(self, modelo: dict) -> Layout | None:
        """
        Se o dicionário do template no JSON tiver os campos de
        posição, retorna Layout.
        """
        campos = {
            "titulo",
            "saida",
            "categoria",
            "emissor",
            "municipio",
            "data",
            "fracao",
            "fragil",
            "numeracao",
        }
        if not any(k in modelo for k in campos):
            return None
        layout: Layout = {}
        for k in campos:
            if k in modelo:
                layout[k] = modelo[k]  # type: ignore[assignment]
        for k in ("logo_y", "logo_largura", "logo_x", "logo_x_mm"):
            if k in modelo:
                layout[k] = modelo[k]  # type: ignore[assignment]
        return layout

    def get_template(self, nome: str) -> Template:
        templates_dim = self._load_templates_dim()
        nome_dim, modelo_dim = self._resolver_nome_template(nome, templates_dim)

        largura_mm = int(modelo_dim.get("largura_mm", 60))
        altura_mm = int(modelo_dim.get("altura_mm", 80))
        gap_mm = int(modelo_dim.get("gap_mm", 2))
        direction = int(modelo_dim.get("direction", 1))

        layout_json = self._extrair_layout_do_json(modelo_dim)
        if layout_json is not None:
            layout_escolhido = layout_json
        else:
            _, layout_escolhido = self._resolver_nome_template(nome_dim, LAYOUTS)

        layout_escolhido = copy.deepcopy(layout_escolhido)

        for req in (
            "titulo",
            "saida",
            "categoria",
            "emissor",
            "municipio",
            "data",
            "fracao",
            "fragil",
            "numeracao",
        ):
            if req not in layout_escolhido:
                raise ValueError(
                    f"Layout '{nome_dim}' incorreto: campo '{req}' ausente."
                )

        _ajustar_altura_layout(layout_escolhido, altura_mm)
        _ajustar_largura_layout(layout_escolhido, largura_mm)

        tpl = Template(
            largura_mm=largura_mm,
            altura_mm=altura_mm,
            gap_mm=gap_mm,
            direction=direction,
            layout=layout_escolhido,
        )
        return tpl


template_manager = TemplateManager()


def _get_templates() -> dict[str, dict]:
    """Retorna o dicionário de templates carregado."""
    return template_manager._load_templates_dim()

# -------------------- layout (posições) --------------------
class TextoLayout(TypedDict):
    x: int
    y: int
    font: str
    xm: int
    ym: int

class Layout(TypedDict, total=False):
    titulo: TextoLayout
    saida: TextoLayout
    categoria: TextoLayout
    emissor: TextoLayout
    municipio: TextoLayout
    data: TextoLayout
    fracao: TextoLayout
    fragil: TextoLayout
    numeracao: TextoLayout
    logo_y: int
    logo_largura: int
    logo_x: int
    logo_x_mm: float

# Fallback embutido para posições
LAYOUTS: dict[str, Layout] = {
    "60x80":{
        "largura_mm":60,"altura_mm":80,"gap_mm":2,"direction":0,
        "titulo":     {"x":20,"y":10,"font":"3","xm":2,"ym":2},
        "saida":      {"x":20,"y":70,"font":"2","xm":1,"ym":1},
        "categoria":  {"x":20,"y":100,"font":"2","xm":1,"ym":1},
        "emissor":    {"x":20,"y":130,"font":"2","xm":1,"ym":1},
        "municipio":  {"x":20,"y":180,"font":"2","xm":1,"ym":1},
        "data":       {"x":20,"y":230,"font":"2","xm":1,"ym":1},
        "fracao":     {"x":20,"y":270,"font":"2","xm":1,"ym":1},
        "fragil":     {"x":280,"y":270,"font":"2","xm":1,"ym":1},
        "numeracao":  {"x": 180, "y": 360, "font": "5", "xm": 2, "ym": 2},
        "logo_y":700,"logo_largura":220
    },

    "100x30": {
        "titulo":    {"x": 20,  "y": 20,  "font": "3", "xm": 1, "ym": 1},
        "saida":     {"x": 20,  "y": 60,  "font": "2", "xm": 1, "ym": 1},
        "categoria": {"x": 20,  "y": 90,  "font": "2", "xm": 1, "ym": 1},
        "emissor":   {"x": 20,  "y": 120, "font": "2", "xm": 1, "ym": 1},
        "municipio": {"x": 20,  "y": 150, "font": "2", "xm": 1, "ym": 1},
        "data":      {"x": 20,  "y": 180, "font": "2", "xm": 1, "ym": 1},
        "fracao":    {"x": 20,  "y": 220, "font": "2", "xm": 1, "ym": 1},
        "fragil":    {"x": 200, "y": 220, "font": "2", "xm": 1, "ym": 1},
        "numeracao": {"x": 450, "y": 36,  "font": "2", "xm": 2, "ym": 2},
        "logo_y": 75,
        "logo_largura": 120,
        "logo_x": 550
    }
}

# -------------------- Aliases (compatibilidade) --------------------
ALIASES = {
    "padrao": "100x30",
    "padrão": "100x30",
}

# -------------------- Defaults de dimensões --------------------
_DEFAULT_LAYOUT_KEY = "100x30"

def _norm_key(s: str) -> str:
    s = unicodedata.normalize("NFKD", s) if s else ""
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.strip().lower()


def listar_templates() -> list[str]:
    """Lista (união) dos nomes presentes no templates.json e nos fallbacks."""
    nomes = set(LAYOUTS.keys())
    try:
        for k in template_manager._load_templates_dim().keys():
            nomes.add(k)
    except Exception:
        pass
    return sorted(nomes)


def _ajustar_altura_layout(layout: Layout, altura_mm: int) -> None:
    limite = altura_mm * DOTS_MM
    for chave, espec in layout.items():
        if not isinstance(espec, dict) or "y" not in espec:
            continue
        base = FONT_BASE_W.get(str(espec.get("font", "2")), 12)
        ym = max(int(espec.get("ym", 1)), 1)
        altura = base * ym
        if espec["y"] + altura <= limite:
            continue

        orig_y = espec["y"]
        orig_ym = ym

        if chave in {"fracao", "fragil"}:
            novo_y = limite - altura
            if novo_y < 0:
                max_ym = max(1, limite // base)
                if max_ym != orig_ym:
                    _logger().debug("Ajuste '%s.ym': %s -> %s", chave, orig_ym, max_ym)
                espec["ym"] = max_ym
                altura = base * max_ym
                novo_y = max(0, limite - altura)
            if novo_y != orig_y:
                _logger().debug("Ajuste '%s.y': %s -> %s", chave, orig_y, novo_y)
                espec["y"] = novo_y
                outro = "fragil" if chave == "fracao" else "fracao"
                if outro in layout and isinstance(layout[outro], dict):
                    outro_y = layout[outro].get("y")
                    if outro_y != novo_y:
                        _logger().debug(
                            "Ajuste '%s.y': %s -> %s", outro, outro_y, novo_y
                        )
                layout[outro]["y"] = novo_y
        else:
            max_ym = max(1, (limite - espec["y"]) // base)
            if max_ym != orig_ym:
                _logger().debug("Ajuste '%s.ym': %s -> %s", chave, orig_ym, max_ym)
            espec["ym"] = max_ym
            altura = base * max_ym
            if espec["y"] + altura > limite:
                novo_y = max(0, limite - altura)
                if novo_y != orig_y:
                    _logger().debug("Ajuste '%s.y': %s -> %s", chave, orig_y, novo_y)
                espec["y"] = novo_y

def _ajustar_largura_layout(layout: Layout, largura_mm: int) -> None:
    limite = largura_mm * DOTS_MM

    textos_padrao = {
        "titulo": "CONIMS",
        "saida": "Saida: 000",
        "categoria": "Categoria: X",
        "emissor": "Emissor: X",
        "municipio": "Municipio: X",
        "data": "Impresso em: 00/00/0000 00:00",
        "fracao": "[ ] Fracao",
        "fragil": "[ ] Fragil",
        "numeracao": "9999 DE 9999",
    }

    for chave, espec in layout.items():
        if not isinstance(espec, dict) or "x" not in espec:
            continue

        texto = textos_padrao.get(chave, "X")
        font = str(espec.get("font", "2"))
        xm = max(int(espec.get("xm", 1)), 1)
        largura = text_width_dots(texto, font, xm)
        if espec["x"] + largura <= limite:
            continue

        orig_x = espec["x"]
        orig_xm = xm

        largura_unit = text_width_dots(texto, font, 1)
        max_xm = max(1, (limite - orig_x) // max(largura_unit, 1))
        if max_xm < orig_xm:
            _logger().debug("Ajuste '%s.xm': %s -> %s", chave, orig_xm, max_xm)
            espec["xm"] = max_xm
            xm = max_xm
            largura = text_width_dots(texto, font, xm)

        if espec["x"] + largura > limite:
            novo_x = max(0, limite - largura)
            if novo_x != orig_x:
                _logger().debug("Ajuste '%s.x': %s -> %s", chave, orig_x, novo_x)
            espec["x"] = novo_x

    # Ajuste do logo
    adjust_logo_position(layout, largura_mm, DOTS_MM)

def aplicar_template(nome: str) -> Template:
    """Carrega e ajusta o template solicitado."""
    tpl = template_manager.get_template(nome)
    _logger().info(
        "Template aplicado: nome=%s largura_mm=%s altura_mm=%s gap_mm=%s direction=%s",
        nome,
        tpl.largura_mm,
        tpl.altura_mm,
        tpl.gap_mm,
        tpl.direction,
    )
    return tpl

class ErroImpressora(TypedDict):
    code: int
    message: str

def descobrir_impressora_padrao() -> str | None:
    """Retorna o nome da impressora configurada ou a padrão do sistema."""
    try:
        win32print = _get_win32print()
        nome = win32print.GetDefaultPrinter()
        config = carregar_config()
        config["ultima_impressora"] = nome
        salvar_config(config)
        return str(nome)
    except Exception:
        try:
            config = carregar_config()
            nome = config.get("ultima_impressora")
            if nome:
                win32print = _get_win32print()
                handle = win32print.OpenPrinter(nome)
                win32print.ClosePrinter(handle)
                return str(nome)
        except Exception:
            pass
        return None

def _texto_layout(chave: str, texto: str, layout: Layout) -> str:
    p = layout[chave]
    v = sanitize_text(texto)
    return f'TEXT {p["x"]},{p["y"]},"{p["font"]}",0,{p["xm"]},{p["ym"]},"{v}"\r\n'

def _calc_logo_x(layout: Layout, dots_x: int, largura_bytes: int) -> int:
    if "logo_x_mm" in layout:
        x_logo = int(layout["logo_x_mm"] * DOTS_MM)  # type: ignore[index]
    elif "logo_x" in layout:
        x_logo = int(layout["logo_x"])  # type: ignore[index]
    else:
        x_logo = (dots_x - (largura_bytes * 8)) // 2  # centraliza
    return max(0, min(x_logo, max(0, dots_x - (largura_bytes * 8))))


class TsplBuilder:
    """Gera comandos TSPL a partir de um ``Template``."""

    def __init__(self, template: Template) -> None:
        self.template = template
        self.layout = template.layout

        logo_path = recurso_caminho("logo.png")
        largura_desejada = int(self.layout.get("logo_largura", 240))
        self.bitmap, self.largura_bytes, self.altura_px = melhorar_logo(
            logo_path, largura_desejada=largura_desejada
        )

        self.dots_x = template.largura_mm * DOTS_MM
        self.dots_y = template.altura_mm * DOTS_MM

        logo_y = int(self.layout.get("logo_y", 0))
        if logo_y + self.altura_px > self.dots_y:
            limite = self.dots_y
            altura_logo = self.altura_px
            novo_y = max(0, limite - altura_logo)
            if novo_y != logo_y:
                _logger().debug("Ajuste 'logo_y': %s -> %s", logo_y, novo_y)
                self.layout["logo_y"] = novo_y
                logo_y = novo_y
            if altura_logo > limite:
                max_largura = max(1, int(largura_desejada * limite / altura_logo))
                if max_largura != largura_desejada:
                    _logger().debug(
                        "Ajuste 'logo_largura': %s -> %s", largura_desejada, max_largura
                    )
                self.layout["logo_largura"] = max_largura
                largura_desejada = max_largura
                importlib.import_module("utils").melhorar_logo.cache_clear()
                self.bitmap, self.largura_bytes, self.altura_px = melhorar_logo(
                    logo_path, largura_desejada=max_largura
                )
                if self.layout.get("logo_y", 0) + self.altura_px > limite:
                    novo_y = max(0, limite - self.altura_px)
                    self.layout["logo_y"] = novo_y

        self.x_logo = _calc_logo_x(self.layout, self.dots_x, self.largura_bytes)

        for chave in (
            "titulo",
            "saida",
            "categoria",
            "emissor",
            "municipio",
            "data",
            "fracao",
            "fragil",
            "numeracao",
        ):
            if chave not in self.layout:
                raise ValueError(f"Layout incorreto: campo '{chave}' ausente.")

    def _t(self, ch: str, txt: str) -> str:
        return _texto_layout(ch, txt, self.layout)

    def build(self, dados: dict) -> str:
        """Monta etiquetas usando ``dados`` fornecidos."""

        volumes = int(dados.get("volumes", 1))
        inicio_indice = int(dados.get("inicio_indice", 1))
        total_exibicao = dados.get("total_exibicao")
        total_display = total_exibicao if total_exibicao is not None else volumes

        saida = dados.get("saida", "")
        categoria = dados.get("categoria", "")
        emissor = dados.get("emissor", "")
        municipio = dados.get("municipio", "")
        data_hora = dados.get("data_hora", "")

        partes: list[str] = []
        for offset in range(volumes):
            numero_atual = inicio_indice + offset
            cmd = (
                f"SIZE {self.template.largura_mm} mm,{self.template.altura_mm} mm\r\n"
                f"GAP {self.template.gap_mm} mm,0\r\n"
                "DENSITY 8\r\n"
                "SPEED 4\r\n"
                f"DIRECTION {self.template.direction}\r\n"
                "CLS\r\n"
            )
            cmd += self._t("titulo", "CONIMS")
            cmd += self._t("saida", f"Saida: {saida}")
            cmd += self._t("categoria", f"Categoria: {categoria}")
            cmd += self._t("emissor", f"Emissor: {emissor}")
            cmd += self._t("municipio", f"Municipio: {municipio}")
            cmd += self._t("data", f"Impresso em: {data_hora}")
            cmd += self._t("fracao", "[ ] Fracao")
            cmd += self._t("fragil", "[ ] Fragil")
            cmd += self._t("numeracao", f"{numero_atual} DE {total_display}")

            cmd += (
                f"BITMAP {self.x_logo},{self.layout['logo_y']},"
                f"{self.largura_bytes},{self.altura_px},0,"
            )
            cmd += self.bitmap.decode(ENCODING, errors="replace") + "\r\n"
            cmd += "PRINT 1\r\n"
            partes.append(cmd)

        tspl = "".join(partes)
        _logger().debug("tspl_first_200=%r", tspl[:200])
        return tspl

    def build_pagina_teste(self) -> str:
        """Gera comandos para página de teste."""

        ruler_start = self.layout["titulo"]["x"]
        ruler_y = self.dots_y - 40
        ruler_len = min(50 * DOTS_MM, self.dots_x - ruler_start)
        ruler_len -= ruler_len % (10 * DOTS_MM)
        if (
            ruler_len <= 0
            or ruler_start + ruler_len > self.dots_x
            or ruler_y + 4 > self.dots_y
        ):
            raise ValueError("Layout inválido p/ régua de calibração.")

        cmd = (
            f"SIZE {self.template.largura_mm} mm,{self.template.altura_mm} mm\r\n"
            f"GAP {self.template.gap_mm} mm,0\r\n"
            "DENSITY 8\r\n"
            "SPEED 4\r\n"
            f"DIRECTION {self.template.direction}\r\n"
            "CLS\r\n"
        )
        cmd += self._t("titulo", "CONIMS")
        cmd += self._t("saida", "Saida: 000")
        cmd += self._t("categoria", "Categoria: TESTE")
        cmd += self._t("emissor", "Emissor: TESTE")
        cmd += self._t("municipio", "Municipio: TESTE")
        cmd += self._t("data", "Impresso em: 00/00/0000 00:00")
        cmd += self._t("fracao", "[ ] Fracao")
        cmd += self._t("fragil", "[ ] Fragil")
        cmd += self._t("numeracao", "1 DE 1")

        cmd += (
            f"BITMAP {self.x_logo},{self.layout['logo_y']},"
            f"{self.largura_bytes},{self.altura_px},0,"
        )

        barras = f"BAR {ruler_start},{ruler_y},{ruler_len},4\r\n"
        marcas = ruler_len // (10 * DOTS_MM)
        for i in range(marcas + 1):
            altura = 20 if i in (0, marcas) else 12
            x = ruler_start + i * 10 * DOTS_MM
            y = ruler_y - altura
            barras += f"BAR {x},{y},2,{altura}\r\n"

        cmd += self.bitmap.decode(ENCODING, errors="replace")
        cmd += f"\r\n{barras}PRINT 1\r\n"
        _logger().debug("tspl_first_200=%r", cmd[:200])
        return cmd

def montar_tspl(template: Template, dados: dict) -> str:
    """Monta o conteúdo TSPL a partir do template informado e dos dados."""
    builder = TsplBuilder(template)
    return builder.build(dados)


class PrinterService:
    """Serviço responsável por enviar comandos TSPL à impressora."""

    def __init__(
        self,
        printer_name: str | None = None,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self.printer_name = printer_name
        self.logger = logger or _logger()

    def send(
        self, tspl: str, *, retry: int = 1
    ) -> tuple[bool, ErroImpressora | None]:
        nome_imp = self.printer_name
        if not nome_imp:
            nome_imp = descobrir_impressora_padrao()
        if nome_imp is None:
            return False, {"code": 0, "message": "Nenhuma impressora padrão encontrada"}
        log = self.logger
        if log:
            log.debug("impressora=%s tspl_len=%d", nome_imp, len(tspl))

        win32print = _get_win32print()

        for tentativa in range(1, retry + 1):
            if log:
                log.info("Tentativa %s de impressão", tentativa)
            try:
                h_prn = win32print.OpenPrinter(nome_imp)
                win32print.StartDocPrinter(h_prn, 1, ("Etiqueta CONIMS", None, "RAW"))
                win32print.StartPagePrinter(h_prn)
                win32print.WritePrinter(
                    h_prn, tspl.encode(ENCODING, errors="replace")
                )
                win32print.EndPagePrinter(h_prn)
                win32print.EndDocPrinter(h_prn)
                win32print.ClosePrinter(h_prn)
                if log:
                    log.info("Impressão concluída na tentativa %s", tentativa)
                return True, None
            except Exception as e:  # pragma: no cover - usado em Windows
                codigo = getattr(e, "winerror", -1)
                mensagem = getattr(e, "strerror", str(e))
                if log:
                    log.warning(
                        "Falha na tentativa %s de impressão: %s - %s",
                        tentativa,
                        codigo,
                        mensagem,
                    )
                if tentativa == retry:
                    return False, {"code": codigo, "message": mensagem}
                atraso = 0.5 * (2 ** (tentativa - 1))
                time.sleep(atraso)

def imprimir_etiqueta(
    tspl: str,
    repetir_em_falha: bool = False,
    *,
    nome_impressora: str | None = None,
    logger: logging.Logger | None = None,
) -> tuple[bool, ErroImpressora | None]:
    """Envia uma string TSPL já montada para a impressora padrão."""

    service = PrinterService(nome_impressora, logger=logger)
    retry = 3 if repetir_em_falha else 1
    return service.send(tspl, retry=retry)


def imprimir_pagina_teste(
    template: Template,
    repetir_em_falha: bool = False,
    *,
    nome_impressora: str | None = None,
    logger: logging.Logger | None = None,
) -> tuple[bool, ErroImpressora | None]:
    """Imprime uma página de teste usando o template informado."""

    try:
        tspl = TsplBuilder(template).build_pagina_teste()
    except ValueError as e:
        return False, {"code": 0, "message": str(e)}

    return imprimir_etiqueta(
        tspl,
        repetir_em_falha,
        nome_impressora=nome_impressora,
        logger=logger,
    )
