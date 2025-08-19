"""Rotinas relacionadas à impressão das etiquetas.

Responsabilidade:
    Montar comandos TSPL e enviar dados para impressoras térmicas.

Dependências:
    - win32print
    - log
    - persistence
    - utils

Exemplo:
    >>> from printing import LAYOUT_ATUAL, montar_tspl, imprimir_etiqueta
    >>> tspl = montar_tspl(LAYOUT_ATUAL, {})
    >>> imprimir_etiqueta(tspl)
"""

import json
import time
import unicodedata
from typing import TypedDict

import win32print

from log import logger
from persistence import carregar_config, salvar_config
from utils import melhorar_logo, recurso_caminho

DOTS_MM: int = 8  # ~203 dpi
ENCODING: str = "cp1252"  # TSPL espera 8-bit (latin-1/cp1252)

# Largura base aproximada (em dots) dos fonts TSPL internos (ajuste fino se precisar)
FONT_BASE_W = {
    "1": 8,
    "2": 12,
    "3": 16,
    "4": 24,
    "5": 32,
}


def _text_width_dots(texto: str, font: str, xm: int) -> int:
    """Largura aproximada do texto em dots (considerando fontes internas TSPL)."""
    base = FONT_BASE_W.get(str(font), 12)
    xm = int(xm) if int(xm) > 0 else 1
    return len(str(texto)) * base * xm


# -------------------- templates --------------------
_DEFAULT_TEMPLATE = {
    "60x80": {"largura_mm": 60, "altura_mm": 80, "gap_mm": 2}
}

TEMPLATES: dict[str, dict[str, int]] | None = None


def _get_templates() -> dict[str, dict[str, int]]:
    """Carrega ``templates.json`` sob demanda, com fallback seguro."""

    global TEMPLATES
    if TEMPLATES is not None:
        return TEMPLATES

    try:
        with open(recurso_caminho("templates.json"), "r", encoding="utf-8") as f:
            TEMPLATES = json.load(f)
    except Exception:
        logger.exception(
            "Falha ao carregar templates.json; usando template padrão."
        )
        TEMPLATES = _DEFAULT_TEMPLATE.copy()
    return TEMPLATES


class TextoLayout(TypedDict):
    x: int
    y: int
    font: str
    xm: int
    ym: int


class Layout(TypedDict):
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
    # opcional: numeracao_total -> quando presente, imprime "DE N" separado
    # numeracao_total: TextoLayout  # deixamos não tipado para evitar dependências


