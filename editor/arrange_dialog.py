from __future__ import annotations

from qt_compat import QDialog, QDialogButtonBox, QFormLayout, QSpinBox, QVBoxLayout


class ArrangeGridDialog(QDialog):
    """Dialog to collect grid dimensions for the arrange action."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Organizar em grade")
        self._columns = QSpinBox(self)
        self._columns.setMinimum(1)
        self._columns.setMaximum(999)
        self._columns.setValue(2)

        self._rows = QSpinBox(self)
        self._rows.setMinimum(1)
        self._rows.setMaximum(999)
        self._rows.setValue(2)

        form_layout = QFormLayout()
        form_layout.addRow("Colunas (N):", self._columns)
        form_layout.addRow("Linhas (M):", self._rows)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form_layout)
        layout.addWidget(button_box)

    def grid_size(self) -> tuple[int, int]:
        return self._columns.value(), self._rows.value()
