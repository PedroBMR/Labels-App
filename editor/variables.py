"""Widgets dedicated to managing template variables in the editor."""

from __future__ import annotations

import json
from functools import partial
from typing import Any

from model.template import TemplateVariable
from qt_compat import (
    QColor,
    QComboBox,
    QCheckBox,
    QAbstractItemView,
    QHeaderView,
    QHBoxLayout,
    QIcon,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QStyle,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
    Qt,
    pyqtSignal,
)


_TYPE_INFO: dict[str, tuple[str, str]] = {
    "text": ("Texto", "#eef2ff"),
    "multiline": ("Texto", "#eef2ff"),
    "number": ("Número", "#fff4d6"),
    "bool": ("Booleano", "#e8f6e1"),
    "json": ("JSON", "#ffe4e1"),
}


class VariablePanel(QWidget):
    """Panel listing template variables with rich editing capabilities."""

    changed = pyqtSignal(dict)
    savePresetRequested = pyqtSignal()
    applyPresetRequested = pyqtSignal()
    managePresetsRequested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._variables: dict[str, TemplateVariable] = {}
        self._values: dict[str, Any] = {}
        self._items: dict[str, QTreeWidgetItem] = {}
        self._editors: dict[str, QWidget] = {}
        self._types: dict[str, str] = {}
        self._errors: dict[str, str] = {}
        self._updating = False

        self._build_ui()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        controls = QHBoxLayout()
        controls.setSpacing(6)

        self.search_edit = QLineEdit(self)
        self.search_edit.setPlaceholderText("Buscar variáveis…")
        self.search_edit.textChanged.connect(self._apply_filters)
        controls.addWidget(self.search_edit, stretch=1)

        self.scope_combo = QComboBox(self)
        self.scope_combo.addItem("Todos os escopos", "all")
        self.scope_combo.addItem("Template", "template")
        self.scope_combo.addItem("Item", "item")
        self.scope_combo.currentIndexChanged.connect(self._apply_filters)
        controls.addWidget(self.scope_combo)

        self.save_preset_button = QPushButton("Save preset…", self)
        self.save_preset_button.clicked.connect(
            lambda _checked=False: self.savePresetRequested.emit()
        )
        controls.addWidget(self.save_preset_button)

        self.apply_preset_button = QPushButton("Apply preset…", self)
        self.apply_preset_button.clicked.connect(
            lambda _checked=False: self.applyPresetRequested.emit()
        )
        controls.addWidget(self.apply_preset_button)

        self.manage_presets_button = QPushButton("Manage presets…", self)
        self.manage_presets_button.clicked.connect(
            lambda _checked=False: self.managePresetsRequested.emit()
        )
        controls.addWidget(self.manage_presets_button)

        layout.addLayout(controls)

        self.tree = QTreeWidget(self)
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels(["Variável", "Valor", "Escopo", "Tipo"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionMode(QAbstractItemView.NoSelection)
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        layout.addWidget(self.tree, stretch=1)

    # ------------------------------------------------------------------
    def set_variables(
        self,
        variables: dict[str, TemplateVariable],
        values: dict[str, Any],
    ) -> None:
        self._variables = dict(variables)
        self._values = {}
        self._items = {}
        self._editors = {}
        self._types = {}
        self._errors = {}

        self._updating = True
        self.tree.clear()

        for name in sorted(self._variables):
            var = self._variables[name]
            item = QTreeWidgetItem(self.tree)
            item.setData(0, Qt.UserRole, name)
            item.setTextAlignment(2, Qt.AlignCenter)
            item.setTextAlignment(3, Qt.AlignCenter)

            editor_type = self._guess_editor_type(var, values.get(name))
            self._types[name] = editor_type

            editor = self._build_editor(name, editor_type, values.get(name), var)
            self.tree.setItemWidget(item, 1, editor)
            self._editors[name] = editor

            item.setText(2, "Template" if var.scope == "template" else "Item")
            type_chip = self._build_type_chip(editor_type)
            self.tree.setItemWidget(item, 3, type_chip)

            self._items[name] = item
            self._apply_type_color(item, editor_type)
            self._update_row_state(name)
            self._update_value_from_editor(name)

        self._updating = False
        self._apply_filters()
        self.changed.emit(dict(self._values))

    # ------------------------------------------------------------------
    def values(self) -> dict[str, Any]:
        return dict(self._values)

    def template_values(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for name, value in self._values.items():
            variable = self._variables.get(name)
            scope = variable.scope if variable else "item"
            if scope == "template":
                result[name] = value
        return result

    def item_values(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for name, value in self._values.items():
            variable = self._variables.get(name)
            scope = variable.scope if variable else "item"
            if scope == "item":
                result[name] = value
        return result

    # ------------------------------------------------------------------
    def _build_editor(
        self,
        name: str,
        editor_type: str,
        current: Any,
        variable: TemplateVariable,
    ) -> QWidget:
        if editor_type == "bool":
            checkbox = QCheckBox(self.tree)
            checkbox.setChecked(bool(self._coerce_bool(current, variable.default)))
            checkbox.stateChanged.connect(partial(self._on_editor_changed, name))
            return checkbox

        if editor_type == "number":
            field = QLineEdit(self.tree)
            field.setPlaceholderText("0")
            field.setText(self._format_number(current, variable.default))
            field.textChanged.connect(partial(self._on_editor_changed, name))
            return field

        if editor_type == "json":
            editor = QPlainTextEdit(self.tree)
            editor.setTabChangesFocus(True)
            editor.setMinimumHeight(72)
            editor.setPlainText(self._format_json(current, variable.default))
            editor.textChanged.connect(partial(self._on_editor_changed, name))
            return editor

        if editor_type == "multiline":
            editor = QPlainTextEdit(self.tree)
            editor.setTabChangesFocus(True)
            editor.setMinimumHeight(72)
            editor.setPlainText(self._format_text(current, variable.default))
            editor.textChanged.connect(partial(self._on_editor_changed, name))
            return editor

        field = QLineEdit(self.tree)
        field.setText(self._format_text(current, variable.default))
        field.textChanged.connect(partial(self._on_editor_changed, name))
        return field

    def _build_type_chip(self, editor_type: str) -> QWidget:
        label = QLabel(_TYPE_INFO.get(editor_type, (editor_type.title(), "#eeeeee"))[0])
        label.setAlignment(Qt.AlignCenter)
        color = _TYPE_INFO.get(editor_type, ("", "#eeeeee"))[1]
        label.setStyleSheet(
            "border-radius: 10px; padding: 2px 8px; font-size: 11px; "
            f"background-color: {color}; color: #1f1f1f;"
        )
        return label

    # ------------------------------------------------------------------
    def _on_editor_changed(self, name: str) -> None:
        if self._updating:
            return
        self._update_value_from_editor(name)
        self.changed.emit(dict(self._values))
        self._apply_filters()

    def _update_value_from_editor(self, name: str) -> None:
        item = self._items.get(name)
        editor = self._editors.get(name)
        variable = self._variables.get(name)
        if not item or not editor or not variable:
            return
        editor_type = self._types.get(name, "text")

        value, valid, error = self._read_editor_value(editor_type, editor, variable)
        self._values[name] = value

        if valid:
            self._errors.pop(name, None)
        else:
            self._errors[name] = error or "Valor inválido"

        self._update_row_state(name)

    # ------------------------------------------------------------------
    def _apply_filters(self) -> None:
        scope_filter = self.scope_combo.currentData() or "all"
        query = self.search_edit.text().strip().lower()
        for name, item in self._items.items():
            variable = self._variables.get(name)
            if not variable:
                continue
            visible = True
            if scope_filter != "all" and variable.scope != scope_filter:
                visible = False
            if visible and query:
                haystack = " ".join(
                    filter(
                        None,
                        [
                            name.lower(),
                            (variable.description or "").lower(),
                            str(self._values.get(name, "")).lower(),
                        ],
                    )
                )
                if query not in haystack:
                    visible = False
            item.setHidden(not visible)

    # ------------------------------------------------------------------
    def _update_row_state(self, name: str) -> None:
        item = self._items.get(name)
        variable = self._variables.get(name)
        if not item or not variable:
            return

        base_label = name + (" *" if variable.is_required() else "")
        error = self._errors.get(name)

        if error:
            item.setText(0, f"⚠ {base_label}")
            warning_icon = self.style().standardIcon(QStyle.SP_MessageBoxWarning)
            item.setIcon(0, warning_icon)
            tooltip = error
            if variable.description:
                tooltip = f"{variable.description}\n\n{error}"
            item.setToolTip(0, tooltip)
            item.setToolTip(1, tooltip)
            item.setData(0, Qt.ForegroundRole, QColor("#c0392b"))
        else:
            item.setText(0, base_label)
            item.setIcon(0, QIcon())
            tooltip = variable.description or ""
            item.setToolTip(0, tooltip)
            item.setToolTip(1, tooltip)
            item.setData(0, Qt.ForegroundRole, None)

    # ------------------------------------------------------------------
    def _apply_type_color(self, item: QTreeWidgetItem, editor_type: str) -> None:
        color_hex = _TYPE_INFO.get(editor_type, ("", "#f0f0f0"))[1]
        color = QColor(color_hex)
        color.setAlpha(60)
        for column in range(self.tree.columnCount()):
            item.setBackground(column, color)

    # ------------------------------------------------------------------
    @staticmethod
    def _guess_editor_type(variable: TemplateVariable, value: Any) -> str:
        candidate = value if value is not None else variable.default
        if isinstance(candidate, bool):
            return "bool"
        if isinstance(candidate, (int, float)) and not isinstance(candidate, bool):
            return "number"
        if isinstance(candidate, (list, dict)):
            return "json"
        if isinstance(candidate, str):
            stripped = candidate.strip()
            if stripped.startswith("{") or stripped.startswith("["):
                try:
                    json.loads(stripped)
                except Exception:
                    pass
                else:
                    return "json"
            if "\n" in candidate or len(candidate) > 80:
                return "multiline"
        if isinstance(variable.default, (list, dict)):
            return "json"
        if isinstance(variable.default, str) and (
            "\n" in variable.default or len(variable.default) > 80
        ):
            return "multiline"
        return "text"

    @staticmethod
    def _format_json(current: Any, default: Any) -> str:
        value = current if current is not None else default
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        try:
            return json.dumps(value, ensure_ascii=False, indent=2)
        except TypeError:
            return str(value)

    @staticmethod
    def _format_text(current: Any, default: Any) -> str:
        value = current if current is not None else default
        if value is None:
            return ""
        return str(value)

    @staticmethod
    def _format_number(current: Any, default: Any) -> str:
        value = current if current is not None else default
        if value is None:
            return ""
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return str(value)
        return str(value)

    @staticmethod
    def _coerce_bool(current: Any, default: Any) -> bool:
        if current is not None:
            return bool(current)
        if default is not None:
            return bool(default)
        return False

    def _read_editor_value(
        self,
        editor_type: str,
        editor: QWidget,
        variable: TemplateVariable,
    ) -> tuple[Any, bool, str]:
        if editor_type == "bool" and isinstance(editor, QCheckBox):
            return editor.isChecked(), True, ""

        if editor_type == "number" and isinstance(editor, QLineEdit):
            text = editor.text().strip().replace(",", ".")
            if not text:
                if variable.is_required():
                    return None, False, "Informe um número"
                return None, True, ""
            try:
                number = float(text)
            except ValueError:
                return None, False, "Número inválido"
            if number.is_integer():
                number = int(number)
            return number, True, ""

        if editor_type == "json" and isinstance(editor, QPlainTextEdit):
            text = editor.toPlainText().strip()
            if not text:
                if variable.is_required():
                    return None, False, "Informe um valor JSON"
                return None, True, ""
            try:
                return json.loads(text), True, ""
            except ValueError as exc:
                return None, False, f"JSON inválido: {exc}"

        if editor_type == "multiline" and isinstance(editor, QPlainTextEdit):
            text = editor.toPlainText()
            if variable.is_required() and not text.strip():
                return text, False, "Valor obrigatório"
            return text, True, ""

        if isinstance(editor, QPlainTextEdit):
            text = editor.toPlainText()
        elif isinstance(editor, QLineEdit):
            text = editor.text()
        else:
            text = str(getattr(editor, "text", lambda: "")())

        if variable.is_required() and not text.strip():
            return text, False, "Valor obrigatório"
        return text, True, ""
