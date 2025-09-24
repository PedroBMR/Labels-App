"""Model helpers for application data."""

from .template import (
    CURRENT_TEMPLATE_VERSION,
    TemplateDocument,
    TemplateValidationError,
    TemplateVariable,
    slugify,
)

__all__ = [
    "CURRENT_TEMPLATE_VERSION",
    "TemplateDocument",
    "TemplateValidationError",
    "TemplateVariable",
    "slugify",
]
