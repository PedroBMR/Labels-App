"""Data structures for label templates."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from string import Formatter
from typing import Any, ClassVar, Iterable, Mapping

__all__ = [
    "CURRENT_TEMPLATE_VERSION",
    "TemplateDocument",
    "TemplateValidationError",
    "TemplateVariable",
    "slugify",
]

CURRENT_TEMPLATE_VERSION = 1


class TemplateValidationError(ValueError):
    """Raised when required variables are missing for a template."""

    def __init__(
        self,
        missing: list[str],
        *,
        scope: str | None = None,
        index: int | None = None,
    ) -> None:
        self.missing = missing
        self.scope = scope
        self.index = index
        if scope == "item" and index is not None:
            message = (
                "Variáveis obrigatórias ausentes no item "
                f"{index + 1}: {', '.join(missing)}"
            )
        else:
            message = f"Variáveis obrigatórias ausentes: {', '.join(missing)}"
        super().__init__(message)


@dataclass(slots=True)
class TemplateVariable:
    """Describe metadata about a template variable."""

    name: str
    default: Any | None = None
    required: bool = False
    scope: str = "item"
    description: str | None = None

    VALID_SCOPES: ClassVar[set[str]] = {"item", "template"}

    def __post_init__(self) -> None:
        if self.scope not in self.VALID_SCOPES:
            self.scope = "item"

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"required": self.required, "scope": self.scope}
        if self.description:
            data["description"] = self.description
        if self.default is not None:
            data["default"] = self.default
        return data

    @classmethod
    def from_any(cls, name: str, value: Any) -> "TemplateVariable":
        if isinstance(value, cls):
            return value
        if isinstance(value, Mapping):
            data = dict(value)
            required = bool(data.get("required"))
            scope = str(data.get("scope", "item"))
            description = data.get("description")
            default = data.get("default") if "default" in data else None
            return cls(
                name=name,
                default=default,
                required=required,
                scope=scope,
                description=str(description) if description is not None else None,
            )
        return cls(name=name, default=value)

    def is_required(self) -> bool:
        return bool(self.required)


_slug_regex = re.compile(r"[^a-z0-9]+")


def _iter_format_fields(value: str) -> Iterable[str]:
    """Yield placeholder field names found in ``value``."""

    formatter = Formatter()
    try:
        iterator = formatter.parse(value)
    except ValueError:  # pragma: no cover - defensive against bad formats
        return

    for _literal, field_name, _format_spec, _conversion in iterator:
        if not field_name:
            continue
        cleaned = field_name.split("!", 1)[0]
        cleaned = cleaned.split(":", 1)[0]
        cleaned = cleaned.split(".", 1)[0]
        cleaned = cleaned.split("[", 1)[0]
        cleaned = cleaned.strip()
        if cleaned:
            yield cleaned


def _collect_placeholders(data: Any) -> set[str]:
    names: set[str] = set()
    if isinstance(data, Mapping):
        for value in data.values():
            names.update(_collect_placeholders(value))
    elif isinstance(data, (list, tuple)):
        for entry in data:
            names.update(_collect_placeholders(entry))
    elif isinstance(data, str):
        for field in _iter_format_fields(data):
            names.add(field)
    return names


def slugify(value: str) -> str:
    """Return a filesystem-friendly slug from ``value``."""

    normalized = unicodedata.normalize("NFKD", value or "")
    without_marks = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    lowered = without_marks.lower()
    collapsed = _slug_regex.sub("-", lowered).strip("-")
    return collapsed or "template"


def _normalise_page(page: Mapping[str, Any] | None) -> dict[str, Any]:
    if isinstance(page, Mapping):
        data = {str(key): value for key, value in page.items()}
    else:
        data = {}
    data.setdefault("backend", data.get("type", "tspl"))
    return data


def _normalise_elements(elements: Any) -> list[dict[str, Any]]:
    if not isinstance(elements, list):
        return []
    normalised: list[dict[str, Any]] = []
    for element in elements:
        if isinstance(element, Mapping):
            normalised.append({str(key): value for key, value in element.items()})
    return normalised


def _normalise_variables(data: Mapping[str, Any] | None) -> dict[str, TemplateVariable]:
    variables: dict[str, TemplateVariable] = {}
    if not isinstance(data, Mapping):
        return variables
    for name, spec in data.items():
        variables[str(name)] = TemplateVariable.from_any(str(name), spec)
    return variables


def _value_provided(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    return True


def _normalise_metadata(data: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(data, Mapping):
        return {}
    metadata = {str(key): value for key, value in data.items()}
    fonts = metadata.get("fonts")
    if isinstance(fonts, Mapping):
        metadata["fonts"] = {str(key): value for key, value in fonts.items()}
    else:
        metadata.pop("fonts", None)
    return metadata


@dataclass(slots=True)
class TemplateDocument:
    """Serializable template representation."""

    name: str
    page: dict[str, Any]
    elements: list[dict[str, Any]]
    variables: dict[str, TemplateVariable] = field(default_factory=dict)
    version: int = CURRENT_TEMPLATE_VERSION
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.page = _normalise_page(self.page)
        self.elements = _normalise_elements(self.elements)
        self.variables = dict(self.variables)
        for key, value in list(self.variables.items()):
            if not isinstance(value, TemplateVariable):
                self.variables[key] = TemplateVariable.from_any(key, value)
        self.metadata = _normalise_metadata(self.metadata)

    @property
    def backend(self) -> str:
        return str(self.page.get("backend", "tspl"))

    @property
    def slug(self) -> str:
        return slugify(self.name)

    def to_dict(self) -> dict[str, Any]:
        data = {
            "name": self.name,
            "version": self.version,
            "page": dict(self.page),
            "elements": [dict(element) for element in self.elements],
            "variables": {name: var.to_dict() for name, var in self.variables.items()},
        }
        if self.metadata:
            data["metadata"] = dict(self.metadata)
        return data

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def copy(self) -> "TemplateDocument":
        return TemplateDocument.from_dict(self.to_dict())

    def as_backend_dict(self) -> dict[str, Any]:
        data = dict(self.page)
        data.setdefault("backend", data.get("type", "tspl"))
        data["elements"] = [dict(element) for element in self.elements]
        if self.metadata:
            data["metadata"] = dict(self.metadata)
        return data

    def defaults(self, *, scope: str | None = None) -> dict[str, Any]:
        defaults: dict[str, Any] = {}
        for name, var in self.variables.items():
            if var.default is None:
                continue
            if scope is None or var.scope == scope:
                defaults[name] = var.default
        return defaults

    def required_names(self, *, scope: str | None = None) -> set[str]:
        names = set()
        for name, var in self.variables.items():
            if var.is_required() and (scope is None or var.scope == scope):
                names.add(name)
        return names

    def placeholder_names(self) -> set[str]:
        """Return a set with all placeholder names referenced by the template."""

        names = _collect_placeholders(self.elements)
        names.update(_collect_placeholders(self.page))
        return names

    def ensure_placeholder_variables(self, *, default_scope: str = "item") -> set[str]:
        """Ensure placeholders without metadata become template variables."""

        placeholders = self.placeholder_names()
        for name in placeholders:
            if name not in self.variables:
                self.variables[name] = TemplateVariable(name=name, scope=default_scope)
        return placeholders

    def ensure_valid(self, variables: Mapping[str, Any]) -> None:
        missing_template = [
            name
            for name in self.required_names(scope="template")
            if not _value_provided(variables.get(name))
        ]
        if missing_template:
            raise TemplateValidationError(sorted(missing_template), scope="template")

        required_item_vars = self.required_names(scope="item")
        if not required_item_vars:
            return

        items = variables.get("items")
        if not isinstance(items, list):
            raise TemplateValidationError(["items"], scope="template")

        for index, item in enumerate(items):
            if not isinstance(item, Mapping):
                raise TemplateValidationError(["items"], scope="item", index=index)
            missing = [
                name
                for name in required_item_vars
                if not _value_provided(item.get(name))
            ]
            if missing:
                raise TemplateValidationError(
                    sorted(missing), scope="item", index=index
                )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TemplateDocument":
        if "name" not in data:
            raise ValueError("Template data missing 'name'")
        name = str(data["name"])
        version = int(data.get("version", CURRENT_TEMPLATE_VERSION))
        page = _normalise_page(data.get("page"))
        elements = _normalise_elements(data.get("elements"))
        variables = _normalise_variables(data.get("variables"))
        metadata = _normalise_metadata(data.get("metadata"))
        return cls(
            name=name,
            page=page,
            elements=elements,
            variables=variables,
            version=version,
            metadata=metadata,
        )

    @classmethod
    def from_json(cls, payload: str) -> "TemplateDocument":
        return cls.from_dict(json.loads(payload))

    @classmethod
    def from_file(cls, path: str | Path) -> "TemplateDocument":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)

    def dump(self, path: str | Path, *, indent: int | None = 2) -> None:
        Path(path).write_text(self.to_json(indent=indent), encoding="utf-8")

    @classmethod
    def from_legacy(
        cls,
        name: str,
        data: Mapping[str, Any],
        *,
        defaults: Mapping[str, Any] | None = None,
    ) -> "TemplateDocument":
        elements = _normalise_elements(data.get("elements"))
        page = {str(key): value for key, value in data.items() if key != "elements"}
        page.setdefault("backend", page.get("type", "tspl"))
        variables: dict[str, TemplateVariable] = {}
        if defaults:
            for key, value in defaults.items():
                variables[str(key)] = TemplateVariable(name=str(key), default=value)
        variables.setdefault(
            "items",
            TemplateVariable(
                name="items",
                scope="template",
                required=True,
                description="Lista de itens",
            ),
        )
        return cls(name=name, page=page, elements=elements, variables=variables)
