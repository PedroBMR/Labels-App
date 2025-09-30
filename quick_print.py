"""Modal dialog for the quick print workflow."""

from __future__ import annotations

import json
from typing import Any, Mapping

try:  # pragma: no cover - optional dependency guard
    from PIL.ImageQt import ImageQt  # type: ignore
except ImportError:  # pragma: no cover - Pillow missing at runtime
    ImageQt = None  # type: ignore[assignment]

from db import store as db_store
from log import logger
from persistence import carregar_config
from printing import (
    WindowsSpoolerTransport,
    compile_model_silent,
    listar_impressoras,
    listar_templates,
    prepare_quick_job,
    resolve_media_settings,
)
from printing.queue import PrinterTarget, enqueue_job
from qt_compat import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFont,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPixmap,
    QPushButton,
    QSpinBox,
    Qt,
    QVBoxLayout,
)
from render import render_template
from template_store import template_store


class QuickPrintDialog(QDialog):
    """Allow users to print labels by selecting only the template."""

    _last_payload: bytes | None = None
    _last_printer: str | None = None
    _last_job_id: int | None = None
    _last_backend: str = "tspl"
    _last_template: str | None = None
    _last_media_settings: Mapping[str, Any] | None = None

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Impressão rápida")
        self.setModal(True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("Selecione o modelo para imprimir")
        title.setFont(QFont("Segoe UI", 12, QFont.Medium))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color:#f0f0f0;")
        layout.addWidget(title)

        self.model_combo = QComboBox()
        self.model_combo.setEditable(False)
        self.model_combo.setStyleSheet(
            "".join(
                [
                    "QComboBox{background:#252525;color:#f0f0f0;padding:6px;",
                    "border:1px solid #333;border-radius:6px;}",
                    "QComboBox QAbstractItemView{background:#1e1e1e;color:#f0f0f0;}",
                ]
            )
        )

        self.copies_spin = QSpinBox()
        self.copies_spin.setMinimum(1)
        self.copies_spin.setValue(1)
        self.copies_spin.setStyleSheet(
            "".join(
                [
                    "QSpinBox{background:#252525;color:#f0f0f0;padding:6px;",
                    "border:1px solid #333;border-radius:6px;}",
                ]
            )
        )

        self.printer_combo = QComboBox()
        self.printer_combo.setEditable(True)
        self.printer_combo.setInsertPolicy(QComboBox.NoInsert)
        if self.printer_combo.lineEdit():
            self.printer_combo.lineEdit().setPlaceholderText("Impressora padrão")
        self.printer_combo.setStyleSheet(
            "".join(
                [
                    "QComboBox{background:#252525;color:#f0f0f0;padding:6px;",
                    "border:1px solid #333;border-radius:6px;}",
                    "QComboBox QAbstractItemView{background:#1e1e1e;color:#f0f0f0;}",
                ]
            )
        )

        self.preview_check = QCheckBox("Mostrar pré-visualização antes de enviar")
        self.preview_check.setStyleSheet("color:#d0d0d0;")
        self._preview_available = ImageQt is not None
        if not self._preview_available:
            self.preview_check.setChecked(False)
            self.preview_check.setEnabled(False)
            self.preview_check.setToolTip(
                "Pré-visualização indisponível: instale Pillow para habilitar."
            )

        form_layout = QVBoxLayout()
        form_layout.setSpacing(10)

        def _row(label_text: str, widget) -> None:
            row = QHBoxLayout()
            label = QLabel(label_text)
            label.setStyleSheet("color:#d0d0d0;font-size:13px;")
            row.addWidget(label)
            row.addWidget(widget, stretch=1)
            form_layout.addLayout(row)

        _row("Modelo:", self.model_combo)
        _row("Cópias:", self.copies_spin)
        _row("Impressora:", self.printer_combo)

        layout.addLayout(form_layout)
        layout.addWidget(self.preview_check)

        button_row = QHBoxLayout()
        button_row.setSpacing(12)

        self.print_btn = QPushButton("Imprimir")
        self.print_btn.setDefault(True)
        self.print_btn.setAutoDefault(True)
        self.print_btn.clicked.connect(self._on_print)
        self.print_btn.setStyleSheet(
            "".join(
                [
                    "QPushButton{background:#2f855a;color:white;padding:8px 18px;",
                    "border:none;border-radius:6px;}",
                    "QPushButton:pressed{background:#276749;}",
                ]
            )
        )

        self.reprint_btn = QPushButton("Reimprimir última")
        self.reprint_btn.clicked.connect(self._on_reprint_last)
        self.reprint_btn.setStyleSheet(
            "".join(
                [
                    "QPushButton{background:#2d3748;color:#f0f0f0;padding:8px 18px;",
                    "border:none;border-radius:6px;}",
                    "QPushButton:pressed{background:#1a202c;}",
                ]
            )
        )

        self.close_btn = QPushButton("Fechar")
        self.close_btn.clicked.connect(self.reject)
        self.close_btn.setStyleSheet(
            "".join(
                [
                    "QPushButton{background:#4a5568;color:#f0f0f0;padding:8px 18px;",
                    "border:none;border-radius:6px;}",
                    "QPushButton:pressed{background:#2d3748;}",
                ]
            )
        )

        button_row.addWidget(self.print_btn)
        button_row.addWidget(self.reprint_btn)
        button_row.addWidget(self.close_btn)
        layout.addLayout(button_row)

        self.status_label = QLabel("Pronto")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color:#9ae6b4;font-size:12px;")
        layout.addWidget(self.status_label)

        self.setStyleSheet("background-color:#1b1b1b;")

        template_store.templateSaved.connect(self._on_template_saved)

        self._reload_templates()
        self._reload_printers()

    # ------------------------------------------------------------------
    def _reload_templates(self) -> None:
        current = self.model_combo.currentText()
        names = listar_templates()
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        self.model_combo.addItems(names)
        if current:
            index = self.model_combo.findText(current)
            if index >= 0:
                self.model_combo.setCurrentIndex(index)
        self.model_combo.blockSignals(False)
        if not names:
            self._update_status("Nenhum modelo disponível", "#f6ad55")

    def _reload_printers(self) -> None:
        current = self.printer_combo.currentText().strip()
        names = listar_impressoras()
        self.printer_combo.blockSignals(True)
        self.printer_combo.clear()
        self.printer_combo.addItem("")
        self.printer_combo.addItems(names)
        if current:
            index = self.printer_combo.findText(current)
            if index >= 0:
                self.printer_combo.setCurrentIndex(index)
            else:
                self.printer_combo.setEditText(current)
        self.printer_combo.blockSignals(False)

    def showEvent(self, event) -> None:  # noqa: D401
        super().showEvent(event)
        self._reload_templates()
        self._reload_printers()

    def _on_template_saved(self, _path: str) -> None:
        self._reload_templates()

    def _current_model(self) -> str:
        return self.model_combo.currentText().strip()

    def _current_printer(self) -> str | None:
        text = self.printer_combo.currentText().strip()
        return text or None

    def set_printer_hint(self, name: str | None) -> None:
        if name:
            self.printer_combo.setEditText(name)

    def _build_overrides(self) -> Mapping[str, int]:
        return {"copies": self.copies_spin.value()}

    def _on_print(self) -> None:
        model = self._current_model()
        if not model:
            QMessageBox.warning(self, "Modelo", "Selecione um modelo para imprimir.")
            return

        overrides = self._build_overrides()
        config = carregar_config()
        printer = self._current_printer()
        if not printer:
            hint = str(config.get("ultima_impressora", "")).strip()
            printer = hint or None

        profile = None
        if printer:
            try:
                profile = db_store.load_printer_profile(printer)
            except Exception:  # pragma: no cover - defensive logging only
                logger.exception("Falha ao carregar perfil da impressora %s", printer)
                profile = None

        try:
            template, variables = prepare_quick_job(
                model,
                overrides,
                silent=True,
                config=config,
                printer_name=printer,
                printer_profile=profile,
            )
        except Exception as exc:
            logger.exception("Falha ao preparar modelo para impressão rápida")
            QMessageBox.critical(self, "Erro", str(exc))
            return

        if self.preview_check.isChecked() and self._preview_available:
            if not self._show_preview(template, variables):
                self._update_status("Pré-visualização cancelada", "#f6ad55")
                return
        elif self.preview_check.isChecked() and not self._preview_available:
            QMessageBox.warning(
                self,
                "Pré-visualização",
                "Instale o pacote Pillow para habilitar a pré-visualização.",
            )
            self.preview_check.setChecked(False)

        media_settings = resolve_media_settings(config, printer_profile=profile)

        try:
            payload = compile_model_silent(
                model,
                overrides,
                silent=True,
                printer_name=printer,
                printer_profile=profile,
            )
        except Exception as exc:
            logger.exception("Falha ao compilar modelo para impressão rápida")
            QMessageBox.critical(self, "Erro", str(exc))
            return

        backend_name = "tspl"
        if hasattr(template, "backend"):
            candidate = getattr(template, "backend")
            if isinstance(candidate, str) and candidate:
                backend_name = candidate
        if hasattr(template, "document"):
            page = getattr(template.document, "page", {})
            if isinstance(page, Mapping):
                maybe_backend = page.get("backend")
                if isinstance(maybe_backend, str) and maybe_backend:
                    backend_name = maybe_backend

        printer = printer
        transport = WindowsSpoolerTransport(printer)
        target = PrinterTarget(
            name=printer,
            backend=backend_name,
            transport="win32",
            send=transport.send,
            logger=logger,
        )

        try:
            job_id, status = enqueue_job(
                model,
                payload,
                target,
                copies=self.copies_spin.value(),
                params={
                    "template_backend": backend_name,
                    "printer_backend": backend_name,
                    "printer_transport": "win32",
                    "media_settings": media_settings,
                    "printer_host": None,
                    "printer_port": None,
                },
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Falha ao enfileirar impressão rápida")
            self._update_status("Erro ao enfileirar impressão", "#f6ad55")
            QMessageBox.critical(
                self,
                "Erro na impressão",
                f"Não foi possível enfileirar a impressão:\n{exc}",
            )
            return

        QuickPrintDialog._last_payload = payload
        QuickPrintDialog._last_printer = printer
        QuickPrintDialog._last_job_id = job_id
        QuickPrintDialog._last_backend = backend_name
        QuickPrintDialog._last_template = model
        QuickPrintDialog._last_media_settings = media_settings

        status_text = str(status or "pending").lower()
        if status_text == "failed":
            self._update_status("Erro ao enfileirar impressão", "#f6ad55")
            QMessageBox.critical(
                self,
                "Erro na impressão",
                "Não foi possível iniciar o trabalho de impressão.",
            )
            return

        message = f"Impressão enfileirada (#{job_id})"
        color = "#9ae6b4" if status_text == "done" else "#63b3ed"
        self._update_status(message, color)

    def _on_reprint_last(self) -> None:
        payload = None
        record = None
        if QuickPrintDialog._last_job_id is not None:
            try:
                payload = db_store.get_job_payload(job_id=QuickPrintDialog._last_job_id)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Não foi possível recuperar o payload: %s", exc)
            try:
                record = db_store.get_print_job(job_id=QuickPrintDialog._last_job_id)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Não foi possível recuperar metadados do job: %s", exc)
        if payload is None:
            payload = QuickPrintDialog._last_payload
        if payload is None:
            QMessageBox.information(
                self,
                "Nenhuma impressão",
                "Nenhum trabalho rápido foi enviado ainda.",
            )
            return

        printer = self._current_printer() or QuickPrintDialog._last_printer
        backend = QuickPrintDialog._last_backend
        template_name = QuickPrintDialog._last_template
        if record:
            record_backend = (
                record.get("template_backend") or record.get("printer_backend")
            )
            if isinstance(record_backend, str) and record_backend:
                backend = record_backend
            record_template = record.get("template_name")
            if isinstance(record_template, str) and record_template:
                template_name = record_template
        target_printer = printer or QuickPrintDialog._last_printer

        transport = WindowsSpoolerTransport(target_printer)
        target = PrinterTarget(
            name=target_printer,
            backend=backend,
            transport="win32",
            send=transport.send,
            logger=logger,
        )

        media_settings = QuickPrintDialog._last_media_settings
        if record:
            raw_settings = record.get("media_settings")
            if isinstance(raw_settings, Mapping):
                media_settings = raw_settings
            elif isinstance(raw_settings, (bytes, bytearray, memoryview)):
                try:
                    media_settings = json.loads(raw_settings.decode("utf-8"))
                except Exception:  # pragma: no cover - defensive
                    media_settings = media_settings
            elif isinstance(raw_settings, str):
                try:
                    media_settings = json.loads(raw_settings)
                except Exception:  # pragma: no cover - defensive
                    media_settings = media_settings

        try:
            job_id, status = enqueue_job(
                template_name,
                payload,
                target,
                copies=self.copies_spin.value(),
                params={
                    "template_backend": backend,
                    "printer_backend": backend,
                    "printer_transport": "win32",
                    "media_settings": media_settings,
                },
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Falha ao reenfileirar impressão rápida")
            self._update_status("Erro ao reimprimir", "#f6ad55")
            QMessageBox.critical(
                self,
                "Erro na reimpressão",
                f"Não foi possível reenfileirar o trabalho:\n{exc}",
            )
            return

        QuickPrintDialog._last_job_id = job_id
        QuickPrintDialog._last_payload = payload
        QuickPrintDialog._last_printer = target_printer
        QuickPrintDialog._last_media_settings = media_settings

        status_text = str(status or "pending").lower()
        if status_text == "failed":
            self._update_status("Erro ao reimprimir", "#f6ad55")
            QMessageBox.critical(
                self,
                "Erro na reimpressão",
                "Não foi possível iniciar o trabalho de reimpressão.",
            )
            return

        message = f"Reimpressão enfileirada (#{job_id})"
        color = "#63b3ed" if status_text != "done" else "#9ae6b4"
        self._update_status(message, color)

    def _show_preview(self, template, variables: Mapping[str, Any]) -> bool:
        if ImageQt is None:
            QMessageBox.warning(
                self,
                "Pré-visualização",
                "Pré-visualização indisponível: instale Pillow.",
            )
            return False
        context = dict(variables)
        items = context.pop("items", None)
        if isinstance(items, list) and items:
            first = items[0]
            if isinstance(first, Mapping):
                context.update(first)

        try:
            image = render_template(
                {
                    "page": template.document.page,
                    "elements": template.document.elements,
                },
                context,
                calibration=template.calibration,
            )
        except Exception as exc:
            logger.exception("Falha ao renderizar pré-visualização rápida")
            QMessageBox.warning(self, "Pré-visualização", str(exc))
            return False

        qt_image = ImageQt(image)
        pixmap = QPixmap.fromImage(qt_image)
        if pixmap.width() > 600:
            pixmap = pixmap.scaledToWidth(600, Qt.SmoothTransformation)
        preview = QDialog(self)
        preview.setWindowTitle("Pré-visualização")
        preview.setModal(True)
        preview.setAttribute(Qt.WA_DeleteOnClose, True)
        preview.setStyleSheet("background-color:#1b1b1b;")
        layout = QVBoxLayout(preview)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        label = QLabel()
        label.setAlignment(Qt.AlignCenter)
        label.setPixmap(pixmap)
        layout.addWidget(label)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(preview.accept)
        buttons.rejected.connect(preview.reject)
        layout.addWidget(buttons)

        return preview.exec_() == QDialog.Accepted

    def _update_status(self, message: str, color: str) -> None:
        self.status_label.setText(message)
        self.status_label.setStyleSheet(f"color:{color};font-size:12px;")


__all__ = ["QuickPrintDialog"]
