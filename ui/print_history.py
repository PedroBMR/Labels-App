"""Widgets utilitários para exibir o histórico de impressão."""

from __future__ import annotations

from datetime import datetime
from typing import Iterable

from db import store as db_store
from qt_compat import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    Qt,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    pyqtSignal,
)


def _format_timestamp(value: object) -> str:
    if not value:
        return ""
    if isinstance(value, bytes):  # defensive
        try:
            value = value.decode("utf-8")
        except Exception:
            return ""
    text = str(value)
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return text
    if dt.tzinfo is not None:
        dt = dt.astimezone()
    return dt.strftime("%d/%m/%Y %H:%M:%S")


class PrintHistoryWidget(QWidget):
    """Tabela com os trabalhos de impressão armazenados na base."""

    reprintRequested = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None, *, limit: int = 50) -> None:
        super().__init__(parent)
        self._limit = limit

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        title = QLabel("Histórico recente de impressões")
        title.setStyleSheet("color:#d0d0d0;font-weight:600;")
        layout.addWidget(title)

        self._table = QTableWidget(0, 7, self)
        self._table.setObjectName("printHistoryTable")
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.setHorizontalHeaderLabels(
            [
                "Status",
                "Impressora",
                "Template",
                "Transporte",
                "Criado",
                "Atualizado",
                "Erro",
            ]
        )
        self._table.itemDoubleClicked.connect(self._handle_double_click)
        layout.addWidget(self._table)

        controls = QHBoxLayout()
        controls.addStretch(1)

        self._refresh_btn = QPushButton("Atualizar")
        self._refresh_btn.clicked.connect(self.refresh)
        controls.addWidget(self._refresh_btn)

        self._reprint_btn = QPushButton("Reimprimir seleção")
        self._reprint_btn.clicked.connect(self._emit_reprint)
        controls.addWidget(self._reprint_btn)

        layout.addLayout(controls)

        self.refresh()

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        """Recarrega os dados do histórico a partir do banco."""

        try:
            rows = db_store.list_print_jobs(limit=self._limit)
        except Exception:
            rows = []
        self._populate(rows)

    def selected_job_id(self) -> int | None:
        """Retorna o identificador do trabalho selecionado."""

        indexes = self._table.selectionModel().selectedRows()
        if not indexes:
            return None
        row = indexes[0].row()
        item = self._table.item(row, 0)
        if item is None:
            return None
        value = item.data(Qt.UserRole)
        if isinstance(value, int):
            return value
        try:
            return int(value)
        except Exception:
            return None

    # ------------------------------------------------------------------
    def _populate(self, rows: Iterable[dict[str, object]]) -> None:
        data = list(rows)
        self._table.setRowCount(len(data))
        for row_idx, row in enumerate(data):
            job_id = row.get("id")
            status_text = str(row.get("status") or "").upper()
            status_item = QTableWidgetItem(status_text)
            status_item.setData(
                Qt.UserRole,
                int(job_id) if isinstance(job_id, int) else job_id,
            )
            self._table.setItem(row_idx, 0, status_item)

            printer = str(row.get("printer_name") or "")
            self._table.setItem(row_idx, 1, QTableWidgetItem(printer))

            template = str(row.get("template_name") or "")
            backend = row.get("template_backend") or row.get("printer_backend")
            if backend:
                template = template or "—"
                template = f"{template} ({backend})"
            self._table.setItem(row_idx, 2, QTableWidgetItem(template))

            transport = str(row.get("printer_transport") or "")
            self._table.setItem(row_idx, 3, QTableWidgetItem(transport))

            created = row.get("pending_at") or row.get("created_at")
            self._table.setItem(
                row_idx,
                4,
                QTableWidgetItem(_format_timestamp(created)),
            )

            updated = (
                row.get("finished_at")
                or row.get("failed_at")
                or row.get("running_at")
            )
            self._table.setItem(
                row_idx,
                5,
                QTableWidgetItem(_format_timestamp(updated)),
            )

            error_text = str(row.get("error_text") or "")
            self._table.setItem(row_idx, 6, QTableWidgetItem(error_text))

    def _emit_reprint(self) -> None:
        job_id = self.selected_job_id()
        if job_id is not None:
            self.reprintRequested.emit(int(job_id))

    def _handle_double_click(self, _item) -> None:  # pragma: no cover - UI interaction
        self._emit_reprint()
