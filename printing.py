"""Rotinas relacionadas à impressão das etiquetas."""

from typing import TypedDict

import time
import win32print

from utils import melhorar_logo, recurso_caminho
from log import logger

LARGURA_ETIQUETA_MM: int = 60
ALTURA_ETIQUETA_MM: int = 80
DOTS_MM: int = 8  # ~203 dpi


class ErroImpressora(TypedDict):
    code: int
    message: str


def descobrir_impressora_padrao() -> str | None:
    """Retorna o nome da impressora padrão ou ``None`` se não houver.

    Captura quaisquer exceções vindas do ``win32print`` e devolve ``None``
    para indicar ausência ou erro ao obter a impressora.
    """

    try:
        return win32print.GetDefaultPrinter()
    except Exception:  # pragma: no cover - apenas em ambientes sem win32
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

            # -------- monta e imprime etiquetas ----------
            for offset in range(volumes):
                numero_atual = inicio_indice + offset  # ex.: 7,8,9,10
                cmd = (
                    f"SIZE {LARGURA_ETIQUETA_MM} mm,{ALTURA_ETIQUETA_MM} mm\n"
                    "GAP 2 mm,0 mm\n"
                    "CLS\n"
                    'TEXT 30,  20,"3",0,2,2,"CONIMS"\n'
                    'TEXT 30,  70,"2",0,1,1,"Saida: {saida}"\n'
                    'TEXT 30,  90,"2",0,1,1,"Categoria: {categoria}"\n'
                    'TEXT 30, 120,"2",0,1,1,"Emissor: {emissor}"\n'
                    'TEXT 30, 150,"2",0,1,1,"Municipio: {municipio}"\n'
                    'TEXT 30, 180,"2",0,1,1,"Impresso em: {data_hora}"\n'
                    'TEXT 30, 220,"2",0,1,1,"[ ] Fracao"\n'
                    'TEXT 30, 270,"2",0,1,1,"[ ] Fragil"\n'
                    'TEXT 30, 330,"4",0,2,2,"{i} DE {volumes_total}"\n'
                    f"BITMAP {x_logo},450,{largura_bytes},{altura_px},0,"
                )
                cmd = cmd.format(
                    saida=saida,
                    categoria=categoria,
                    emissor=emissor,
                    municipio=municipio,
                    data_hora=data_hora,
                    i=numero_atual,
                    volumes_total=total_exibicao,
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
