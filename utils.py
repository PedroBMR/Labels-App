"""Funções utilitárias utilizadas pelo aplicativo."""

import os
import shutil
import sys
from datetime import datetime

from PIL import Image

def _base_dir() -> str:
    """Obtém o diretório base do aplicativo.

    Returns:
        str: Caminho do diretório base.
    """

    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

def recurso_caminho(rel_path: str) -> str:
    """Constroi caminho absoluto para um recurso em ``assets``.

    Args:
        rel_path (str): Caminho relativo dentro de ``assets``.

    Returns:
        str: Caminho absoluto para o recurso.
    """

    return os.path.join(_base_dir(), "assets", rel_path)

def melhorar_logo(path_logo: str, largura_desejada: int = 160) -> tuple[bytes, int, int]:
    """Converte a logo para bitmap monocromático TSPL.

    Args:
        path_logo (str): Caminho para a imagem da logo.
        largura_desejada (int, optional): Largura final desejada. Padrão 160.

    Returns:
        tuple[bytes, int, int]: Dados do bitmap, largura em bytes e altura em pixels.
    """

    logo = Image.open(path_logo).convert("L")  # escala de cinza
    proporcao = largura_desejada / logo.width
    nova_altura = int(round(logo.height * proporcao))

    # Redimensiona com alta qualidade
    logo = logo.resize((largura_desejada, nova_altura), resample=Image.LANCZOS)

    # Binarização/dithering
    logo_bw = logo.convert("1", dither=Image.FLOYDSTEINBERG)

    largura_em_bytes = largura_desejada // 8
    pixels = logo_bw.load()

    bitmap_data = bytearray()
    for y in range(logo_bw.height):
        for x_byte in range(largura_em_bytes):
            byte = 0
            for b in range(8):
                x = x_byte * 8 + b
                if x < logo_bw.width and pixels[x, y] == 0:
                    byte |= (1 << (7 - b))
            bitmap_data.append(byte)

    # >>> importante: retornar bytes, não bytearray, para concatenar com b"..."
    return bytes(bitmap_data), largura_em_bytes, logo_bw.height

def backup_automatico() -> None:
    """Realiza cópia de segurança dos arquivos de dados."""

    base = _base_dir()
    origem = os.path.join(base, "assets")
    destino = os.path.join(base, "_backup")
    os.makedirs(destino, exist_ok=True)
    agora = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    arquivos = ["historico_impressoes.csv", "contagem.json", "contagem_mensal.json"]
    for arq in arquivos:
        orig = os.path.join(origem, arq)
        if os.path.exists(orig):
            nome_backup = f"{arq.replace('.', f'_{agora}.')}"
            shutil.copy2(orig, os.path.join(destino, nome_backup))


def _install_dir() -> str:
    """Retorna o diretório de instalação do aplicativo."""

    return (
        os.path.dirname(sys.executable)
        if getattr(sys, "frozen", False)
        else os.path.dirname(os.path.abspath(__file__))
    )

def migrate_legacy_data() -> None:
    """Migra arquivos legados para a nova estrutura de ``assets``."""

    base = _install_dir()
    old_dir = os.path.join(base, "_internal")
    new_dir = os.path.join(base, "assets")

    if not os.path.isdir(old_dir):
        return  # nada pra migrar

    os.makedirs(new_dir, exist_ok=True)

    # arquivos que nos interessam
    arquivos = [
        "historico_impressoes.csv",
        "contagem.json",
        "contagem_mensal.json",
        "logo.png", "color.png", "color.ico",
    ]

    for nome in arquivos:
        origem = os.path.join(old_dir, nome)
        destino = os.path.join(new_dir, nome)
        if os.path.exists(origem) and not os.path.exists(destino):
            try:
                shutil.copy2(origem, destino)
            except Exception:
                pass

    # renomeia _internal para um backup (se der)
    try:
        stamp = datetime.now().strftime("%Y%m%d_%H%M")
        os.rename(old_dir, os.path.join(base, f"_internal.bak-{stamp}"))
    except Exception:
        pass
