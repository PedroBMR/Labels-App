"""Rotinas relacionadas à impressão das etiquetas."""

from typing import TypedDict

import json
import time
import win32print

from utils import melhorar_logo, recurso_caminho
from log import logger
from persistence import carregar_config, salvar_config

DOTS_MM: int = 8  # ~203 dpi

# -------------------- templates --------------------
try:
    with open(recurso_caminho("templates.json"), "r", encoding="utf-8") as f:
        TEMPLATES: dict[str, dict[str, int]] = json.load(f)
except Exception:
    # Fallback para garantir funcionamento mesmo sem arquivo
    TEMPLATES = {
        "Padrão": {"largura_mm": 60, "altura_mm": 80, "gap_mm": 2}
    }


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


LAYOUTS: dict[str, Layout] = {
    "Padrão": {
        "titulo": {"x": 30, "y": 20, "font": "3", "xm": 2, "ym": 2},
        "saida": {"x": 30, "y": 70, "font": "2", "xm": 1, "ym": 1},
        "categoria": {"x": 30, "y": 90, "font": "2", "xm": 1, "ym": 1},
        "emissor": {"x": 30, "y": 120, "font": "2", "xm": 1, "ym": 1},
        "municipio": {"x": 30, "y": 150, "font": "2", "xm": 1, "ym": 1},
        "data": {"x": 30, "y": 180, "font": "2", "xm": 1, "ym": 1},
        "fracao": {"x": 30, "y": 220, "font": "2", "xm": 1, "ym": 1},
        "fragil": {"x": 30, "y": 270, "font": "2", "xm": 1, "ym": 1},
        "numeracao": {"x": 30, "y": 330, "font": "4", "xm": 2, "ym": 2},
        "logo_y": 450,
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
    },
    "Panoramico": {
        "titulo": {"x": 20, "y": 20, "font": "2", "xm": 1, "ym": 1},
        "saida": {"x": 20, "y": 60, "font": "1", "xm": 1, "ym": 1},
        "categoria": {"x": 20, "y": 90, "font": "1", "xm": 1, "ym": 1},
        "emissor": {"x": 20, "y": 120, "font": "1", "xm": 1, "ym": 1},
        "municipio": {"x": 20, "y": 150, "font": "1", "xm": 1, "ym": 1},
        "data": {"x": 20, "y": 180, "font": "1", "xm": 1, "ym": 1},
        "fracao": {"x": 420, "y": 60, "font": "1", "xm": 1, "ym": 1},
        "fragil": {"x": 420, "y": 90, "font": "1", "xm": 1, "ym": 1},
        "numeracao": {"x": 420, "y": 180, "font": "2", "xm": 1, "ym": 1},
        "logo_y": 120,
    },
}

LARGURA_ETIQUETA_MM: int = 60
ALTURA_ETIQUETA_MM: int = 80
GAP_MM: int = 2
LAYOUT_ATUAL: Layout = LAYOUTS["Padrão"]


def listar_templates() -> list[str]:
    """Retorna a lista de nomes de templates disponíveis."""

    return list(TEMPLATES.keys())


def aplicar_template(nome: str) -> None:
    """Define qual template será utilizado nas impressões."""

    modelo = TEMPLATES.get(nome)
    if not modelo:
        nome = list(TEMPLATES.keys())[0]
        modelo = TEMPLATES[nome]
    global LARGURA_ETIQUETA_MM, ALTURA_ETIQUETA_MM, GAP_MM, LAYOUT_ATUAL
    LARGURA_ETIQUETA_MM = int(modelo.get("largura_mm", 60))
    ALTURA_ETIQUETA_MM = int(modelo.get("altura_mm", 80))
    GAP_MM = int(modelo.get("gap_mm", 2))
    LAYOUT_ATUAL = LAYOUTS.get(nome, LAYOUTS[list(LAYOUTS.keys())[0]])


# aplica template padrão ao importar módulo
aplicar_template("Padrão")


class ErroImpressora(TypedDict):
    code: int
    message: str


def descobrir_impressora_padrao() -> str | None:
    """Retorna o nome da impressora configurada ou a padrão do sistema."""

    try:
        config = carregar_config()
        nome = config.get("ultima_impressora")
        if nome:
            try:
                handle = win32print.OpenPrinter(nome)
                win32print.ClosePrinter(handle)
                return str(nome)
            except Exception:
                pass
        nome = win32print.GetDefaultPrinter()
        config["ultima_impressora"] = nome
        salvar_config(config)
        return nome
    except Exception:  # pragma: no cover - ambientes sem win32
        return None


