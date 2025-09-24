"""High level printing helpers built on top of :mod:`compile` backends."""

from __future__ import annotations

import copy
import importlib
import json
import logging
import socket
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol

from compile import Calibration, CompilationError, get_backend
from model.template import TemplateDocument, TemplateValidationError
from utils import recurso_caminho

# Retained for backwards compatibility with legacy code/tests that relied on
# the constant when performing manual conversions.
DOTS_MM: int = 8

DEFAULT_VARIABLES: dict[str, Any] = {
    "titulo": "CONIMS",
    "saida": "",
    "categoria": "",
    "emissor": "",
    "municipio": "",
    "data": "",
    "data_hora": "",
    "fracao": "[ ] Fracao",
    "fragil": "[ ] Fragil",
    "numero": 1,
    "total": 1,
}

DEFAULT_TEMPLATES: dict[str, dict[str, Any]] = {
    "100x30": {
        "backend": "tspl",
        "width_mm": 100,
        "height_mm": 30,
        "gap_mm": 2,
        "direction": 1,
        "elements": [
            {"type": "text", "x_mm": 4, "y_mm": 4, "font": {"name": "3", "x": 1, "y": 1}, "content": "{titulo}"},
            {"type": "text", "x_mm": 4, "y_mm": 9, "font": {"name": "2", "x": 1, "y": 1}, "content": "Saida: {saida}"},
            {"type": "text", "x_mm": 4, "y_mm": 13, "font": {"name": "2", "x": 1, "y": 1}, "content": "Categoria: {categoria}"},
            {"type": "text", "x_mm": 4, "y_mm": 17, "font": {"name": "2", "x": 1, "y": 1}, "content": "Emissor: {emissor}"},
            {"type": "text", "x_mm": 4, "y_mm": 21, "font": {"name": "2", "x": 1, "y": 1}, "content": "Municipio: {municipio}"},
            {"type": "text", "x_mm": 4, "y_mm": 25, "font": {"name": "2", "x": 1, "y": 1}, "content": "Impresso em: {data_hora}"},
            {"type": "text", "x_mm": 4, "y_mm": 27.5, "font": {"name": "2", "x": 1, "y": 1}, "content": "{fracao}"},
            {"type": "text", "x_mm": 60, "y_mm": 27.5, "font": {"name": "2", "x": 1, "y": 1}, "content": "{fragil}"},
            {"type": "text", "x_mm": 68, "y_mm": 6, "font": {"name": "5", "x": 1, "y": 1}, "content": "{numero} DE {total}"},
            {"type": "image", "x_mm": 70, "y_mm": 16, "key": "logo", "max_width_mm": 24, "max_height_mm": 12},
        ],
    },
    "60x80": {
        "backend": "tspl",
        "width_mm": 60,
        "height_mm": 80,
        "gap_mm": 2,
        "direction": 0,
        "elements": [
            {"type": "text", "x_mm": 4, "y_mm": 6, "font": {"name": "3", "x": 1, "y": 1}, "content": "{titulo}"},
            {"type": "text", "x_mm": 4, "y_mm": 14, "font": {"name": "2", "x": 1, "y": 1}, "content": "Saida: {saida}"},
            {"type": "text", "x_mm": 4, "y_mm": 19, "font": {"name": "2", "x": 1, "y": 1}, "content": "Categoria: {categoria}"},
            {"type": "text", "x_mm": 4, "y_mm": 24, "font": {"name": "2", "x": 1, "y": 1}, "content": "Emissor: {emissor}"},
            {"type": "text", "x_mm": 4, "y_mm": 29, "font": {"name": "2", "x": 1, "y": 1}, "content": "Municipio: {municipio}"},
            {"type": "text", "x_mm": 4, "y_mm": 34, "font": {"name": "2", "x": 1, "y": 1}, "content": "Impresso em: {data_hora}"},
            {"type": "text", "x_mm": 4, "y_mm": 39, "font": {"name": "2", "x": 1, "y": 1}, "content": "{fracao}"},
            {"type": "text", "x_mm": 28, "y_mm": 39, "font": {"name": "2", "x": 1, "y": 1}, "content": "{fragil}"},
            {"type": "text", "x_mm": 18, "y_mm": 46, "font": {"name": "5", "x": 1, "y": 1}, "content": "{numero} DE {total}"},
            {"type": "image", "x_mm": 10, "y_mm": 58, "key": "logo", "max_width_mm": 40, "max_height_mm": 18},
        ],
    },
}

