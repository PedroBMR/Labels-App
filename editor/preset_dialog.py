"""Dialog for managing stored variable presets for a template."""

from __future__ import annotations

from qt_compat import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QInputDialog,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    Qt,
    QVBoxLayout,
)

from .preset_manager import PresetManager

__all__ = ["PresetManagerDialog"]


class PresetManagerDialog(QDialog):
    """Simple UI listing presets with rename/delete affordances."""

    def __init__(
        self, manager: PresetManager, parent: QDialog | None = None
    ) -> None:
        super().__init__(parent)
        self._manager = manager
        self.setWindowTitle("Gerenciar presets")
        self.resize(400, 320)

        layout = QVBoxLayout(self)

        self._list = QListWidget(self)
        self._list.itemSelectionChanged.connect(self._update_button_state)
        layout.addWidget(self._list, stretch=1)

        button_row = QHBoxLayout()
        self._rename_button = QPushButton("Renomear…", self)
        self._rename_button.clicked.connect(self._rename_selected)
        button_row.addWidget(self._rename_button)

        self._delete_button = QPushButton("Excluir", self)
        self._delete_button.clicked.connect(self._delete_selected)
        button_row.addWidget(self._delete_button)

        layout.addLayout(button_row)

        button_box = QDialogButtonBox(QDialogButtonBox.Close, parent=self)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self._populate()
        self._update_button_state()

    # ------------------------------------------------------------------
    def _populate(self, *, select: str | None = None) -> None:
        self._list.clear()
        presets = self._manager.list_presets()
        for preset in presets:
            name = str(preset.get("name") or "")
            item = QListWidgetItem(name, self._list)
            item.setData(Qt.UserRole, preset)
            updated_at = preset.get("updated_at")
            if updated_at:
                item.setToolTip(f"Atualizado em {updated_at}")
        if select:
            matches = self._list.findItems(select, Qt.MatchExactly)
            if matches:
                self._list.setCurrentItem(matches[0])
        elif self._list.count():
            self._list.setCurrentRow(0)

    # ------------------------------------------------------------------
    def _selected_item(self) -> QListWidgetItem | None:
        items = self._list.selectedItems()
        return items[0] if items else None

    # ------------------------------------------------------------------
    def _update_button_state(self) -> None:
        has_selection = self._selected_item() is not None
        self._rename_button.setEnabled(has_selection)
        self._delete_button.setEnabled(has_selection)

    # ------------------------------------------------------------------
    def _rename_selected(self) -> None:
        item = self._selected_item()
        if item is None:
            return
        old_name = item.text()
        new_name, ok = QInputDialog.getText(
            self,
            "Renomear preset",
            "Novo nome:",
            text=old_name,
        )
        if not ok:
            return
        cleaned = new_name.strip()
        if not cleaned:
            QMessageBox.warning(
                self,
                "Nome inválido",
                "Informe um nome para o preset.",
            )
            return
        if not self._manager.rename_preset(old_name, cleaned):
            QMessageBox.warning(
                self,
                "Falha ao renomear",
                "Não foi possível renomear o preset selecionado.",
            )
            return
        self._populate(select=cleaned)

    # ------------------------------------------------------------------
    def _delete_selected(self) -> None:
        item = self._selected_item()
        if item is None:
            return
        name = item.text()
        reply = QMessageBox.question(
            self,
            "Excluir preset",
            f"Excluir o preset '{name}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        if not self._manager.delete_preset(name):
            QMessageBox.warning(
                self,
                "Preset ausente",
                "O preset selecionado não está mais disponível.",
            )
            self._populate()
            return
        self._populate()

