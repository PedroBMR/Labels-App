"""Rotinas relacionadas ao envio de comandos TSPL.

Responsabilidade:
    Enviar dados para impressoras térmicas utilizando ``win32print``.

Dependências:
    - win32print
    - log
    - persistence
    - layout_builder

Exemplo:
    >>> from layout_builder import LAYOUT_ATUAL, montar_tspl
    >>> from printing import imprimir_etiqueta
    >>> tspl = montar_tspl(LAYOUT_ATUAL, {})
    >>> imprimir_etiqueta(tspl)
"""

import time
from typing import TypedDict

import win32print

from log import logger
from persistence import carregar_config, salvar_config
import layout_builder as lb
from layout_builder import ENCODING


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


def _enviar_tspl(tspl: str, repetir_em_falha: bool = False) -> tuple[bool, ErroImpressora | None]:
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


def imprimir_etiqueta(tspl: str, repetir_em_falha: bool = False) -> tuple[bool, ErroImpressora | None]:
    """Envia uma string TSPL já montada para a impressora padrão."""
    return _enviar_tspl(tspl, repetir_em_falha)


def imprimir_pagina_teste(repetir_em_falha: bool = False) -> tuple[bool, ErroImpressora | None]:
    """Imprime uma página de teste padrão."""
    try:
        tspl = lb.montar_pagina_teste_tspl(lb.LAYOUT_ATUAL)
    except ValueError as e:
        return False, {"code": 0, "message": str(e)}
    return _enviar_tspl(tspl, repetir_em_falha)