LAYOUTS: dict[str, Layout] = {
    "60x80": {
        "titulo": {"x": 30, "y": 20, "font": "3", "xm": 2, "ym": 2},
        "saida": {"x": 30, "y": 70, "font": "2", "xm": 1, "ym": 1},
        "categoria": {"x": 30, "y": 90, "font": "2", "xm": 1, "ym": 1},
        "emissor": {"x": 30, "y": 120, "font": "2", "xm": 1, "ym": 1},
        "municipio": {"x": 30, "y": 150, "font": "2", "xm": 1, "ym": 1},
        "data": {"x": 30, "y": 180, "font": "2", "xm": 1, "ym": 1},
        "fracao": {"x": 30, "y": 220, "font": "2", "xm": 1, "ym": 1},
        "fragil": {"x": 30, "y": 270, "font": "2", "xm": 1, "ym": 1},
        "numeracao": {"x": 30, "y": 330, "font": "4", "xm": 2, "ym": 2},
        "logo_y": 400,
        "logo_largura": 240,
    },
    "Compacto": {
        "titulo": {"x": 30, "y": 15, "font": "3", "xm": 2, "ym": 2},
        "saida": {"x": 30, "y": 52, "font": "2", "xm": 1, "ym": 1},
        "categoria": {"x": 30, "y": 68, "font": "2", "xm": 1, "ym": 1},
        "emissor": {"x": 30, "y": 90, "font": "2", "xm": 1, "ym": 1},
        "municipio": {"x": 30, "y": 112, "font": "2", "xm": 1, "ym": 1},
        "data": {"x": 30, "y": 135, "font": "2", "xm": 1, "ym": 1},
        "fracao": {"x": 30, "y": 165, "font": "2", "xm": 1, "ym": 1},
        "fragil": {"x": 30, "y": 202, "font": "2", "xm": 1, "ym": 1},
        "numeracao": {"x": 30, "y": 248, "font": "4", "xm": 2, "ym": 2},
        "logo_y": 338,
        "logo_largura": 240,
    },
    "100x30": {
        "titulo": {"x": 20, "y": 20, "font": "3", "xm": 1, "ym": 1},
        "saida": {"x": 20, "y": 60, "font": "2", "xm": 1, "ym": 1},
        "categoria": {"x": 20, "y": 90, "font": "2", "xm": 1, "ym": 1},
        "emissor": {"x": 20, "y": 120, "font": "2", "xm": 1, "ym": 1},
        "municipio": {"x": 20, "y": 150, "font": "2", "xm": 1, "ym": 1},
        "data": {"x": 20, "y": 180, "font": "2", "xm": 1, "ym": 1},

        # [ ] Fração e [ ] Frágil lado a lado (mesma linha)
        "fracao": {"x": 20,  "y": 220, "font": "2", "xm": 1, "ym": 1},
        "fragil": {"x": 200, "y": 220, "font": "2", "xm": 1, "ym": 1},

        # Numeração (número e "DE N" na mesma linha; "DE N" segue a largura do número)
        "numeracao": {"x": 500, "y": 36, "font": "2", "xm": 2, "ym": 2},

        # Logo
        "logo_y": 75,
        "logo_largura": 120,
        "logo_x": 550
    }

}

# Campo opcional: imprime "DE N" separado (seguir X dinamicamente)
LAYOUTS["100x30"]["numeracao_total"] = {  # type: ignore[index]
    "x": 550,
    "y": 36,
    "font": "2",
    "xm": 2,
    "ym": 2,
    # parâmetros extras (não TSPL): seguem o número automaticamente
    "follow": True,   # True = calcula X com base na largura do número
    "gap_mm": 2.0,    # folga entre número e "DE", em milímetros
}

# Alias de layout para acesso direto
LAYOUTS["Panoramico"] = LAYOUTS["100x30"]

# -------------------- Aliases de nomes (compatibilidade) --------------------
# Só usamos se o nome solicitado NÃO existir em TEMPLATES/LAYOUTS.
ALIASES = {
    "panoramico": "100x30",
    "panorâmico": "100x30",
    "padrao": "60x80",
    "padrão": "60x80",
}

# -------------------- Defaults seguros (sem depender de "Padrão") --------------------
# Dimensões default até aplicar um template real
LARGURA_ETIQUETA_MM: int = 60
ALTURA_ETIQUETA_MM: int = 80
GAP_MM: int = 2

# Layout default: usa o primeiro disponível se "Padrão" não existir
_DEFAULT_LAYOUT_KEY = next(iter(LAYOUTS))
LAYOUT_ATUAL: Layout = LAYOUTS.get("Padrão", LAYOUTS[_DEFAULT_LAYOUT_KEY])


def _norm_key(s: str) -> str:
    """Normaliza string para comparação (sem acentos, minúsculas, trim)."""
    s = unicodedata.normalize("NFKD", s) if s else ""
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.strip().lower()


def _sanitize_text(s: str) -> str:
    """Sanitiza texto para TSPL (remove quebras e troca aspas duplas por simples)."""
    if s is None:
        return ""
    s = s.replace("\r", " ").replace("\n", " ")
    s = s.replace('"', "'")
    return s


def listar_templates() -> list[str]:
    """Retorna a lista de nomes de templates disponíveis."""
    return list(_get_templates().keys())


