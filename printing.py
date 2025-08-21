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
    "logo_y": 560, "logo_largura": 280
  },
  "100x30": { ... }
}
Se as posições não estiverem no JSON, o código usa LAYOUTS abaixo.
"""

from __future__ import annotations

import json
import time
import unicodedata
from dataclasses import dataclass
from typing import TypedDict

import win32print

from log import logger
from persistence import carregar_config, salvar_config
from utils import melhorar_logo, recurso_caminho

DOTS_MM: int = 8   # ~203 dpi
ENCODING: str = "cp1252"  # TSPL espera 8-bit (latin-1/cp1252)

# Largura base aproximada (em dots) das fontes internas TSPL (ajuste fino se precisar)
FONT_BASE_W = {
    "1": 8,
    "2": 12,
    "3": 16,
    "4": 24,
    "5": 32,
    "6": 40,
}

def _text_width_dots(texto: str, font: str, xm: int) -> int:
    base = FONT_BASE_W.get(str(font), 12)
    xm = int(xm) if int(xm) > 0 else 1
    return len(str(texto)) * base * xm

# -------------------- templates (tamanho/direction) --------------------
_DEFAULT_TEMPLATE_DIM = {
    "100x30": {"largura_mm": 100, "altura_mm": 30, "gap_mm": 2, "direction": 1},
    "60x80": {"largura_mm": 60, "altura_mm": 80, "gap_mm": 2, "direction": 0},
}


TEMPLATES: dict[str, dict] | None = None


@dataclass
class Template:
    largura_mm: int
    altura_mm: int
    gap_mm: int
    direction: int
    layout: Layout
    layout_nome: str


class TemplateManager:
    def __init__(self) -> None:
        self._templates_dim: dict[str, dict] | None = None
        self._templates_dim_mtime: float | None = None

    def _load_templates_dim(self, force: bool = False) -> dict[str, dict]:
        """Carrega templates.json. Aceita tanto dimensões quanto posições.
        Se houver falha, retorna fallback somente com dimensões.
        """
        global TEMPLATES
        try:
            if TEMPLATES is not None:
                self._templates_dim = TEMPLATES
                return self._templates_dim

            self._templates_dim = None
            path = recurso_caminho("templates.json")
            mtime = None
            try:
                import os
                mtime = os.path.getmtime(path)
            except Exception:
                pass

            needs_reload = (
                force
                or self._templates_dim is None
                or (
                    self._templates_dim_mtime is not None
                    and mtime
                    and mtime != self._templates_dim_mtime
                )
            )
            if needs_reload:
                with open(path, "r", encoding="utf-8") as f:
                    self._templates_dim = json.load(f)
                self._templates_dim_mtime = mtime
                TEMPLATES = self._templates_dim
                logger.info(
                    "Templates carregados de %s: %s",
                    path,
                    ", ".join(self._templates_dim.keys()),
                )
            return self._templates_dim  # type: ignore[return-value]
        except Exception:
            logger.exception(
                "Falha ao carregar templates.json; usando dimensões padrão."
            )
            return _DEFAULT_TEMPLATE_DIM.copy()

    def recarregar_templates(self) -> None:
        """Força recarga do templates.json (dimensões e, se existir, posições)."""
        global TEMPLATES
        self._templates_dim = None
        self._templates_dim_mtime = None
        TEMPLATES = None
        self._load_templates_dim(force=True)

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
        """Se o dicionário do template no JSON tiver os campos de posição, retorna Layout."""
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
            nome_layout = nome_dim
        else:
            nome_layout, layout_escolhido = self._resolver_nome_template(
                nome_dim, LAYOUTS
            )

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
                    f"Layout '{nome_layout}' incorreto: campo '{req}' ausente."
                )

        return Template(
            largura_mm=largura_mm,
            altura_mm=altura_mm,
            gap_mm=gap_mm,
            direction=direction,
            layout=layout_escolhido,
            layout_nome=nome_layout,
        )


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
    "60x80": {
        "titulo":    {"x": 20,  "y": 20,  "font": "5", "xm": 3, "ym": 3},
        "saida":     {"x": 20,  "y": 120, "font": "4", "xm": 3, "ym": 3},
        "categoria": {"x": 20,  "y": 200, "font": "4", "xm": 3, "ym": 3},
        "emissor":   {"x": 20,  "y": 280, "font": "4", "xm": 3, "ym": 3},
        "municipio": {"x": 20,  "y": 360, "font": "4", "xm": 3, "ym": 3},
        "data":      {"x": 20,  "y": 440, "font": "4", "xm": 3, "ym": 3},
        "fracao":    {"x": 20,  "y": 520, "font": "4", "xm": 3, "ym": 3},
        "fragil":    {"x": 300, "y": 520, "font": "4", "xm": 3, "ym": 3},
        "numeracao": {"x": 430, "y": 20,  "font": "6", "xm": 2, "ym": 2},
        "logo_y": 560,
        "logo_largura": 280
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
LARGURA_ETIQUETA_MM: int = 100
ALTURA_ETIQUETA_MM: int = 30
GAP_MM: int = 2
DIRECTION: int = 1

_DEFAULT_LAYOUT_KEY = "100x30"
LAYOUT_ATUAL: Layout = LAYOUTS.get("Padrão", LAYOUTS[_DEFAULT_LAYOUT_KEY])
_LAYOUT_NOME_ATUAL: str = _DEFAULT_LAYOUT_KEY

def _norm_key(s: str) -> str:
    s = unicodedata.normalize("NFKD", s) if s else ""
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.strip().lower()

def _sanitize_text(s: str) -> str:
    if s is None:
        return ""
    s = s.replace("\r", " ").replace("\n", " ")
    s = s.replace('"', "'")
    return s

def listar_templates() -> list[str]:
    """Lista (união) dos nomes presentes no templates.json e nos fallbacks."""
    nomes = set(LAYOUTS.keys())
    try:
        for k in template_manager._load_templates_dim().keys():
            nomes.add(k)
    except Exception:
        pass
    return sorted(nomes)

def _text_height_dots(font: str, ym: int) -> int:
    base = FONT_BASE_W.get(str(font), 12)
    ym = int(ym) if int(ym) > 0 else 1
    return base * ym

def _ajustar_altura_layout(layout: Layout) -> None:
    limite = ALTURA_ETIQUETA_MM * DOTS_MM
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
                    logger.debug("Ajuste '%s.ym': %s -> %s", chave, orig_ym, max_ym)
                espec["ym"] = max_ym
                altura = base * max_ym
                novo_y = max(0, limite - altura)
            if novo_y != orig_y:
                logger.debug("Ajuste '%s.y': %s -> %s", chave, orig_y, novo_y)
                espec["y"] = novo_y
                outro = "fragil" if chave == "fracao" else "fracao"
                if outro in layout and isinstance(layout[outro], dict):
                    outro_y = layout[outro].get("y")
                    if outro_y != novo_y:
                        logger.debug("Ajuste '%s.y': %s -> %s", outro, outro_y, novo_y)
                layout[outro]["y"] = novo_y
        else:
            max_ym = max(1, (limite - espec["y"]) // base)
            if max_ym != orig_ym:
                logger.debug("Ajuste '%s.ym': %s -> %s", chave, orig_ym, max_ym)
            espec["ym"] = max_ym
            altura = base * max_ym
            if espec["y"] + altura > limite:
                novo_y = max(0, limite - altura)
                if novo_y != orig_y:
                    logger.debug("Ajuste '%s.y': %s -> %s", chave, orig_y, novo_y)
                espec["y"] = novo_y

def _ajustar_largura_layout(layout: Layout) -> None:
    limite = LARGURA_ETIQUETA_MM * DOTS_MM

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
        largura = _text_width_dots(texto, font, xm)
        if espec["x"] + largura <= limite:
            continue

        orig_x = espec["x"]
        orig_xm = xm

        largura_unit = _text_width_dots(texto, font, 1)
        max_xm = max(1, (limite - orig_x) // max(largura_unit, 1))
        if max_xm < orig_xm:
            logger.debug("Ajuste '%s.xm': %s -> %s", chave, orig_xm, max_xm)
            espec["xm"] = max_xm
            xm = max_xm
            largura = _text_width_dots(texto, font, xm)

        if espec["x"] + largura > limite:
            novo_x = max(0, limite - largura)
            if novo_x != orig_x:
                logger.debug("Ajuste '%s.x': %s -> %s", chave, orig_x, novo_x)
            espec["x"] = novo_x

    # Ajuste do logo
    logo_largura = layout.get("logo_largura")
    if isinstance(logo_largura, int):
        if logo_largura > limite:
            logger.debug("Ajuste 'logo_largura': %s -> %s", logo_largura, limite)
            layout["logo_largura"] = limite
            logo_largura = limite

    if "logo_x_mm" in layout:
        logo_x_mm = float(layout.get("logo_x_mm", 0))
        largura_mm = (logo_largura or 0) / DOTS_MM
        max_x_mm = max(0, LARGURA_ETIQUETA_MM - largura_mm)
        if logo_x_mm > max_x_mm:
            logger.debug("Ajuste 'logo_x_mm': %s -> %s", logo_x_mm, max_x_mm)
            layout["logo_x_mm"] = max_x_mm
    elif "logo_x" in layout:
        logo_x = int(layout.get("logo_x", 0))
        max_x = max(0, limite - int(logo_largura or 0))
        if logo_x > max_x:
            logger.debug("Ajuste 'logo_x': %s -> %s", logo_x, max_x)
            layout["logo_x"] = max_x

def aplicar_template(nome: str) -> None:
    """Define qual template será utilizado nas impressões (dimensões + posições)."""
    global LARGURA_ETIQUETA_MM, ALTURA_ETIQUETA_MM, GAP_MM, DIRECTION, LAYOUT_ATUAL, _LAYOUT_NOME_ATUAL

    tpl = template_manager.get_template(nome)

    LARGURA_ETIQUETA_MM = tpl.largura_mm
    ALTURA_ETIQUETA_MM = tpl.altura_mm
    GAP_MM = tpl.gap_mm
    DIRECTION = tpl.direction

    LAYOUT_ATUAL = tpl.layout
    _LAYOUT_NOME_ATUAL = tpl.layout_nome
    _ajustar_altura_layout(LAYOUT_ATUAL)
    _ajustar_largura_layout(LAYOUT_ATUAL)

    logger.info(
        "Template aplicado: nome=%s (layout=%s) largura_mm=%s altura_mm=%s gap_mm=%s direction=%s",
        nome,
        tpl.layout_nome,
        LARGURA_ETIQUETA_MM,
        ALTURA_ETIQUETA_MM,
        GAP_MM,
        DIRECTION,
    )

class ErroImpressora(TypedDict):
    code: int
    message: str

def descobrir_impressora_padrao() -> str | None:
    """Retorna o nome da impressora configurada ou a padrão do sistema."""
    try:
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
                handle = win32print.OpenPrinter(nome)
                win32print.ClosePrinter(handle)
                return str(nome)
        except Exception:
            pass
        return None

def _texto_layout(chave: str, texto: str, layout: Layout) -> str:
    p = layout[chave]
    v = _sanitize_text(texto)
    return f'TEXT {p["x"]},{p["y"]},"{p["font"]}",0,{p["xm"]},{p["ym"]},"{v}"\r\n'

def _calc_logo_x(layout: Layout, dots_x: int, largura_bytes: int) -> int:
    if "logo_x_mm" in layout:
        x_logo = int(layout["logo_x_mm"] * DOTS_MM)  # type: ignore[index]
    elif "logo_x" in layout:
        x_logo = int(layout["logo_x"])  # type: ignore[index]
    else:
        x_logo = (dots_x - (largura_bytes * 8)) // 2  # centraliza
    return max(0, min(x_logo, max(0, dots_x - (largura_bytes * 8))))

def montar_tspl(template: Layout, dados: dict) -> str:
    """Monta o conteúdo TSPL a partir do layout informado e dos dados."""
    layout = template

    logo_path = recurso_caminho("logo.png")
    bitmap, largura_bytes, altura_px = melhorar_logo(
        logo_path, largura_desejada=layout.get("logo_largura", 240)
    )

    dots_x = LARGURA_ETIQUETA_MM * DOTS_MM
    x_logo = _calc_logo_x(layout, dots_x, largura_bytes)

    for chave in ("titulo","saida","categoria","emissor","municipio","data","fracao","fragil","numeracao"):
        if chave not in layout:
            raise ValueError(f"Layout incorreto: campo '{chave}' ausente.")

    def t(ch: str, txt: str) -> str:
        return _texto_layout(ch, txt, layout)

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
            f"SIZE {LARGURA_ETIQUETA_MM} mm,{ALTURA_ETIQUETA_MM} mm\r\n"
            f"GAP {GAP_MM} mm,0\r\n"
            "DENSITY 8\r\n"
            "SPEED 4\r\n"
            f"DIRECTION {DIRECTION}\r\n"
            "CLS\r\n"
        )
        cmd += t("titulo", "CONIMS")
        cmd += t("saida", f"Saida: {saida}")
        cmd += t("categoria", f"Categoria: {categoria}")
        cmd += t("emissor", f"Emissor: {emissor}")
        cmd += t("municipio", f"Municipio: {municipio}")
        cmd += t("data", f"Impresso em: {data_hora}")
        cmd += t("fracao", "[ ] Fracao")
        cmd += t("fragil", "[ ] Fragil")
        cmd += t("numeracao", f"{numero_atual} DE {total_display}")

        cmd += f"BITMAP {x_logo},{layout['logo_y']},{largura_bytes},{altura_px},0,"
        cmd += bitmap.decode(ENCODING, errors="replace") + "\r\n"
        cmd += "PRINT 1\r\n"
        partes.append(cmd)

    tspl = "".join(partes)
    logger.debug("tspl_first_200=%r", tspl[:200])
    return tspl

def imprimir_etiqueta(tspl: str, repetir_em_falha: bool = False) -> tuple[bool, ErroImpressora | None]:
    """Envia uma string TSPL já montada para a impressora padrão."""
    nome_imp = descobrir_impressora_padrao()
    if nome_imp is None:
        return False, {"code": 0, "message": "Nenhuma impressora padrão encontrada"}
    logger.debug("impressora=%s tspl_len=%d", nome_imp, len(tspl))

    max_tentativas = 3 if repetir_em_falha else 1
    for tentativa in range(1, max_tentativas + 1):
        logger.info("Tentativa %s de impressão", tentativa)
        try:
            h_prn = win32print.OpenPrinter(nome_imp)
            win32print.StartDocPrinter(h_prn, 1, ("Etiqueta CONIMS", None, "RAW"))
            win32print.StartPagePrinter(h_prn)
            win32print.WritePrinter(h_prn, tspl.encode(ENCODING, errors="replace"))
            win32print.EndPagePrinter(h_prn)
            win32print.EndDocPrinter(h_prn)
            win32print.ClosePrinter(h_prn)
            logger.info("Impressão concluída na tentativa %s", tentativa)
            return True, None
        except Exception as e:
            codigo = getattr(e, "winerror", -1)
            mensagem = getattr(e, "strerror", str(e))
            logger.warning("Falha na tentativa %s de impressão: %s - %s", tentativa, codigo, mensagem)
            if tentativa == max_tentativas:
                return False, {"code": codigo, "message": mensagem}
            atraso = 0.5 * (2 ** (tentativa - 1))
            time.sleep(atraso)

def imprimir_pagina_teste(repetir_em_falha: bool = False) -> tuple[bool, ErroImpressora | None]:
    """Imprime uma página de teste usando o layout atual (régua + campos fictícios)."""
    layout = LAYOUT_ATUAL

    logo_path = recurso_caminho("logo.png")
    bitmap, largura_bytes, altura_px = melhorar_logo(
        logo_path, largura_desejada=layout.get("logo_largura", 240)
    )

    dots_x = LARGURA_ETIQUETA_MM * DOTS_MM
    dots_y = ALTURA_ETIQUETA_MM * DOTS_MM
    x_logo = _calc_logo_x(layout, dots_x, largura_bytes)

    for chave in ("titulo","saida","categoria","emissor","municipio","data","fracao","fragil","numeracao"):
        if chave not in layout:
            return False, {"code": 0, "message": f"Layout incorreto: campo '{chave}' ausente."}

    ruler_start = layout["titulo"]["x"]
    ruler_y = dots_y - 40
    ruler_len = min(50 * DOTS_MM, dots_x - ruler_start)
    ruler_len -= ruler_len % (10 * DOTS_MM)
    if ruler_len <= 0 or ruler_start + ruler_len > dots_x or ruler_y + 4 > dots_y:
        return False, {"code": 0, "message": "Layout inválido p/ régua de calibração."}

    nome_imp = descobrir_impressora_padrao()
    if nome_imp is None:
        return False, {"code": 0, "message": "Nenhuma impressora padrão encontrada"}

    max_tentativas = 3 if repetir_em_falha else 1
    for tentativa in range(1, max_tentativas + 1):
        logger.info("Tentativa %s de impressão", tentativa)
        try:
            h_prn = win32print.OpenPrinter(nome_imp)
            win32print.StartDocPrinter(h_prn, 1, ("Etiqueta CONIMS", None, "RAW"))
            win32print.StartPagePrinter(h_prn)

            def t(ch: str, txt: str) -> str:
                return _texto_layout(ch, txt, layout)

            cmd = (
                f"SIZE {LARGURA_ETIQUETA_MM} mm,{ALTURA_ETIQUETA_MM} mm\r\n"
                f"GAP {GAP_MM} mm,0\r\n"
                "DENSITY 8\r\n"
                "SPEED 4\r\n"
                f"DIRECTION {DIRECTION}\r\n"
                "CLS\r\n"
            )
            cmd += t("titulo", "CONIMS")
            cmd += t("saida", "Saida: 000")
            cmd += t("categoria", "Categoria: TESTE")
            cmd += t("emissor", "Emissor: TESTE")
            cmd += t("municipio", "Municipio: TESTE")
            cmd += t("data", "Impresso em: 00/00/0000 00:00")
            cmd += t("fracao", "[ ] Fracao")
            cmd += t("fragil", "[ ] Fragil")
            cmd += t("numeracao", "1 DE 1")

            cmd += f"BITMAP {x_logo},{layout['logo_y']},{largura_bytes},{altura_px},0,"

            # régua (marcas a cada 10 mm)
            barras = f"BAR {ruler_start},{ruler_y},{ruler_len},4\r\n"
            marcas = ruler_len // (10 * DOTS_MM)
            for i in range(marcas + 1):
                altura = 20 if i in (0, marcas) else 12
                x = ruler_start + i * 10 * DOTS_MM
                y = ruler_y - altura
                barras += f"BAR {x},{y},2,{altura}\r\n"

            cmd += bitmap.decode(ENCODING, errors="replace")
            cmd += f"\r\n{barras}PRINT 1\r\n"

            logger.debug("impressora=%s tspl_len=%d", nome_imp, len(cmd))
            logger.debug("tspl_first_200=%r", cmd[:200])

            win32print.WritePrinter(h_prn, cmd.encode(ENCODING, errors="replace"))
            win32print.EndPagePrinter(h_prn)
            win32print.EndDocPrinter(h_prn)
            win32print.ClosePrinter(h_prn)
            logger.info("Impressão concluída na tentativa %s", tentativa)
            return True, None
        except Exception as e:
            codigo = getattr(e, "winerror", -1)
            mensagem = getattr(e, "strerror", str(e))
            logger.warning("Falha na tentativa %s de impressão: %s - %s", tentativa, codigo, mensagem)
            if tentativa == max_tentativas:
                return False, {"code": codigo, "message": mensagem}
            atraso = 0.5 * (2 ** (tentativa - 1))
            time.sleep(atraso)