ALIASES: dict[str, str] = {"padrao": "100x30", "padrão": "100x30"}
CALIBRATION_SQUARE_MM = 50.0


def _norm_key(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return value.strip().lower()


def _default_logo() -> str | None:
    try:
        return recurso_caminho("logo.png")
    except Exception:
        return None


def combine_calibrations(*calibrations: Calibration | None) -> Calibration:
    scale_x = 1.0
    scale_y = 1.0
    for cal in calibrations:
        if not cal:
            continue
        scale_x *= cal.scale_x
        scale_y *= cal.scale_y
    return Calibration(scale_x=scale_x, scale_y=scale_y)


@dataclass
class Template:
    """Wrapper around :class:`model.template.TemplateDocument`."""

    document: TemplateDocument
    calibration: Calibration = field(default_factory=Calibration)

    @property
    def name(self) -> str:
        return self.document.name

    @property
    def data(self) -> dict[str, Any]:
        return self.document.as_backend_dict()

    def clone(self) -> "Template":
        return Template(self.document.copy(), self.calibration)

    @property
    def backend(self) -> str:
        return self.document.backend

    @property
    def width_mm(self) -> float:
        return float(self.document.page.get("width_mm", 0))

    @property
    def height_mm(self) -> float:
        return float(self.document.page.get("height_mm", 0))

    @property
    def gap_mm(self) -> float:
        return float(self.document.page.get("gap_mm", 0))

    def with_calibration(self, calibration: Calibration) -> "Template":
        return Template(self.document.copy(), calibration)


class TemplateManager:
    def __init__(self, directory: Path | None = None) -> None:
        self._directory = directory
        self._cache: dict[str, Template] | None = None

    @property
    def directory(self) -> Path:
        if self._directory is None:
            self._directory = Path(recurso_caminho("templates"))
        self._directory.mkdir(parents=True, exist_ok=True)
        return self._directory

    def reload(self) -> None:
        self._cache = None

    def list_names(self) -> list[str]:
        return sorted(self._templates().keys())

    def get_template(self, name: str) -> Template:
        templates = self._templates()
        if not templates:
            raise RuntimeError("Nenhum template disponível")
        resolved = self._resolve_name(name, templates)
        return templates[resolved].clone()

    # ------------------------------------------------------------------
    def _templates(self) -> dict[str, Template]:
        if self._cache is not None:
            return self._cache

        documents: dict[str, TemplateDocument] = {}
        self._migrate_legacy()
        logger = logging.getLogger("app")

        for path in sorted(self.directory.glob("*.json")):
            try:
                document = TemplateDocument.from_file(path)
            except Exception:  # pragma: no cover - defensive
                logger.exception("Falha ao carregar template: %s", path)
                continue
            documents[document.name] = document

        if not documents:
            for name, legacy in DEFAULT_TEMPLATES.items():
                documents[name] = TemplateDocument.from_legacy(name, legacy, defaults=DEFAULT_VARIABLES)

        self._cache = {name: Template(doc) for name, doc in documents.items()}
        return self._cache

    def _migrate_legacy(self) -> None:
        legacy_path = Path(recurso_caminho("templates.json"))
        if not legacy_path.exists():
            return

        try:
            with legacy_path.open("r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except Exception:  # pragma: no cover - defensive
            logging.getLogger("app").exception("Falha ao migrar templates.json")
            return

        if not isinstance(raw, dict):
            return

        for name, spec in raw.items():
            if not isinstance(spec, Mapping):
                continue
            document = TemplateDocument.from_legacy(name, spec, defaults=DEFAULT_VARIABLES)
            target = self.directory / f"{document.slug}.json"
            if target.exists():
                continue
            try:
                document.dump(target)
            except OSError:  # pragma: no cover - depends on filesystem
                logging.getLogger("app").exception("Falha ao gravar template migrado: %s", target)

    def _resolve_name(self, name: str, templates: Mapping[str, Template]) -> str:
        if name in templates:
            return name
        norm = _norm_key(name)
        for key in templates:
            if _norm_key(key) == norm:
                return key
        if norm in ALIASES:
            alias = ALIASES[norm]
            if alias in templates:
                return alias
        return next(iter(templates))


template_manager = TemplateManager()


def listar_templates() -> list[str]:
    return template_manager.list_names()


def recarregar_templates() -> None:
    template_manager.reload()


def aplicar_template(nome: str) -> Template:
    return template_manager.get_template(nome)


def build_label_series(
    dados: Mapping[str, Any],
    template: Template | TemplateDocument | None = None,
) -> list[dict[str, Any]]:
    volumes = max(1, int(dados.get("volumes", 1)))
    inicio = int(dados.get("inicio_indice", 1))
    total = int(dados.get("total_exibicao") or volumes)

    defaults = dict(DEFAULT_VARIABLES)
    if isinstance(template, TemplateDocument):
        defaults.update(template.defaults(scope="item"))
    elif isinstance(template, Template):
        defaults.update(template.document.defaults(scope="item"))

    base = dict(defaults)
    base.update({k: dados.get(k, base.get(k)) for k in defaults})
    base.update({k: dados.get(k) for k in dados if k not in base})

    logo = dados.get("logo") or _default_logo()
    if logo:
        base["logo"] = logo

    series: list[dict[str, Any]] = []
    for offset in range(volumes):
        numero = inicio + offset
        ctx = dict(base)
        ctx.update(
            {
                "numero": numero,
                "indice": numero,
                "volume": offset + 1,
                "total": total,
                "total_exibicao": total,
            }
        )
        series.append(ctx)
    return series


def compile_template(
    template: Template | TemplateDocument | Mapping[str, Any],
    variables: Mapping[str, Any],
    *,
    backend_name: str | None = None,
    calibration: Calibration | None = None,
) -> tuple[str, str]:
    try:
        if isinstance(template, Template):
            template.document.ensure_valid(variables)
            combined = combine_calibrations(template.calibration, calibration)
            backend = backend_name or template.backend
            template_data = template.data
        elif isinstance(template, TemplateDocument):
            template.ensure_valid(variables)
            combined = calibration or Calibration()
            backend = backend_name or template.backend
            template_data = template.as_backend_dict()
        else:
            combined = calibration or Calibration()
            template_data = dict(template)
            backend = backend_name or str(template_data.get("backend", "tspl"))
    except TemplateValidationError as exc:
        raise CompilationError(str(exc)) from exc
    backend = backend or "tspl"
    compiler = get_backend(backend, template_data, calibration=combined)
    return backend, compiler.compile(variables)


def montar_tspl(template: Template, dados: Mapping[str, Any]) -> str:
    variables = template.document.defaults(scope="template")
    variables["items"] = build_label_series(dados, template)
    _, commands = compile_template(template, variables, backend_name="tspl")
    return commands


def montar_zpl(template: Template, dados: Mapping[str, Any]) -> str:
    variables = template.document.defaults(scope="template")
    variables["items"] = build_label_series(dados, template)
    _, commands = compile_template(template, variables, backend_name="zpl")
    return commands


class Transport(Protocol):
    def send(self, payload: bytes) -> None:  # pragma: no cover - protocol definition
        ...


class TransportError(RuntimeError):
    def __init__(self, message: str, *, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code if code is not None else -1


class WindowsSpoolerTransport:
    def __init__(self, printer_name: str | None = None) -> None:
        self.printer_name = printer_name

    def _resolve_printer(self) -> str:
        name = self.printer_name or descobrir_impressora_padrao()
        if not name:
            raise TransportError("Nenhuma impressora padrão configurada", code=0)
        return name

    def send(self, payload: bytes) -> None:  # pragma: no cover - requires Windows
        name = self._resolve_printer()
        try:
            win32print = _get_win32print()
            handle = win32print.OpenPrinter(name)
            try:
                win32print.StartDocPrinter(handle, 1, ("Etiqueta", None, "RAW"))
                win32print.StartPagePrinter(handle)
                win32print.WritePrinter(handle, payload)
                win32print.EndPagePrinter(handle)
                win32print.EndDocPrinter(handle)
            finally:
                win32print.ClosePrinter(handle)
        except Exception as exc:  # pragma: no cover - Windows only
            code = getattr(exc, "winerror", getattr(exc, "errno", -1))
            raise TransportError(str(exc), code=code) from exc


class TcpTransport:
    def __init__(self, host: str, port: int = 9100, *, timeout: float = 10.0) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout

    def send(self, payload: bytes) -> None:
        try:
            with socket.create_connection((self.host, self.port), self.timeout) as sock:
                sock.sendall(payload)
        except OSError as exc:
            raise TransportError(str(exc), code=getattr(exc, "errno", -1)) from exc


class CUPSTransport:
    def __init__(self, printer_name: str | None = None) -> None:
        try:
            import cups  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise TransportError("Modulo CUPS indisponivel") from exc

        self._conn = cups.Connection()
        default = self._conn.getDefault()
        self.printer_name = printer_name or default
        if not self.printer_name:
            raise TransportError("Nenhuma impressora CUPS configurada")

    def send(self, payload: bytes) -> None:  # pragma: no cover - depends on CUPS
        try:
            self._conn.printData(self.printer_name, payload, "Etiqueta", {})
        except RuntimeError as exc:
            raise TransportError(str(exc)) from exc


_win32_module: Any | None = None


def _get_win32print():  # pragma: no cover - Windows only
    global _win32_module
    if _win32_module is None:
        _win32_module = importlib.import_module("win32print")
    return _win32_module


def descobrir_impressora_padrao() -> str | None:
    try:
        win32print = _get_win32print()
    except Exception:  # pragma: no cover - not on Windows
        return None
    try:
        return win32print.GetDefaultPrinter()  # type: ignore[attr-defined]
    except Exception:
        return None


def listar_impressoras() -> list[str]:
    try:
        win32print = _get_win32print()
    except Exception:  # pragma: no cover - not on Windows
        return []

    try:
        flags = getattr(win32print, "PRINTER_ENUM_LOCAL", 2) | getattr(
            win32print, "PRINTER_ENUM_CONNECTIONS", 4
        )
        entries = win32print.EnumPrinters(flags)
    except Exception:  # pragma: no cover - Windows specific failure
        entries = []

    nomes: list[str] = []
    for entry in entries or []:
        nome: str | None = None
        if isinstance(entry, (list, tuple)) and len(entry) >= 3:
            maybe = entry[2]
            if isinstance(maybe, str):
                nome = maybe
        elif isinstance(entry, dict):
            nome = entry.get("pPrinterName") or entry.get("Name")
        elif isinstance(entry, str):
            nome = entry
        if nome:
            nomes.append(nome)

    padrao = descobrir_impressora_padrao()
    if padrao and padrao not in nomes:
        nomes.append(padrao)
    # remove duplicatas mantendo ordem
    vistos: set[str] = set()
    resultado: list[str] = []
    for nome in nomes:
        if nome not in vistos:
            resultado.append(nome)
            vistos.add(nome)
    return resultado


@dataclass
class PrinterConfig:
    backend: str = "tspl"
    transport: str = "win32"
    printer_name: str | None = None
    host: str | None = None
    port: int = 9100
    encoding: str | None = None
    calibration: Calibration = field(default_factory=Calibration)
    timeout: float = 10.0


class Printer:
    def __init__(self, config: PrinterConfig, *, logger: logging.Logger | None = None) -> None:
        self.config = config
        self.logger = logger or logging.getLogger("app")
        self.transport = self._make_transport()

    def _make_transport(self) -> Transport:
        mode = self.config.transport.lower()
        if mode == "win32":
            return WindowsSpoolerTransport(self.config.printer_name)
        if mode == "tcp":
            if not self.config.host:
                raise ValueError("TCP transport requer host")
            return TcpTransport(self.config.host, self.config.port, timeout=self.config.timeout)
        if mode == "cups":
            return CUPSTransport(self.config.printer_name)
        raise ValueError(f"Transporte desconhecido: {self.config.transport}")

    def compile_job(
        self, template: Template | Mapping[str, Any], variables: Mapping[str, Any]
    ) -> tuple[str, str]:
        backend_name, commands = compile_template(
            template,
            variables,
            backend_name=self.config.backend,
            calibration=self.config.calibration,
        )
        return backend_name, commands

    def send_commands(self, commands: str, *, backend: str | None = None) -> None:
        encoding = self.config.encoding
        backend = backend or self.config.backend
        if encoding is None:
            encoding = "cp1252" if backend.lower() == "tspl" else "utf-8"
        payload = commands.encode(encoding, errors="replace")
        self.transport.send(payload)

    def print_job(
        self, template: Template | Mapping[str, Any], variables: Mapping[str, Any]
    ) -> tuple[bool, dict | None]:
        try:
            backend_name, commands = self.compile_job(template, variables)
            self.send_commands(commands, backend=backend_name)
            return True, None
        except TransportError as exc:
            if self.logger:
                self.logger.error("Falha ao enviar comandos para impressora: %s", exc)
            return False, {"code": exc.code, "message": str(exc)}
        except CompilationError as exc:
            return False, {"code": -1, "message": str(exc)}

    def print_template(self, template: Template, dados: Mapping[str, Any]) -> tuple[bool, dict | None]:
        variables = template.document.defaults(scope="template")
        variables["items"] = build_label_series(dados, template)
        return self.print_job(template, variables)

    def print_calibration(
        self, *, backend: str | None = None, square_mm: float = CALIBRATION_SQUARE_MM
    ) -> tuple[bool, dict | None]:
        tpl = build_calibration_template(square_mm=square_mm, backend=backend or self.config.backend)
        return self.print_job(tpl, {})

    def apply_calibration(
        self,
        measured_width: float | None,
        measured_height: float | None,
        *,
        square_mm: float = CALIBRATION_SQUARE_MM,
    ) -> Calibration:
        new_cal = apply_calibration_adjustment(
            self.config.calibration, measured_width, measured_height, square_mm=square_mm
        )
        self.config.calibration = new_cal
        return new_cal


def build_calibration_template(
    *, square_mm: float = CALIBRATION_SQUARE_MM, backend: str | None = None
) -> Template:
    margem = max(5.0, square_mm * 0.2)
    page = {
        "backend": backend or "tspl",
        "width_mm": square_mm + margem * 2,
        "height_mm": square_mm + margem * 2,
        "gap_mm": 2,
    }
    elements = [
        {
            "type": "shape",
            "kind": "rect",
            "x_mm": margem,
            "y_mm": margem,
            "width_mm": square_mm,
            "height_mm": square_mm,
            "thickness_mm": 0.5,
        },
        {
            "type": "text",
            "x_mm": margem,
            "y_mm": margem + square_mm + 4,
            "font": {"name": "2", "x": 1, "y": 1},
            "content": f"{square_mm:.0f} mm",
        },
    ]
    document = TemplateDocument(
        name=f"calibration_{page['backend']}",
        page=page,
        elements=elements,
        variables={},
    )
    return Template(document)


def apply_calibration_adjustment(
    current: Calibration,
    measured_width: float | None,
    measured_height: float | None,
    *,
    square_mm: float = CALIBRATION_SQUARE_MM,
) -> Calibration:
    scale_x = current.scale_x
    scale_y = current.scale_y
    if measured_width and measured_width > 0:
        scale_x *= square_mm / measured_width
    if measured_height and measured_height > 0:
        scale_y *= square_mm / measured_height
    return Calibration(scale_x=scale_x, scale_y=scale_y)


def imprimir_etiqueta(
    commands: str,
    repetir_em_falha: bool = False,
    *,
    nome_impressora: str | None = None,
    logger: logging.Logger | None = None,
) -> tuple[bool, dict | None]:
    config = PrinterConfig(backend="tspl", transport="win32", printer_name=nome_impressora)
    printer = Printer(config, logger=logger)
    tentativas = 3 if repetir_em_falha else 1
    for tentativa in range(1, tentativas + 1):
        try:
            printer.send_commands(commands, backend="tspl")
            return True, None
        except TransportError as exc:
            if logger:
                logger.warning("Falha na tentativa %s: %s", tentativa, exc)
            if tentativa == tentativas:
                return False, {"code": exc.code, "message": str(exc)}
            time.sleep(0.5 * tentativa)


def imprimir_pagina_teste(
    template: Template,
    repetir_em_falha: bool = False,
    *,
    nome_impressora: str | None = None,
    logger: logging.Logger | None = None,
) -> tuple[bool, dict | None]:
    dados = {
        "saida": "000",
        "categoria": "TESTE",
        "emissor": "SISTEMA",
        "municipio": "TESTE",
        "data_hora": "00/00/0000 00:00",
        "volumes": 1,
    }
    config = PrinterConfig(backend="tspl", transport="win32", printer_name=nome_impressora)
    printer = Printer(config, logger=logger)
    return printer.print_template(template, dados)
