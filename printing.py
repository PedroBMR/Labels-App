# printing.py
import win32print
from datetime import datetime
from utils import recurso_caminho, melhorar_logo

LARGURA_ETIQUETA_MM = 60
ALTURA_ETIQUETA_MM = 80
DOTS_MM = 8  # ~203 dpi

def imprimir_etiqueta(
    saida, categoria, emissor, municipio, volumes, data_hora,
    contagem_total=0, contagem_mensal=0,
    inicio_indice: int = 1,           # <-- NOVO: inicia numeração em N
    total_exibicao: int = None        # <-- NOVO: total mostrado em "X DE Y"
):
    """
    Monta e envia o comando TSPL para a impressora padrão.
    Retorna True se ok, senão gera exceção.
    """
    # -------- prepara logo --------
    logo_path = recurso_caminho("logo.png")
    bitmap, largura_bytes, altura_px = melhorar_logo(logo_path, largura_desejada=240)

    dots_x = LARGURA_ETIQUETA_MM * DOTS_MM
    x_logo = (dots_x - (largura_bytes * 8)) // 2  # centraliza logo

    # Total exibido no rodapé
    if total_exibicao is None:
        total_exibicao = volumes

    # -------- abre impressora --------
    nome_imp = win32print.GetDefaultPrinter()
    h_prn = win32print.OpenPrinter(nome_imp)
    h_job = win32print.StartDocPrinter(h_prn, 1, ("Etiqueta CONIMS", None, "RAW"))
    win32print.StartPagePrinter(h_prn)

    # -------- monta e imprime etiquetas ----------
    # agora imprimimos 'volumes' etiquetas, numerando a partir de 'inicio_indice'
    for offset in range(volumes):
        numero_atual = inicio_indice + offset  # ex.: 7,8,9,10
        cmd = (
            f"SIZE {LARGURA_ETIQUETA_MM} mm,{ALTURA_ETIQUETA_MM} mm\n"
            "GAP 2 mm,0 mm\n"
            "CLS\n"
            "TEXT 30,  20,\"3\",0,2,2,\"CONIMS\"\n"
            "TEXT 30,  70,\"2\",0,1,1,\"Saida: {saida}\"\n"
            "TEXT 30,  90,\"2\",0,1,1,\"Categoria: {categoria}\"\n"
            "TEXT 30, 120,\"2\",0,1,1,\"Emissor: {emissor}\"\n"
            "TEXT 30, 150,\"2\",0,1,1,\"Municipio: {municipio}\"\n"
            "TEXT 30, 180,\"2\",0,1,1,\"Impresso em: {data_hora}\"\n"
            "TEXT 30, 220,\"2\",0,1,1,\"[ ] Fracao\"\n"
            "TEXT 30, 270,\"2\",0,1,1,\"[ ] Fragil\"\n"
            "TEXT 30, 330,\"4\",0,2,2,\"{i} DE {volumes_total}\"\n"
            f"BITMAP {x_logo},450,{largura_bytes},{altura_px},0,"
        )
        cmd = cmd.format(
            saida=saida,
            categoria=categoria,
            emissor=emissor,
            municipio=municipio,
            data_hora=data_hora,
            i=numero_atual,
            volumes_total=total_exibicao
        )
        corpo = cmd.encode() + bitmap + b"\nPRINT 1\n"
        win32print.WritePrinter(h_prn, corpo)

    # -------- Finaliza impressão --------
    win32print.EndPagePrinter(h_prn)
    win32print.EndDocPrinter(h_prn)
    win32print.ClosePrinter(h_prn)
    return True