def imprimir_etiqueta(
    saida: str,
    categoria: str,
    emissor: str,
    municipio: str,
    volumes: int,
    data_hora: str,
    contagem_total: int = 0,
    contagem_mensal: int = 0,
    inicio_indice: int = 1,
    total_exibicao: int | None = None,
    repetir_em_falha: bool = False,
) -> tuple[bool, ErroImpressora | None]:
    """Monta e envia comandos TSPL para a impressora padrão.

    Retorna ``(True, None)`` em caso de sucesso ou ``(False, erro)`` quando
    ocorrer algum problema, contendo código e mensagem da falha.
    """

    # -------- prepara logo --------
    logo_path = recurso_caminho("logo.png")
    bitmap, largura_bytes, altura_px = melhorar_logo(logo_path, largura_desejada=240)

    dots_x = LARGURA_ETIQUETA_MM * DOTS_MM
    x_logo = (dots_x - (largura_bytes * 8)) // 2  # centraliza logo

    # Total exibido no rodapé
    if total_exibicao is None:
        total_exibicao = volumes

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

            layout = LAYOUT_ATUAL

            def t(chave: str, texto: str) -> str:
                p = layout[chave]
                return (
                    f'TEXT {p["x"]},{p["y"]},"{p["font"]}",0,'
                    f'{p["xm"]},{p["ym"]},"{texto}"\n'
                )

            # -------- monta e imprime etiquetas ----------
            for offset in range(volumes):
                numero_atual = inicio_indice + offset  # ex.: 7,8,9,10
                cmd = (
                    f"SIZE {LARGURA_ETIQUETA_MM} mm,{ALTURA_ETIQUETA_MM} mm\n"
                    f"GAP {GAP_MM} mm,0 mm\n"
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
                cmd += t("numeracao", f"{numero_atual} DE {total_exibicao}")
                cmd += (
                    f"BITMAP {x_logo},{layout['logo_y']},{largura_bytes},{altura_px},0,"
                )
                corpo = cmd.encode() + bitmap + b"\nPRINT 1\n"
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


def imprimir_pagina_teste(
    repetir_em_falha: bool = False,
) -> tuple[bool, ErroImpressora | None]:
    """Imprime uma página de teste padrão.

    A etiqueta contém o logo, campos fictícios, numeração ``1 DE 1`` e uma
    régua horizontal de 50 mm para calibração da impressora.
    """

    logo_path = recurso_caminho("logo.png")
    bitmap, largura_bytes, altura_px = melhorar_logo(logo_path, largura_desejada=240)

    dots_x = LARGURA_ETIQUETA_MM * DOTS_MM
    x_logo = (dots_x - (largura_bytes * 8)) // 2

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

            # --- monta pagina de teste ---
            cmd = (
                f"SIZE {LARGURA_ETIQUETA_MM} mm,{ALTURA_ETIQUETA_MM} mm\n"
                f"GAP {GAP_MM} mm,0 mm\n"
                "CLS\n"
                'TEXT 30,  20,"3",0,2,2,"CONIMS"\n'
                'TEXT 30,  70,"2",0,1,1,"Saída: 000"\n'
                'TEXT 30,  90,"2",0,1,1,"Categoria: TESTE"\n'
                'TEXT 30, 120,"2",0,1,1,"Emissor: TESTE"\n'
                'TEXT 30, 150,"2",0,1,1,"Município: TESTE"\n'
                'TEXT 30, 180,"2",0,1,1,"Impresso em: 00/00/0000 00:00"\n'
                'TEXT 30, 330,"4",0,2,2,"1 DE 1"\n'
                f"BITMAP {x_logo},450,{largura_bytes},{altura_px},0,"
            )

            # Régua de 50 mm para calibração
            ruler_start = 30
            ruler_y = 600
            ruler_len = 50 * DOTS_MM
            barras = f"BAR {ruler_start},{ruler_y},{ruler_len},4\n"
            for i in range(6):  # marcas a cada 10 mm
                altura = 20 if i in (0, 5) else 12
                x = ruler_start + i * 10 * DOTS_MM
                y = ruler_y - altura
                barras += f"BAR {x},{y},2,{altura}\n"

            corpo = cmd.encode() + bitmap + f"\n{barras}PRINT 1\n".encode()
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
