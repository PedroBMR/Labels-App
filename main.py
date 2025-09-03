"""Ponto de entrada do aplicativo de geração de etiquetas.

Responsabilidade:
    Inicializar a aplicação e capturar falhas desde o início.

Dependências:
    - _version
    - log
    - qt_compat
    - ui
    - utils.migrate_legacy_data

Exemplo:
    $ python main.py
"""

# =========================
# PREÂMBULO: captura de crash ANTES de qualquer import pesado
# =========================
import atexit
import faulthandler
import os
import signal
import sys
import time
import traceback
from datetime import datetime

BOOT_START = time.perf_counter()

# Diretório do script (funciona no .py e também com PyInstaller em desenvolvimento)
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Pasta de logs ao lado do script (sem depender de log.py ainda)
_LOG_DIR = os.path.join(_BASE_DIR, "logs")
os.makedirs(_LOG_DIR, exist_ok=True)

# Arquivo de stderr/crash ultra-cedo
_EARLY_CRASH_FILE = os.path.join(_LOG_DIR, "crash_stderr.log")

# Abrimos o stream com flush por linha
_EARLY_CRASH_STREAM = open(
    _EARLY_CRASH_FILE,
    "a",
    buffering=1,
    encoding="utf-8",
    errors="replace",
)

# Banner de boot (útil para saber se esse preâmbulo rodou)
_EARLY_CRASH_STREAM.write(
    f"\n=== BOOT {datetime.now().isoformat(timespec='seconds')} ===\n"
)

# Redireciona stdout/err para capturar qualquer print/traceback de import
sys.stdout = _EARLY_CRASH_STREAM  # type: ignore[assignment]
sys.stderr = _EARLY_CRASH_STREAM  # type: ignore[assignment]

# Exceções não tratadas durante import ou runtime
def _early_excepthook(exc_type, exc, tb):
    _EARLY_CRASH_STREAM.write("\n=== UNHANDLED EXCEPTION (EARLY) ===\n")
    traceback.print_exception(exc_type, exc, tb, file=_EARLY_CRASH_STREAM)
    _EARLY_CRASH_STREAM.flush()

sys.excepthook = _early_excepthook

# Habilita faulthandler para dumps de threads em sinais/crashes nativos
try:
    faulthandler.enable(_EARLY_CRASH_STREAM, all_threads=True)  # type: ignore[arg-type]
except Exception:
    faulthandler.enable(all_threads=True)

# Registra sinais comuns (nem todos existem no Windows, mas não faz mal checar)
for _sig in (getattr(signal, "SIGSEGV", None),
             getattr(signal, "SIGABRT", None),
             getattr(signal, "SIGILL", None),
             getattr(signal, "SIGFPE", None)):
    if _sig is not None:
        try:
            faulthandler.register(_sig, file=_EARLY_CRASH_STREAM, all_threads=True)  # type: ignore[arg-type]
        except Exception:
            pass

@atexit.register
def _early_close_stream():
    try:
        _EARLY_CRASH_STREAM.flush()
        # Não fechamos aqui se for reaproveitado mais tarde; fechar no atexit final
    except Exception:
        pass


# =========================
# IMPORTS reais do app (depois do preâmbulo)
# =========================
import logging  # noqa: E402

from _version import __version__  # noqa: E402
from log import LOG_FILE, enable_file_logging, logger, boot_logging  # noqa: E402
from qt_compat import (  # noqa: E402
    QApplication,
    QThread,
    QtMsgType,
    qInstallMessageHandler,
)
from ui import EtiquetaApp  # noqa: E402
from utils import migrate_legacy_data  # noqa: E402

# =========================
# Captura "oficial" (integra com logger e Qt)
# =========================
_CRASH_STREAM = _EARLY_CRASH_STREAM  # reaproveitamos o arquivo aberto no preâmbulo
_CRASH_FILE = _EARLY_CRASH_FILE

