"""Central template storage helper with save notifications."""

from __future__ import annotations

from pathlib import Path

from model.template import TemplateDocument, slugify
from qt_compat import QObject, pyqtSignal
from utils import recurso_caminho

__all__ = ["TemplateStore", "template_store"]


class TemplateStore(QObject):
    """Persist templates under the application data directory."""

    templateSaved = pyqtSignal(str)

    def __init__(self, directory: Path | None = None) -> None:
        super().__init__()
        self._directory = Path(directory) if directory is not None else None

    @property
    def directory(self) -> Path:
        if self._directory is None:
            self._directory = Path(recurso_caminho("templates"))
        self._directory.mkdir(parents=True, exist_ok=True)
        return self._directory

    # ------------------------------------------------------------------
    def path_for_name(self, name: str) -> Path:
        slug = slugify(name or "template") or "template"
        return self.directory / f"{slug}.json"

    def ensure_path(self, path: Path, *, name: str | None = None) -> Path:
        target = Path(path)
        if target.suffix != ".json":
            target = target.with_suffix(".json")
        if target.parent == self.directory:
            return target
        return self.path_for_name(name or target.stem)

    # ------------------------------------------------------------------
    def save(
        self,
        document: TemplateDocument,
        *,
        path: Path | None = None,
        overwrite: bool = False,
    ) -> Path:
        target = self.ensure_path(
            path or self.path_for_name(document.name),
            name=document.name,
        )
        if target.exists() and not overwrite:
            raise FileExistsError(str(target))
        document.dump(target)
        # Reload templates so consumers see the freshly saved model.
        from printing import template_manager  # Local import to avoid cycles

        template_manager.reload()
        self.templateSaved.emit(str(target))
        return target


template_store = TemplateStore()
