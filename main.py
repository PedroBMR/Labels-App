"""Ponto de entrada do aplicativo de geração de etiquetas."""

import os
import sys

from PyQt5.QtWidgets import QApplication

from _version import __version__
from ui import EtiquetaApp
from log import logger
from utils import migrate_legacy_data


def ensure_version_file() -> None:
    """Garante a criação do arquivo de versão.

    Cria ou atualiza ``version.txt`` no diretório do executável quando o
    aplicativo está congelado ou no diretório do arquivo em ambiente de
    desenvolvimento.

    Returns:
        None
    """

    try:
        if getattr(sys, "frozen", False):
            # Caminho do executável gerado pelo PyInstaller.
            install_dir = os.path.dirname(sys.executable)
        else:
            # Caminho dos arquivos .py em ambiente de desenvolvimento.
            install_dir = os.path.dirname(os.path.abspath(__file__))

        path = os.path.join(install_dir, "version.txt")
        with open(path, "w", encoding="utf-8") as arquivo:
            arquivo.write(str(__version__))
    except Exception:
        # Não interrompe a inicialização; apenas registra o problema.
        logger.exception("Falha ao gravar version.txt")


if __name__ == "__main__":
    try:
        logger.info("Aplicação iniciada")
        # 1) migra dados do legado para assets (uma vez só)
        migrate_legacy_data()

        # 2) segue o fluxo normal do app
        app = QApplication(sys.argv)

        # garante que version.txt existe/está atualizado
        ensure_version_file()

        janela = EtiquetaApp()
        # defina o título ANTES de mostrar a janela
        janela.setWindowTitle(f"Gerador de Etiquetas — v{__version__}")
        janela.show()

        # entra no loop da UI (bloqueia até fechar)
        sys.exit(app.exec_())

    except Exception:
        # Loga qualquer falha inesperada
        logger.exception("Crash fatal")
