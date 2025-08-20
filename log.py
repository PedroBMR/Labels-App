"""Ferramentas de logging da aplicação.

Responsabilidade:
    Configurar logging rotativo e integração com a interface.

Dependências:
    - logging
    - utils._base_dir

Exemplo:
    >>> from log import logger
    >>> logger.info("Iniciado")
"""

import logging
import os
import threading
from logging.handlers import RotatingFileHandler
from typing import Callable

from utils import _base_dir

LOG_DIR = os.path.join(_base_dir(), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOG_DIR, "app.log")
TSPL_LOG_FILE = os.path.join(LOG_DIR, "tspl.log")


# --- configuração base ----------------------------------------------------
def _create_file_handler(formatter: logging.Formatter) -> logging.Handler:
    handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=1_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(formatter)
    return handler


class _TsplFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:  # pragma: no cover - simples
        return record.module == "printing"


def _create_tspl_handler(formatter: logging.Formatter) -> logging.Handler:
    handler = RotatingFileHandler(
        TSPL_LOG_FILE,
        maxBytes=1_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(formatter)
    handler.addFilter(_TsplFilter())
    return handler


logger = logging.getLogger("app")
_DEBUG = os.getenv("DEBUG", "").lower() in {"1", "true", "yes"}
logger.setLevel(logging.DEBUG if _DEBUG else logging.INFO)

_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
logger.addHandler(_create_file_handler(_formatter))
logger.addHandler(_create_tspl_handler(_formatter))

if _DEBUG:
    console = logging.StreamHandler()
    console.setFormatter(_formatter)
    logger.addHandler(console)


def _thread_excepthook(args: threading.ExceptHookArgs) -> None:
    logger.exception(
        "Exceção não tratada em thread",
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
    )


threading.excepthook = _thread_excepthook


# --- integração com UI -----------------------------------------------------
_status_cb: Callable[[str], None] | None = None


class _StatusHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - simples
        if _status_cb:
            try:
                msg = self.format(record)
                _status_cb(msg)
            except Exception:
                pass


def register_status_callback(callback: Callable[[str], None]) -> None:
    """Registra ``callback`` chamado para mensagens de erro.

    A função será executada sempre que o logger emitir mensagens com nível
    ``ERROR`` ou superior. Útil para atualizar a ``status_label`` da interface
    gráfica de forma centralizada.
    """

    global _status_cb
    _status_cb = callback

    for h in logger.handlers:
        if isinstance(h, _StatusHandler):
            return

    handler = _StatusHandler(level=logging.ERROR)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)