def _setup_crash_capture() -> None:
    """Integra captura com LOG_FILE e mensagens do Qt."""
    global _CRASH_STREAM, _CRASH_FILE

    # Se existir LOG_FILE, apenas garanta que a pasta existe (mantemos o
    # mesmo crash_stderr.log)
    try:
        if LOG_FILE:
            os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    except Exception:
        pass

    # Exceções não tratadas → logger + arquivo de crash
    def _excepthook(exc_type, exc, tb):
        try:
            logger.exception("UNHANDLED EXCEPTION", exc_info=(exc_type, exc, tb))
        except Exception:
            pass
        try:
            _CRASH_STREAM.write("\n=== UNHANDLED EXCEPTION ===\n")  # type: ignore[union-attr]
            traceback.print_exception(exc_type, exc, tb, file=_CRASH_STREAM)  # type: ignore[arg-type]
            _CRASH_STREAM.flush()  # type: ignore[union-attr]
        except Exception:
            pass

    sys.excepthook = _excepthook

    # Mensagens do Qt → log + arquivo de crash
    def _qt_message_handler(mode, context, message):
        try:
            prefix = {
                QtMsgType.QtDebugMsg:   "QT-DEBUG",
                QtMsgType.QtInfoMsg:    "QT-INFO",
                QtMsgType.QtWarningMsg: "QT-WARN",
                QtMsgType.QtCriticalMsg:"QT-ERROR",
                QtMsgType.QtFatalMsg:   "QT-FATAL",
            }.get(mode, "QT-MSG")

            _CRASH_STREAM.write(f"{prefix}: {message}\n")  # type: ignore[union-attr]
            _CRASH_STREAM.flush()  # type: ignore[union-attr]

            if mode == QtMsgType.QtDebugMsg:
                logger.debug(message)
            elif mode == QtMsgType.QtInfoMsg:
                logger.info(message)
            elif mode == QtMsgType.QtWarningMsg:
                logger.warning(message)
            elif mode == QtMsgType.QtCriticalMsg:
                logger.error(message)
            elif mode == QtMsgType.QtFatalMsg:
                logger.critical(message)
        except Exception:
            pass

        if mode == QtMsgType.QtFatalMsg:
            try:
                _CRASH_STREAM.flush()  # type: ignore[union-attr]
            except Exception:
                pass
            os._exit(1)

    qInstallMessageHandler(_qt_message_handler)

    @atexit.register
    def _final_close_stream():
        try:
            if _CRASH_STREAM and not _CRASH_STREAM.closed:  # type: ignore[union-attr]
                _CRASH_STREAM.flush()  # type: ignore[union-attr]
                _CRASH_STREAM.close()  # type: ignore[union-attr]
        except Exception:
            pass


def ensure_version_file() -> None:
    """Garante a criação do arquivo de versão (version.txt) ao lado do
    executável/código."""
    try:
        if getattr(sys, "frozen", False):
            install_dir = os.path.dirname(sys.executable)  # PyInstaller
        else:
            install_dir = os.path.dirname(os.path.abspath(__file__))

        path = os.path.join(install_dir, "version.txt")
        with open(path, "w", encoding="utf-8") as arquivo:
            arquivo.write(str(__version__))
    except Exception:
        # Não interrompe a inicialização; apenas registra o problema.
        logger.exception("Falha ao gravar version.txt")


class _PyWin32Preload(QThread):
    """Pre-importa módulos pywin32 sem bloquear o thread principal."""

    def run(self) -> None:  # noqa: D401 - método do QThread
        import importlib

        try:
            importlib.import_module("win32print")
            importlib.import_module("win32api")
        except Exception:
            # Ignore falhas em sistemas que não sejam Windows ou sem pywin32
            pass


if __name__ == "__main__":
    with boot_logging():
        logger.info("Boot: após imports %.3fs", time.perf_counter() - BOOT_START)
        # Liga a captura "oficial" (Qt + excepthook + integra com logger)
        _setup_crash_capture()

        try:
            logger.info("Aplicação iniciada (v%s)", __version__)
            # 1) Migra dados do legado para assets (uma vez só)
            migrate_legacy_data()

            # 2) Cria a aplicação Qt
            app = QApplication(sys.argv)

            # Garante que version.txt existe/está atualizado
            ensure_version_file()

            # 3) Janela principal
            def _patch_printer():
                _orig_verificar = EtiquetaApp._verificar_impressora
                _printer_logged = False
                def _verificar_wrapper(self):
                    nonlocal _printer_logged
                    _orig_verificar(self)
                    if not _printer_logged:
                        logger.info(
                            "Boot: após verificar impressora %.3fs",
                            time.perf_counter() - BOOT_START,
                        )
                        _printer_logged = True
                EtiquetaApp._verificar_impressora = _verificar_wrapper
            _patch_printer()

            janela = EtiquetaApp()
            janela.setWindowTitle(f"Gerador de Etiquetas — v{__version__}")
            janela.show()
            janela._pywin32_preload = _PyWin32Preload()
            janela._pywin32_preload.finished.connect(janela._pywin32_preload.deleteLater)
            janela._pywin32_preload.start()
            logger.info("Boot: após criar UI %.3fs", time.perf_counter() - BOOT_START)
            enable_file_logging()
            if os.getenv("DEBUG", "").lower() in {"1", "true", "yes"}:
                logger.setLevel(logging.DEBUG)

            # 4) Entra no loop da UI
            # exec_ was renamed to exec in Qt6 / PySide6; use getattr for compatibility
            sys.exit(getattr(app, "exec", app.exec_)())

        except Exception:
            # Loga qualquer falha inesperada; também vai para crash_stderr.log via
            # excepthook
            logger.exception("Crash fatal na thread principal")
            try:
                _CRASH_STREAM.write("\n=== MAIN EXCEPTION ===\n")  # type: ignore[union-attr]
                traceback.print_exc(file=_CRASH_STREAM)  # type: ignore[arg-type]
                _CRASH_STREAM.flush()  # type: ignore[union-attr]
            except Exception:
                pass
            raise
