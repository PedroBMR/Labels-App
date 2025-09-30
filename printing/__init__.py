"""High level printing helpers built on top of :mod:`compile` backends."""

from __future__ import annotations

import base64
import csv
import hashlib
import importlib
import io
import json
import logging
import re
import socket
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from PIL import Image

from compile import Calibration, CompilationError, SafeDict, get_backend
from db import store as db_store
from fonts import font_store
from model.template import TemplateDocument, TemplateValidationError
from persistence import carregar_config, salvar_config
from render import PreviewRenderer
from utils import recurso_caminho
from utils.fs import canonical_path as canonical_file_path

from .queue import PrinterTarget, enqueue_job

# ----------------------------------------------------------------------------

LOGGER = logging.getLogger(__name__)

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
            {
                "type": "text",
                "x_mm": 4,
                "y_mm": 4,
                "font": {"name": "3", "x": 1, "y": 1},
                "content": "{titulo}",
            },
            {
                "type": "text",
                "x_mm": 4,
                "y_mm": 9,
                "font": {"name": "2", "x": 1, "y": 1},
                "content": "Saida: {saida}",
            },
            {
                "type": "text",
                "x_mm": 4,
                "y_mm": 13,
                "font": {"name": "2", "x": 1, "y": 1},
                "content": "Categoria: {categoria}",
            },
            {
                "type": "text",
                "x_mm": 4,
                "y_mm": 17,
                "font": {"name": "2", "x": 1, "y": 1},
                "content": "Emissor: {emissor}",
            },
            {
                "type": "text",
                "x_mm": 4,
                "y_mm": 21,
                "font": {"name": "2", "x": 1, "y": 1},
                "content": "Municipio: {municipio}",
            },
            {
                "type": "text",
                "x_mm": 4,
                "y_mm": 25,
                "font": {"name": "2", "x": 1, "y": 1},
                "content": "Impresso em: {data_hora}",
            },
            {
                "type": "text",
                "x_mm": 4,
                "y_mm": 27.5,
                "font": {"name": "2", "x": 1, "y": 1},
                "content": "{fracao}",
            },
            {
                "type": "text",
                "x_mm": 60,
                "y_mm": 27.5,
                "font": {"name": "2", "x": 1, "y": 1},
                "content": "{fragil}",
            },
            {
                "type": "text",
                "x_mm": 68,
                "y_mm": 6,
                "font": {"name": "5", "x": 1, "y": 1},
                "content": "{numero} DE {total}",
            },
            {
                "type": "image",
                "x_mm": 70,
                "y_mm": 16,
                "key": "logo",
                "max_width_mm": 24,
                "max_height_mm": 12,
            },
        ],
    },
    "60x80": {
        "backend": "tspl",
        "width_mm": 60,
        "height_mm": 80,
        "gap_mm": 2,
        "direction": 0,
        "elements": [
            {
                "type": "text",
                "x_mm": 4,
                "y_mm": 6,
                "font": {"name": "3", "x": 1, "y": 1},
                "content": "{titulo}",
            },
            {
                "type": "text",
                "x_mm": 4,
                "y_mm": 14,
                "font": {"name": "2", "x": 1, "y": 1},
                "content": "Saida: {saida}",
            },
            {
                "type": "text",
                "x_mm": 4,
                "y_mm": 19,
                "font": {"name": "2", "x": 1, "y": 1},
                "content": "Categoria: {categoria}",
            },
            {
                "type": "text",
                "x_mm": 4,
                "y_mm": 24,
                "font": {"name": "2", "x": 1, "y": 1},
                "content": "Emissor: {emissor}",
            },
            {
                "type": "text",
                "x_mm": 4,
                "y_mm": 29,
                "font": {"name": "2", "x": 1, "y": 1},
                "content": "Municipio: {municipio}",
            },
            {
                "type": "text",
                "x_mm": 4,
                "y_mm": 34,
                "font": {"name": "2", "x": 1, "y": 1},
                "content": "Impresso em: {data_hora}",
            },
            {
                "type": "text",
                "x_mm": 4,
                "y_mm": 39,
                "font": {"name": "2", "x": 1, "y": 1},
                "content": "{fracao}",
            },
            {
                "type": "text",
                "x_mm": 28,
                "y_mm": 39,
                "font": {"name": "2", "x": 1, "y": 1},
                "content": "{fragil}",
            },
            {
                "type": "text",
                "x_mm": 18,
                "y_mm": 46,
                "font": {"name": "5", "x": 1, "y": 1},
                "content": "{numero} DE {total}",
            },
            {
                "type": "image",
                "x_mm": 10,
                "y_mm": 58,
                "key": "logo",
                "max_width_mm": 40,
                "max_height_mm": 18,
            },
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


_NON_WORD_RE = re.compile(r"[^0-9a-zA-Z_]+")


def _normalise_header(name: str) -> str:
    value = unicodedata.normalize("NFKD", name or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.replace("-", "_").replace(" ", "_")
    value = _NON_WORD_RE.sub("_", value)
    value = value.strip("_")
    return value.lower()


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

    def with_page_overrides(self, overrides: Mapping[str, Any]) -> "Template":
        document = self.document.copy()
        document.page.update(dict(overrides))
        return Template(document, self.calibration)

    def with_calibration(self, calibration: Calibration) -> "Template":
        return Template(self.document.copy(), calibration)


def _prepare_payload(
    commands: bytes | str,
    backend: str,
    encoding: str | None,
) -> bytes:
    """Encode ``commands`` into bytes using transport defaults."""

    if isinstance(commands, str):
        codec = encoding
        if not codec:
            codec = "cp1252" if backend.lower() == "tspl" else "utf-8"
        return commands.encode(codec, errors="replace")
    return bytes(commands)


def resolve_media_settings(
    config: Mapping[str, Any],
    printer_profile: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Extract media related settings from ``config`` and an optional profile."""

    profile = printer_profile if isinstance(printer_profile, Mapping) else None

    def _profile_value(*keys: str) -> Any:
        if not profile:
            return None
        for key in keys:
            if key in profile:
                value = profile[key]
                if value in (None, ""):
                    continue
                return value
        return None

    def _config_value(*keys: str) -> Any:
        for key in keys:
            if key in config:
                value = config[key]
                if value in (None, ""):
                    continue
                return value
        return None

    def _coerce_float(value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _coerce_positive_int(value: Any) -> int | None:
        try:
            if value in (None, "", False):
                return None
            number = int(float(value))
        except (TypeError, ValueError):
            return None
        return number if number > 0 else None

    def _coerce_bool(value: Any) -> bool | None:
        if value in (None, ""):
            return None
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"1", "true", "yes", "on"}:
                return True
            if lowered in {"0", "false", "no", "off"}:
                return False
        return bool(value)

    media_raw = _profile_value("media_type") or _config_value("media_type") or "gap"
    media_raw = str(media_raw).strip().lower()
    media_type = (
        "black_mark"
        if media_raw in {"mark", "black", "black_mark", "black-mark", "blackmark"}
        else "gap"
    )

    gap_candidate = _profile_value("gap_mm", "media_gap_mm")
    if gap_candidate is None:
        gap_candidate = _config_value("media_gap_mm", "gap_mm")
    gap_mm = _coerce_float(gap_candidate)
    if gap_mm is None:
        gap_mm = 0.0

    gap_offset_candidate = _profile_value(
        "gap_offset_mm",
        "media_gap_offset_mm",
        "media_offset_mm",
    )
    if gap_offset_candidate is None:
        gap_offset_candidate = _config_value(
            "media_gap_offset_mm", "media_offset_mm"
        )
    gap_offset = _coerce_float(gap_offset_candidate)
    if gap_offset is None:
        gap_offset = 0.0

    mark_candidate = _profile_value("mark_mm", "media_mark_mm")
    if mark_candidate is None:
        mark_candidate = _config_value("media_mark_mm")
    mark_mm = _coerce_float(mark_candidate)
    if mark_mm is None:
        mark_mm = gap_mm

    mark_offset_candidate = _profile_value(
        "mark_offset_mm", "media_mark_offset_mm"
    )
    if mark_offset_candidate is None:
        mark_offset_candidate = _config_value("media_mark_offset_mm")
    mark_offset = _coerce_float(mark_offset_candidate)
    if mark_offset is None:
        mark_offset = gap_offset

    fine_offset_candidate = _profile_value(
        "fine_offset_mm", "media_fine_offset_mm"
    )
    if fine_offset_candidate is None:
        fine_offset_candidate = _config_value("media_fine_offset_mm")
    fine_offset = _coerce_float(fine_offset_candidate)
    if fine_offset is None:
        fine_offset = 0.0

    profile_calibrate = _coerce_bool(
        _profile_value("calibrate_next", "calibrate_next_print", "media_calibrate_next")
    )
    if profile_calibrate is None:
        calibrate = bool(_coerce_bool(_config_value("media_calibrate_next")))
    else:
        calibrate = profile_calibrate

    speed_candidate = _profile_value("media_speed", "speed")
    if speed_candidate is None:
        speed_candidate = _config_value("media_speed", "speed")
    speed = _coerce_positive_int(speed_candidate)

    darkness_candidate = _profile_value("media_darkness", "darkness")
    if darkness_candidate is None:
        darkness_candidate = _config_value("media_darkness", "density", "darkness")
    darkness = _coerce_positive_int(darkness_candidate)

    raw_print_rate = _profile_value("media_print_rate", "print_rate")
    if raw_print_rate in (None, "", 0, 0.0):
        raw_print_rate = _config_value("media_print_rate", "print_rate", "print_speed")
    if raw_print_rate in (None, "", 0, 0.0):
        print_rate = str(speed) if speed is not None else None
    else:
        print_rate = str(raw_print_rate)

    return {
        "media_type": media_type,
        "gap_mm": gap_mm,
        "gap_offset_mm": gap_offset,
        "mark_mm": mark_mm,
        "mark_offset_mm": mark_offset,
        "fine_offset_mm": fine_offset,
        "calibrate_next_print": bool(calibrate),
        "speed": speed,
        "density": darkness,
        "darkness": darkness,
        "print_rate": print_rate,
    }


def apply_media_settings(template: Template, settings: Mapping[str, Any]) -> Template:
    """Return a copy of ``template`` with ``settings`` applied to the page."""

    document = template.document.copy()
    page = document.page

    media_type = str(
        settings.get("media_type", page.get("media_type", "gap"))
    ).lower()
    media_type = (
        "black_mark"
        if media_type in {"black_mark", "blackmark", "mark"}
        else "gap"
    )
    page["media_type"] = media_type

    def _coerce(key: str, default: float = 0.0) -> float:
        value = settings.get(key, page.get(key, default))
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    gap_mm = _coerce("gap_mm", float(page.get("gap_mm", 0.0)))
    gap_offset = _coerce("gap_offset_mm", float(page.get("gap_offset_mm", 0.0)))
    mark_mm = _coerce(
        "mark_mm",
        float(page.get("mark_mm", page.get("black_mark_mm", gap_mm))),
    )
    mark_offset = _coerce(
        "mark_offset_mm",
        float(page.get("mark_offset_mm", page.get("black_mark_offset_mm", gap_offset))),
    )
    fine_offset = _coerce("fine_offset_mm", float(page.get("fine_offset_mm", 0.0)))

    page["gap_mm"] = gap_mm
    page["gap_offset_mm"] = gap_offset
    page["mark_mm"] = mark_mm
    page["mark_offset_mm"] = mark_offset
    page["black_mark_mm"] = mark_mm
    page["black_mark_offset_mm"] = mark_offset
    page["fine_offset_mm"] = fine_offset

    def _coerce_int(key: str) -> int | None:
        value = settings.get(key, page.get(key))
        try:
            if value in (None, "", False):
                return None
            number = int(float(value))
        except (TypeError, ValueError):
            return None
        return number if number > 0 else None

    speed = _coerce_int("speed")
    if speed is None:
        speed = _coerce_int("media_speed")
    if speed is not None:
        page["speed"] = speed
    else:
        page.pop("speed", None)

    density = _coerce_int("density")
    if density is None:
        density = _coerce_int("darkness")
    if density is None:
        density = _coerce_int("media_darkness")
    if density is not None:
        page["density"] = density
        page["darkness"] = density
    else:
        page.pop("density", None)
        page.pop("darkness", None)

    print_rate = settings.get("print_rate") or page.get("print_rate")
    if not print_rate:
        print_rate = settings.get("media_print_rate")
    if not print_rate and speed is not None:
        print_rate = str(speed)
    if isinstance(print_rate, (int, float)):
        print_rate = str(int(print_rate))
    elif isinstance(print_rate, str):
        print_rate = print_rate.strip()
    else:
        print_rate = None

    if print_rate:
        page["print_rate"] = print_rate
        page["print_speed"] = print_rate
    else:
        page.pop("print_rate", None)
        page.pop("print_speed", None)

    page["calibrate_next_print"] = bool(settings.get("calibrate_next_print"))

    return Template(document, template.calibration)


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
                documents[name] = TemplateDocument.from_legacy(
                    name,
                    legacy,
                    defaults=DEFAULT_VARIABLES,
                )

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
            document = TemplateDocument.from_legacy(
                name,
                spec,
                defaults=DEFAULT_VARIABLES,
            )
            target = self.directory / f"{document.slug}.json"
            if target.exists():
                continue
            try:
                canonical = canonical_file_path(target)
                document.dump(canonical, canonical_path=canonical)
            except OSError:  # pragma: no cover - depends on filesystem
                logging.getLogger("app").exception(
                    "Falha ao gravar template migrado: %s",
                    target,
                )

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


def load_csv_items(
    path: str | Path,
    *,
    delimiter: str = ",",
    encoding: str = "utf-8",
) -> list[dict[str, Any]]:
    """Return a list of row dictionaries parsed from ``path``."""

    arquivo = Path(path)
    if not arquivo.exists():
        raise FileNotFoundError(str(path))

    with arquivo.open("r", encoding=encoding, newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        if reader.fieldnames is None:
            return []

        items: list[dict[str, Any]] = []
        for row in reader:
            entry: dict[str, Any] = {}
            for raw_key, raw_value in row.items():
                if raw_key is None:
                    continue
                key = str(raw_key).strip()
                if not key:
                    continue
                value = raw_value.strip() if isinstance(raw_value, str) else raw_value
                entry[key] = value
                normalised = _normalise_header(key)
                if normalised and normalised not in entry:
                    entry[normalised] = value
                upper = normalised.upper()
                if upper and upper not in entry:
                    entry[upper] = value
            if entry:
                items.append(entry)
        return items


def build_label_series(
    dados: Mapping[str, Any],
    template: Template | TemplateDocument | None = None,
) -> list[dict[str, Any]]:
    defaults = dict(DEFAULT_VARIABLES)
    if isinstance(template, TemplateDocument):
        defaults.update(template.defaults(scope="item"))
    elif isinstance(template, Template):
        defaults.update(template.document.defaults(scope="item"))

    base = dict(defaults)
    for key in defaults:
        if key in dados:
            base[key] = dados.get(key, base.get(key))
    for key, value in dados.items():
        if key not in base and key != "items":
            base[key] = value

    logo = dados.get("logo") or _default_logo()
    if logo:
        base["logo"] = logo

    items_override = dados.get("items")
    if isinstance(items_override, list) and items_override:
        inicio = int(dados.get("inicio_indice", 1))
        try:
            total_override = int(dados.get("total_exibicao"))
        except (TypeError, ValueError):
            total_override = len(items_override)
        total = total_override if total_override > 0 else len(items_override)
        series: list[dict[str, Any]] = []
        for offset, item in enumerate(items_override):
            ctx = dict(base)
            mapping: Mapping[str, Any]
            if isinstance(item, Mapping):
                mapping = item
            elif hasattr(item, "items"):
                mapping = dict(item.items())  # type: ignore[assignment]
            else:
                mapping = {"value": item}
            ctx.update(mapping)
            numero = inicio + offset
            has_item_numero = isinstance(mapping, Mapping) and "numero" in mapping
            if not has_item_numero and ctx.get("numero") == defaults.get("numero"):
                ctx["numero"] = numero
            else:
                ctx.setdefault("numero", numero)
            ctx.setdefault("indice", numero)
            ctx.setdefault("volume", offset + 1)
            has_item_total = isinstance(mapping, Mapping) and "total" in mapping
            if not has_item_total and "total" not in dados:
                ctx["total"] = total
            else:
                ctx.setdefault("total", total)
            ctx.setdefault("total_exibicao", total)
            series.append(ctx)
        return series

    volumes = max(1, int(dados.get("volumes", 1)))
    inicio = int(dados.get("inicio_indice", 1))
    total = int(dados.get("total_exibicao") or volumes)

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


def prepare_variable_contexts(
    template: Template | TemplateDocument,
    dados: Mapping[str, Any],
) -> list[SafeDict]:
    if isinstance(template, Template):
        document = template.document
    elif isinstance(template, TemplateDocument):
        document = template
    else:  # pragma: no cover - defensive
        raise TypeError("template deve ser Template ou TemplateDocument")

    base = document.defaults(scope="template")
    for key, value in dados.items():
        if key == "items":
            continue
        base[key] = value

    items = build_label_series(dados, template)
    if not items:
        return [SafeDict(dict(base))]

    contexts: list[SafeDict] = []
    for item in items:
        ctx = SafeDict(dict(base))
        ctx.update(item)
        contexts.append(ctx)
    return contexts


def render_label_images(
    template: Template,
    dados: Mapping[str, Any],
    *,
    media_settings: Mapping[str, Any] | None = None,
) -> list[Image.Image]:
    working = template
    if media_settings:
        working = apply_media_settings(template, media_settings)
    contexts = prepare_variable_contexts(working, dados)
    renderer = PreviewRenderer(
        working.document.page,
        calibration=combine_calibrations(working.calibration),
        metadata=working.document.metadata,
    )
    return [renderer.render(working.document.elements, ctx) for ctx in contexts]


def _write_png(image: Image.Image, destino: Path) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    image.convert("L").save(destino, format="PNG")
    return destino


def _write_pdf(images: list[Image.Image], destino: Path) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    primary = images[0].convert("RGB")
    extras = [img.convert("RGB") for img in images[1:]]
    primary.save(destino, format="PDF", save_all=bool(extras), append_images=extras)
    return destino


def _write_svg(image: Image.Image, destino: Path) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    payload = base64.b64encode(buffer.getvalue()).decode("ascii")
    width, height = image.size
    svg = (
        "<svg xmlns=\"http://www.w3.org/2000/svg\" "
        "xmlns:xlink=\"http://www.w3.org/1999/xlink\" "
        f"width=\"{width}\" height=\"{height}\" "
        f"viewBox=\"0 0 {width} {height}\">"
        f"<image width=\"{width}\" height=\"{height}\" "
        f"preserveAspectRatio=\"none\" xlink:href=\"data:image/png;base64,{payload}\"/>"
        "</svg>"
    )
    destino.write_text(svg, encoding="utf-8")
    return destino


def export_labels(
    template: Template,
    dados: Mapping[str, Any],
    destino: str | Path,
    formato: str,
    *,
    media_settings: Mapping[str, Any] | None = None,
    batch: bool = False,
) -> tuple[list[Path], int]:
    images = render_label_images(template, dados, media_settings=media_settings)
    if not images:
        raise ValueError("Nenhuma etiqueta foi gerada para exportação")

    formato_normalizado = formato.lower()
    if formato_normalizado not in {"png", "pdf", "svg"}:
        raise ValueError(f"Formato de exportação inválido: {formato}")

    destino_path = Path(destino)
    if destino_path.suffix.lower() != f".{formato_normalizado}":
        destino_path = destino_path.with_suffix(f".{formato_normalizado}")

    saved: list[Path] = []
    total = len(images)

    if batch and total > 1 and formato_normalizado in {"png", "svg"}:
        for indice, imagem in enumerate(images, start=1):
            sufixo = f"-{indice:03d}"
            target = destino_path.with_name(
                destino_path.stem + sufixo + destino_path.suffix
            )
            if formato_normalizado == "png":
                saved.append(_write_png(imagem, target))
            else:
                saved.append(_write_svg(imagem, target))
    elif formato_normalizado == "pdf" and (batch and total > 1):
        saved.append(_write_pdf(images, destino_path))
    else:
        image = images[0]
        if formato_normalizado == "png":
            saved.append(_write_png(image, destino_path))
        elif formato_normalizado == "pdf":
            saved.append(_write_pdf([image], destino_path))
        else:
            saved.append(_write_svg(image, destino_path))

    return saved, total


def compile_template(
    template: Template | TemplateDocument | Mapping[str, Any],
    variables: Mapping[str, Any],
    *,
    backend_name: str | None = None,
    calibration: Calibration | None = None,
    strict: bool = True,
) -> tuple[str, bytes]:
    try:
        if isinstance(template, Template):
            if strict:
                template.document.ensure_valid(variables)
            combined = combine_calibrations(template.calibration, calibration)
            backend = backend_name or template.backend
            template_data = template.data
        elif isinstance(template, TemplateDocument):
            if strict:
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
    metadata = template_data.get("metadata")
    if isinstance(metadata, Mapping):
        fonts_metadata = metadata.get("fonts")
        if isinstance(fonts_metadata, Mapping):
            font_store.register_metadata(fonts_metadata)
    compiler = get_backend(backend, template_data, calibration=combined)
    commands = compiler.compile(variables)
    if isinstance(commands, str):
        commands_bytes = commands.encode("ascii", errors="replace")
    else:
        commands_bytes = bytes(commands)
    return backend, commands_bytes


def _prepare_quick_variables(
    template: Template,
    overrides: Mapping[str, Any] | None,
    *,
    silent: bool,
) -> dict[str, Any]:
    base = template.document.defaults(scope="template")
    variables: dict[str, Any] = dict(base)

    data = dict(overrides or {})
    items_override = data.pop("items", None)
    variables.update(data)

    raw_copies = variables.get("copies")
    try:
        copies = int(raw_copies)
    except (TypeError, ValueError):
        copies = 1
    if copies < 1:
        copies = 1
    variables["copies"] = copies

    if isinstance(items_override, list) and items_override:
        defaults_item = template.document.defaults(scope="item")
        variables["items"] = [
            {
                **defaults_item,
                **entry,
            }
            if isinstance(entry, Mapping)
            else dict(defaults_item)
            for entry in items_override
        ]
    elif isinstance(items_override, Mapping):
        defaults_item = template.document.defaults(scope="item")
        merged = dict(defaults_item)
        merged.update(items_override)
        variables["items"] = [merged]
    elif silent:
        defaults_item = template.document.defaults(scope="item")
        if defaults_item:
            variables["items"] = [dict(defaults_item)]
        else:
            variables["items"] = [{}]

    return variables


def prepare_quick_job(
    model_name: str,
    overrides: Mapping[str, Any] | None = None,
    *,
    silent: bool = True,
    config: Mapping[str, Any] | None = None,
    printer_name: str | None = None,
    printer_profile: Mapping[str, Any] | None = None,
) -> tuple[Template, dict[str, Any]]:
    cfg = config or carregar_config()
    template = aplicar_template(model_name)

    profile = printer_profile if printer_profile is not None else None
    printer = printer_name
    if printer is None:
        hint = str(cfg.get("ultima_impressora", "")).strip()
        printer = hint or None
    if profile is None and printer:
        try:
            profile = db_store.load_printer_profile(printer)
        except Exception:  # pragma: no cover - defensive logging only
            LOGGER.exception("Falha ao carregar perfil da impressora %s", printer)
            profile = None

    media_settings = resolve_media_settings(cfg, printer_profile=profile)
    base_settings = dict(media_settings)
    base_settings["calibrate_next_print"] = False
    template = apply_media_settings(template, base_settings)
    variables = _prepare_quick_variables(template, overrides, silent=silent)
    return template, variables


def compile_model_silent(
    model_name: str,
    overrides: Mapping[str, Any] | None = None,
    *,
    silent: bool = True,
    printer_name: str | None = None,
    printer_profile: Mapping[str, Any] | None = None,
) -> bytes:
    cfg = carregar_config()

    profile = printer_profile if printer_profile is not None else None
    printer = printer_name
    if printer is None:
        hint = str(cfg.get("ultima_impressora", "")).strip()
        printer = hint or None
    if profile is None and printer:
        try:
            profile = db_store.load_printer_profile(printer)
        except Exception:  # pragma: no cover - defensive logging only
            LOGGER.exception("Falha ao carregar perfil da impressora %s", printer)
            profile = None

    template, variables = prepare_quick_job(
        model_name,
        overrides,
        silent=silent,
        config=cfg,
        printer_name=printer,
        printer_profile=profile,
    )
    media_settings = resolve_media_settings(cfg, printer_profile=profile)

    calibrate_from_profile = False
    if profile:
        raw_profile_flag = None
        for key in ("media_calibrate_next", "calibrate_next", "calibrate_next_print"):
            if key in profile:
                raw_profile_flag = profile[key]
                break
        calibrate_from_profile = bool(raw_profile_flag)

    if media_settings.get("calibrate_next_print"):
        if calibrate_from_profile and printer:
            try:
                db_store.save_printer_profile(
                    printer,
                    {"media_calibrate_next": False},
                )
            except Exception:  # pragma: no cover - defensive logging only
                LOGGER.exception(
                    "Falha ao atualizar calibracao da impressora %s", printer
                )
        else:
            cfg = dict(cfg)
            cfg["media_calibrate_next"] = False
            salvar_config(cfg)

    template = apply_media_settings(template, media_settings)
    backend, commands = compile_template(
        template,
        variables,
        strict=not silent,
    )
    return commands


def montar_tspl(
    template: Template,
    dados: Mapping[str, Any],
    media_settings: Mapping[str, Any] | None = None,
) -> bytes:
    working_template = template
    if media_settings:
        working_template = apply_media_settings(template, media_settings)
    variables = working_template.document.defaults(scope="template")
    variables["items"] = build_label_series(dados, working_template)
    _, commands = compile_template(working_template, variables, backend_name="tspl")
    return commands


def montar_zpl(
    template: Template,
    dados: Mapping[str, Any],
    media_settings: Mapping[str, Any] | None = None,
) -> bytes:
    working_template = template
    if media_settings:
        working_template = apply_media_settings(template, media_settings)
    variables = working_template.document.defaults(scope="template")
    variables["items"] = build_label_series(dados, working_template)
    _, commands = compile_template(working_template, variables, backend_name="zpl")
    return commands


class Transport(Protocol):
    def send(self, payload: bytes) -> None:  # pragma: no cover - protocol definition
        ...


class TransportError(RuntimeError):
    def __init__(self, message: str, *, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code if code is not None else -1


def _record_and_send(
    *,
    payload: bytes,
    payload_hash: str,
    template_name: str | None,
    template_backend: str | None,
    printer_name: str | None,
    printer_backend: str | None,
    printer_transport: str | None,
    media_settings: Mapping[str, Any] | None,
    send_callable: Callable[[bytes], None],
    logger: logging.Logger | None,
) -> tuple[bool, dict | None, int | None]:
    target = PrinterTarget(
        name=printer_name,
        backend=printer_backend,
        transport=printer_transport,
        send=send_callable,
        logger=logger,
    )
    params = {
        "payload_hash": payload_hash,
        "template_backend": template_backend,
        "printer_backend": printer_backend,
        "printer_transport": printer_transport,
        "media_settings": media_settings,
    }
    job_id, status = enqueue_job(
        template_name,
        payload,
        target,
        copies=1,
        params=params,
    )

    return True, {"status": status}, job_id


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
    def __init__(
        self,
        config: PrinterConfig,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self.config = config
        self.logger = logger or logging.getLogger("app")
        self.transport = self._make_transport()

    @staticmethod
    def _prepare_payload(
        commands: bytes | str,
        backend: str,
        encoding: str | None,
    ) -> bytes:
        return _prepare_payload(commands, backend, encoding)

    def _make_transport(self) -> Transport:
        mode = self.config.transport.lower()
        if mode == "win32":
            return WindowsSpoolerTransport(self.config.printer_name)
        if mode == "tcp":
            if not self.config.host:
                raise ValueError("TCP transport requer host")
            return TcpTransport(
                self.config.host,
                self.config.port,
                timeout=self.config.timeout,
            )
        if mode == "cups":
            return CUPSTransport(self.config.printer_name)
        raise ValueError(f"Transporte desconhecido: {self.config.transport}")

    def compile_job(
        self, template: Template | Mapping[str, Any], variables: Mapping[str, Any]
    ) -> tuple[str, bytes]:
        backend_name, commands = compile_template(
            template,
            variables,
            backend_name=self.config.backend,
            calibration=self.config.calibration,
        )
        return backend_name, commands

    def send_commands(
        self,
        commands: bytes | str,
        *,
        backend: str | None = None,
        template_name: str | None = None,
        template_backend: str | None = None,
        media_settings: Mapping[str, Any] | None = None,
    ) -> tuple[bool, dict | None, int | None]:
        backend_name = backend or self.config.backend
        payload = self._prepare_payload(commands, backend_name, self.config.encoding)
        payload_hash = hashlib.sha256(payload).hexdigest()
        return _record_and_send(
            payload=payload,
            payload_hash=payload_hash,
            template_name=template_name,
            template_backend=template_backend or backend_name,
            printer_name=self.config.printer_name,
            printer_backend=self.config.backend,
            printer_transport=self.config.transport,
            media_settings=media_settings,
            send_callable=self.transport.send,
            logger=self.logger,
        )

    def print_job(
        self,
        template: Template | Mapping[str, Any],
        variables: Mapping[str, Any],
        *,
        media_settings: Mapping[str, Any] | None = None,
    ) -> tuple[bool, dict | None, int | None]:
        try:
            backend_name, commands = self.compile_job(template, variables)
        except CompilationError as exc:
            return False, {"code": -1, "message": str(exc)}, None

        template_name: str | None = None
        if isinstance(template, Template):
            template_name = template.name
        elif isinstance(template, Mapping):
            maybe = template.get("name")
            if isinstance(maybe, str):
                template_name = maybe

        ok, error, job_id = self.send_commands(
            commands,
            backend=backend_name,
            template_name=template_name,
            template_backend=backend_name,
            media_settings=media_settings,
        )
        return ok, error, job_id

    def print_template(
        self,
        template: Template,
        dados: Mapping[str, Any],
        *,
        media_settings: Mapping[str, Any] | None = None,
    ) -> tuple[bool, dict | None, int | None]:
        variables = template.document.defaults(scope="template")
        for key, value in dados.items():
            if key == "items":
                continue
            variables[key] = value
        variables["items"] = build_label_series(dados, template)
        return self.print_job(template, variables, media_settings=media_settings)

    def print_calibration(
        self,
        *,
        backend: str | None = None,
        square_mm: float = CALIBRATION_SQUARE_MM,
    ) -> tuple[bool, dict | None, int | None]:
        tpl = build_calibration_template(
            square_mm=square_mm,
            backend=backend or self.config.backend,
        )
        return self.print_job(tpl, {})

    def apply_calibration(
        self,
        measured_width: float | None,
        measured_height: float | None,
        *,
        square_mm: float = CALIBRATION_SQUARE_MM,
    ) -> Calibration:
        new_cal = apply_calibration_adjustment(
            self.config.calibration,
            measured_width,
            measured_height,
            square_mm=square_mm,
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
    commands: bytes | str,
    repetir_em_falha: bool = False,
    *,
    nome_impressora: str | None = None,
    logger: logging.Logger | None = None,
    backend: str = "tspl",
    template_name: str | None = None,
    media_settings: Mapping[str, Any] | None = None,
) -> tuple[bool, dict | None, int | None]:
    config = PrinterConfig(
        backend=backend,
        transport="win32",
        printer_name=nome_impressora,
    )
    printer = Printer(config, logger=logger)
    payload = _prepare_payload(commands, backend, config.encoding)
    payload_hash = hashlib.sha256(payload).hexdigest()
    return _record_and_send(
        payload=payload,
        payload_hash=payload_hash,
        template_name=template_name,
        template_backend=backend,
        printer_name=nome_impressora,
        printer_backend=backend,
        printer_transport=config.transport,
        media_settings=media_settings,
        send_callable=printer.transport.send,
        logger=logger,
    )


def send(
    printer_name: str | None,
    payload: bytes,
    *,
    backend: str = "tspl",
    template_name: str | None = None,
    media_settings: Mapping[str, Any] | None = None,
    logger: logging.Logger | None = None,
) -> tuple[bool, dict | None, int | None]:
    transport = WindowsSpoolerTransport(printer_name)
    payload_bytes = bytes(payload)
    payload_hash = hashlib.sha256(payload_bytes).hexdigest()
    return _record_and_send(
        payload=payload_bytes,
        payload_hash=payload_hash,
        template_name=template_name,
        template_backend=backend,
        printer_name=printer_name,
        printer_backend=backend,
        printer_transport="win32",
        media_settings=media_settings,
        send_callable=transport.send,
        logger=logger or logging.getLogger("app"),
    )


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
    config = PrinterConfig(
        backend="tspl",
        transport="win32",
        printer_name=nome_impressora,
    )
    printer = Printer(config, logger=logger)
    return printer.print_template(template, dados)