def aplicar_template(nome: str) -> None:
    """Define qual template será utilizado nas impressões."""

    # 1) Resolve o modelo (TEMPLATES)
    templates = _get_templates()
    modelo = templates.get(nome)
    if not modelo:
        n_alvo = _norm_key(nome)
        # tenta normalizado
        for k, v in templates.items():
            if _norm_key(k) == n_alvo:
                modelo = v
                nome = k
                break
        # se ainda não encontrou, aplica alias
        if not modelo and n_alvo in ALIASES:
            nome = ALIASES[n_alvo]
            modelo = templates.get(nome)
            if not modelo:
                for k, v in templates.items():
                    if _norm_key(k) == _norm_key(nome):
                        modelo = v
                        nome = k
                        break
    if not modelo:
        # fallback: primeiro template disponível
        nome = next(iter(templates))
        modelo = templates[nome]

    # 2) Resolve o layout (LAYOUTS) com o mesmo nome (ou alias se preciso)
    layout_escolhido = LAYOUTS.get(nome)
    if not layout_escolhido:
        n_alvo = _norm_key(nome)
        for k, v in LAYOUTS.items():
            if _norm_key(k) == n_alvo:
                layout_escolhido = v
                nome = k
                break
        if not layout_escolhido and n_alvo in ALIASES:
            nome2 = ALIASES[n_alvo]
            layout_escolhido = LAYOUTS.get(nome2)
            if not layout_escolhido:
                for k, v in LAYOUTS.items():
                    if _norm_key(k) == _norm_key(nome2):
                        layout_escolhido = v
                        nome = k
                        break
    if not layout_escolhido:
        logger.warning(
            "Layout '%s' não encontrado. Usando o primeiro disponível.",
            nome,
        )
        layout_escolhido = LAYOUTS[next(iter(LAYOUTS))]

    # Campos obrigatórios no layout
    if "fracao" not in layout_escolhido or "fragil" not in layout_escolhido:
        raise ValueError(
            f"Layout '{nome}' deve conter campos 'fracao' e 'fragil'"
        )

    # 3) Aplica dimensões e layout
    global LARGURA_ETIQUETA_MM, ALTURA_ETIQUETA_MM, GAP_MM, LAYOUT_ATUAL
    LARGURA_ETIQUETA_MM = int(modelo.get("largura_mm", 60))
    ALTURA_ETIQUETA_MM = int(modelo.get("altura_mm", 80))
    GAP_MM = int(modelo.get("gap_mm", 2))
    LAYOUT_ATUAL = layout_escolhido
    logger.info(
        "Template aplicado: nome=%s largura_mm=%s altura_mm=%s gap_mm=%s",
        nome, LARGURA_ETIQUETA_MM, ALTURA_ETIQUETA_MM, GAP_MM
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
    """Gera comando ``TEXT`` baseado nas coordenadas do layout informado."""
    p = layout[chave]
    v = _sanitize_text(texto)
    return (f'TEXT {p["x"]},{p["y"]},"{p["font"]}",0,{p["xm"]},{p["ym"]},"{v}"\n')


def _calc_logo_x(layout: Layout, dots_x: int, largura_bytes: int) -> int:
    """Calcula a posição X do logo com override por layout (logo_x ou logo_x_mm)."""
    if "logo_x_mm" in layout:  # type: ignore[operator]
        x_logo = int(layout["logo_x_mm"] * DOTS_MM)  # type: ignore[index]
    elif "logo_x" in layout:  # type: ignore[operator]
        x_logo = int(layout["logo_x"])  # type: ignore[index]
    else:
        x_logo = (dots_x - (largura_bytes * 8)) // 2  # centraliza
    # limita à área imprimível
    return max(0, min(x_logo, max(0, dots_x - (largura_bytes * 8))))


def montar_tspl(template: Layout, dados: dict) -> str:
    """Monta o conteúdo TSPL para impressão de etiquetas.

    ``template`` corresponde ao layout utilizado e ``dados`` deve conter as
    informações necessárias para preencher a etiqueta, como ``saida``,
    ``categoria``, ``emissor``, ``municipio`` e ``data_hora``. Os campos
    ``volumes`` (quantidade de etiquetas), ``inicio_indice`` e
    ``total_exibicao`` controlam a numeração impressa.
    """

    layout = template

    logo_path = recurso_caminho("logo.png")
    bitmap, largura_bytes, altura_px = melhorar_logo(
        logo_path, largura_desejada=layout.get("logo_largura", 240)
    )

    dots_x = LARGURA_ETIQUETA_MM * DOTS_MM
    x_logo = _calc_logo_x(layout, dots_x, largura_bytes)

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
            f"SIZE {LARGURA_ETIQUETA_MM} mm,{ALTURA_ETIQUETA_MM} mm\n"
            f"GAP {GAP_MM} mm,0\n"
            "DENSITY 8\n"
            "SPEED 4\n"
            "DIRECTION 1\n"
            "CLS\n"
        )
        cmd += t("titulo", "CONIMS")
        cmd += t("saida", f"Saida: {saida}")
        cmd += t("categoria", f"Categoria: {categoria}")
        cmd += t("emissor", f"Emissor: {emissor}")
        cmd += t("municipio", f"Municipio: {municipio}")
        cmd += t("data", f"Impresso em: {data_hora}")
        cmd += t("fracao", "[ ] Fracao")
        cmd += t("fragil", "[ ] Fragil")

        if "numeracao_total" in layout:
            cmd += t("numeracao", f"{numero_atual}")
            p_num = layout["numeracao"]
            p_tot = layout["numeracao_total"]  # type: ignore[index]
            follow = bool(p_tot.get("follow", True))  # type: ignore[call-arg]
            gap_mm = float(p_tot.get("gap_mm", 2.0))  # type: ignore[call-arg]
            if follow:
                largura_num = _text_width_dots(
                    str(numero_atual), p_num["font"], p_num["xm"]
                )
                x_de = int(p_num["x"] + largura_num + gap_mm * DOTS_MM)
            else:
                x_de = int(p_tot.get("x", p_num["x"]))  # type: ignore[arg-type]
            y_de = int(p_tot.get("y", p_num["y"]))  # type: ignore[arg-type]
            cmd += (
                f'TEXT {x_de},{y_de},"{p_tot["font"]}",0,{p_tot["xm"]},'
                f'{p_tot["ym"]},"DE {total_display}"\n'
            )
        else:
            cmd += t("numeracao", f"{numero_atual} DE {total_display}")

        cmd += (
            f"BITMAP {x_logo},{layout['logo_y']},{largura_bytes},"
            f"{altura_px},0,"
        )
        cmd += bitmap.decode("latin1")
        cmd += "\nPRINT 1\n"
        partes.append(cmd)

    return "".join(partes)


def imprimir_etiqueta(
    tspl: str, repetir_em_falha: bool = False
) -> tuple[bool, ErroImpressora | None]:
    """Envia uma string TSPL já montada para a impressora padrão."""

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
            win32print.WritePrinter(h_prn, tspl.encode("latin1", errors="replace"))
            win32print.EndPagePrinter(h_prn)
            win32print.EndDocPrinter(h_prn)
            win32print.ClosePrinter(h_prn)
            logger.info("Impressão concluída na tentativa %s", tentativa)
            return True, None
        except Exception as e:  # captura erros do win32print
            codigo = getattr(e, "winerror", -1)
            mensagem = getattr(e, "strerror", str(e))
            logger.warning(
                "Falha na tentativa %s de impressão: %s - %s",
                tentativa,
                codigo,
                mensagem,
            )
            if tentativa == max_tentativas:
                return False, {"code": codigo, "message": mensagem}
            atraso = 0.5 * (2 ** (tentativa - 1))
            time.sleep(atraso)


def imprimir_pagina_teste(
    repetir_em_falha: bool = False,
) -> tuple[bool, ErroImpressora | None]:
    """Imprime uma página de teste padrão.

    A etiqueta contém o logo, campos fictícios, numeração e uma régua de calibração.
    O layout utilizado é o mesmo da impressão normal das etiquetas.
    """

    layout = LAYOUT_ATUAL

    logo_path = recurso_caminho("logo.png")
    bitmap, largura_bytes, altura_px = melhorar_logo(
        logo_path, largura_desejada=layout.get("logo_largura", 240)
    )

    dots_x = LARGURA_ETIQUETA_MM * DOTS_MM
    dots_y = ALTURA_ETIQUETA_MM * DOTS_MM
    x_logo = _calc_logo_x(layout, dots_x, largura_bytes)

    # valida posições do layout
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
        if chave not in layout:
            return False, {
                "code": 0,
                "message": f"Layout incorreto: campo '{chave}' ausente.",
            }

    # régua horizontal para calibração (até 50 mm)
    ruler_start = layout["titulo"]["x"]
    ruler_y = dots_y - 40
    ruler_len = min(50 * DOTS_MM, dots_x - ruler_start)
    ruler_len -= ruler_len % (10 * DOTS_MM)  # múltiplos de 10 mm
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

            # --- monta pagina de teste ---
            cmd = (
                f"SIZE {LARGURA_ETIQUETA_MM} mm,{ALTURA_ETIQUETA_MM} mm\n"
                f"GAP {GAP_MM} mm,0\n"
                "DENSITY 8\n"
                "SPEED 4\n"
                "DIRECTION 1\n"
                "CLS\n"
            )
            cmd += t("titulo", "CONIMS")
            cmd += t("saida", "Saida: 000")
            cmd += t("categoria", "Categoria: TESTE")
            cmd += t("emissor", "Emissor: TESTE")
            cmd += t("municipio", "Municipio: TESTE")
            cmd += t("data", "Impresso em: 00/00/0000 00:00")
            cmd += t("fracao", "[ ] Fracao")
            cmd += t("fragil", "[ ] Fragil")

            # --- numeração teste ---
            if "numeracao_total" in layout:
                cmd += t("numeracao", "1")

                p_num = layout["numeracao"]
                p_tot = layout["numeracao_total"]  # type: ignore[index]
                follow = bool(p_tot.get("follow", True))  # type: ignore[call-arg]
                gap_mm = float(p_tot.get("gap_mm", 2.0))  # type: ignore[call-arg]

                if follow:
                    largura_num = _text_width_dots("1", p_num["font"], p_num["xm"])
                    x_de = int(p_num["x"] + largura_num + gap_mm * DOTS_MM)
                else:
                    x_de = int(p_tot.get("x", p_num["x"]))  # type: ignore[arg-type]

                y_de = int(p_tot.get("y", p_num["y"]))  # type: ignore[arg-type]
                cmd += (
                    f'TEXT {x_de},{y_de},"{p_tot["font"]}",0,{p_tot["xm"]},'
                    f'{p_tot["ym"]},"DE 1"\n'
                )
            else:
                cmd += t("numeracao", "1 DE 1")

            # --- logo ---
            cmd += (
                f"BITMAP {x_logo},{layout['logo_y']},{largura_bytes},"
                f"{altura_px},0,"
            )

            # Régua (marcas a cada 10 mm)
            barras = f"BAR {ruler_start},{ruler_y},{ruler_len},4\n"
            marcas = ruler_len // (10 * DOTS_MM)
            for i in range(marcas + 1):
                altura = 20 if i in (0, marcas) else 12
                x = ruler_start + i * 10 * DOTS_MM
                y = ruler_y - altura
                barras += f"BAR {x},{y},2,{altura}\n"

            logger.debug("tspl_first_200=%r", cmd[:200])
            corpo = (
                cmd.encode(ENCODING, errors="replace")
                + bitmap
                + f"\n{barras}PRINT 1\n".encode(ENCODING)
            )
            win32print.WritePrinter(h_prn, corpo)

            win32print.EndPagePrinter(h_prn)
            win32print.EndDocPrinter(h_prn)
            win32print.ClosePrinter(h_prn)
            logger.info("Impressão concluída na tentativa %s", tentativa)
            return True, None
        except Exception as e:  # captura erros do win32print
            codigo = getattr(e, "winerror", -1)
            mensagem = getattr(e, "strerror", str(e))
            logger.warning(
                "Falha na tentativa %s de impressão: %s - %s",
                tentativa,
                codigo,
                mensagem,
            )
            if tentativa == max_tentativas:
                return False, {"code": codigo, "message": mensagem}
            atraso = 0.5 * (2 ** (tentativa - 1))
            time.sleep(atraso)
