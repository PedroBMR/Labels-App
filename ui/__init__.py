"""Elementos da interface gráfica do gerador de etiquetas.

Responsabilidade principal da interface de impressão.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from functools import partial
from typing import Any, Callable, Mapping, TypedDict

from _version import __version__
from db import store as db_store
from editor.window import LabelEditorWindow
from log import LOG_FILE, logger, register_status_callback
from model.template import TemplateDocument
from quick_print import QuickPrintDialog
from persistence import (
    atualizar_recentes,
    carregar_config,
    carregar_contagem,
    carregar_historico_mensal,
    carregar_recentes_listas,
    gerar_relatorio_mensal,
    registrar_contagem_mensal,
    salvar_config,
    salvar_contagem,
)
from printing import (
    Template,
    aplicar_template,
    apply_media_settings,
    descobrir_impressora_padrao,
    export_labels,
    Printer,
    PrinterConfig,
    imprimir_pagina_teste,
    listar_impressoras,
    listar_templates,
    montar_tspl,
    resolve_media_settings,
)
from printing.queue import PrinterTarget, enqueue_job
from qt_compat import (
    QCheckBox,
    QCloseEvent,
    QColor,
    QComboBox,
    QDateTime,
    QDesktopServices,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFont,
    QFormLayout,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QIcon,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QObject,
    QPalette,
    QPixmap,
    QPushButton,
    QRegularExpression,
    QRegularExpressionValidator,
    QShortcut,
    QSizePolicy,
    QSpacerItem,
    QSpinBox,
    Qt,
    QKeySequence,
    QTime,
    QTimeEdit,
    QTimer,
    QToolButton,
    QUrl,
    QVBoxLayout,
    QWidget,
    QThread,
    pyqtSignal,
    pyqtSlot,
)
from template_store import template_store
from utils import backup_automatico, normalize_text, recurso_caminho
from ui.print_history import PrintHistoryWidget

CATEGORIAS_PADRAO = [
    "LIMPEZA, COPA, COZINHA",
    "DEVOLUCAO",
    "ORTOPEDICO",
    "CRE CHOPIM",
    "EXPEDIENTE",
    "OSTOMIA",
    "CURATIVOS",
    "LIMPEZA",
    "NUTRIÇAO",
    "MEDICAMENTO",
    "AMBULATORIAL",
    "ODONTO",
]

EMISSORES_PADRAO = [
    "FERNANDO",
    "DANIELA",
    "RUDINEY",
    "ELIZANGELA",
    "DANIELA E RUDINEY",
    "DANIELA E ELIZANGELA",
    "RUDINEY E ELIZANGELA",
    "DANIELA, RUDINEY E ELIZANGELA",
    "LUAN",
    "LUCAS",
    "ANDREY",
    "LUAN E LUCAS",
    "LUAN E ANDREY",
    "LUCAS E ANDREY",
    "LUAN, LUCAS E ANDREY",
    "PEDRO LUIZ",
]

MUNICIPIOS_PADRAO = [
    "ABELARDO LUZ",
    "BOM SUCESSO DO SUL",
    "CAIBI",
    "CAMPO ERE",
    "CHOPINZINHO",
    "CRE CHOPIN",
    "CLEVELANDIA",
    "CORONEL DOMINGOS SOARES",
    "CORONEL MARTINS",
    "CORONEL VIVIDA",
    "FORMOSA DO SUL",
    "GALVAO",
    "HONORIO SERPA",
    "IPUACU",
    "IRATI",
    "ITAPEJARA D' OESTE",
    "JUPIA",
    "MANGUEIRINHA",
    "MARIOPOLIS",
    "NOVO HORIZONTE",
    "OURO VERDE",
    "PALMA SOLA",
    "PALMAS",
    "PATO BRANCO",
    "SANTIAGO DO SUL",
    "SAO BERNARDINO",
    "SAO JOAO",
    "SAO LOURENCO DO OESTE",
    "SAUDADE DO IGUACU",
    "SULINA",
    "VITORINO",
]


class _DatabaseWorker(QObject):
    finished = pyqtSignal(str, object, object)
    error = pyqtSignal(str, Exception, object)

    def __init__(
        self,
        action: str,
        function: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        context: dict[str, Any] | None,
    ) -> None:
        super().__init__()
        self._action = action
        self._function = function
        self._args = args
        self._kwargs = kwargs
        self._context = context or {}

    @pyqtSlot()
    def run(self) -> None:
        try:
            result = self._function(*self._args, **self._kwargs)
        except Exception as exc:  # pragma: no cover - defensive
            self.error.emit(self._action, exc, self._context)
        else:
            self.finished.emit(self._action, result, self._context)


class ConfigDialog(QDialog):
    """Janela de configurações do aplicativo."""

    def __init__(self, parent: QWidget, settings: dict[str, Any]):
        super().__init__(parent)
        self.setWindowTitle("Configurações")
        layout = QVBoxLayout(self)

        self._settings = settings
        self._status_callback: Callable[[str, str], None] | None = None
        if parent is not None:
            status_cb = getattr(parent, "_atualizar_status", None)
            if callable(status_cb):
                self._status_callback = status_cb
        self._active_threads: list[QThread] = []
        self._workers: dict[QThread, _DatabaseWorker] = {}
        self.destroyed.connect(lambda *_: self._teardown_workers())

        self._db_path = db_store.default_db_path()

        db_group = QGroupBox("Banco de dados")
        db_layout = QGridLayout(db_group)
        db_layout.setColumnStretch(1, 1)

        self.db_path_label = QLabel()
        self.db_path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.db_size_label = QLabel()
        self.db_size_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        db_layout.addWidget(QLabel("Arquivo:"), 0, 0)
        db_layout.addWidget(self.db_path_label, 0, 1, 1, 2)
        db_layout.addWidget(QLabel("Tamanho:"), 1, 0)
        db_layout.addWidget(self.db_size_label, 1, 1, 1, 2)

        button_row = QHBoxLayout()
        self.backup_button = QPushButton("Backup…")
        self.vacuum_button = QPushButton("Vacuum")
        self.integrity_button = QPushButton("Integrity Check")

        button_row.addWidget(self.backup_button)
        button_row.addWidget(self.vacuum_button)
        button_row.addWidget(self.integrity_button)
        button_row.addStretch(1)

        db_layout.addLayout(button_row, 2, 0, 1, 3)

        layout.addWidget(db_group)

        self._gap_size = float(settings.get("media_gap_mm", 2.0) or 0.0)
        self._gap_offset = float(settings.get("media_gap_offset_mm", 0.0) or 0.0)
        self._mark_size = float(settings.get("media_mark_mm", self._gap_size) or 0.0)
        self._mark_offset = float(
            settings.get("media_mark_offset_mm", self._gap_offset) or 0.0
        )
        self._default_gap_size = float(self._gap_size)
        self._default_gap_offset = float(self._gap_offset)
        self._default_mark_size = float(self._mark_size)
        self._default_mark_offset = float(self._mark_offset)

        form = QFormLayout()
        self.printer_combo = QComboBox()
        self.printer_combo.setEditable(True)
        self.printer_combo.currentTextChanged.connect(self._on_printer_changed)
        form.addRow("Impressora:", self.printer_combo)

        self.template_combo = QComboBox()
        form.addRow("Modelo:", self.template_combo)

        self.retry_check = QCheckBox("Repetir automaticamente em falha (3x)")
        self.retry_check.setChecked(bool(settings.get("retry_automatico")))
        form.addRow("Repetir em falha:", self.retry_check)

        self.time_edit = QTimeEdit()
        horario = settings.get("backup_horario", "17:10")
        hora = QTime.fromString(str(horario), "HH:mm")
        if not hora.isValid():
            hora = QTime(17, 10)
        self.time_edit.setDisplayFormat("HH:mm")
        self.time_edit.setTime(hora)
        form.addRow("Horário backup:", self.time_edit)

        layout.addLayout(form)

        self.backup_button.clicked.connect(self._on_backup_clicked)
        self.vacuum_button.clicked.connect(self._on_vacuum_clicked)
        self.integrity_button.clicked.connect(self._on_integrity_clicked)
        self._refresh_db_info()

        media_group = QGroupBox("Configurações da mídia")
        media_form = QFormLayout(media_group)

        self.media_type_combo = QComboBox()
        self.media_type_combo.addItem("Gap (web)", "gap")
        self.media_type_combo.addItem("Marca preta", "black_mark")

        self.media_size_label = QLabel()
        self.media_offset_label = QLabel()
        self.media_size_spin = QDoubleSpinBox()
        self.media_size_spin.setRange(0.0, 100.0)
        self.media_size_spin.setDecimals(2)
        self.media_size_spin.setSingleStep(0.1)

        self.media_offset_spin = QDoubleSpinBox()
        self.media_offset_spin.setRange(-50.0, 50.0)
        self.media_offset_spin.setDecimals(2)
        self.media_offset_spin.setSingleStep(0.1)

        self.media_speed_spin = QSpinBox()
        self.media_speed_spin.setRange(0, 20)
        self.media_speed_spin.setSpecialValueText("Padrão")
        try:
            self.media_speed_spin.setValue(
                int(float(settings.get("media_speed", 0) or 0))
            )
        except (TypeError, ValueError):
            self.media_speed_spin.setValue(0)
        self._default_media_speed = int(self.media_speed_spin.value())

        self.media_darkness_spin = QSpinBox()
        self.media_darkness_spin.setRange(0, 30)
        self.media_darkness_spin.setSpecialValueText("Padrão")
        try:
            self.media_darkness_spin.setValue(
                int(
                    float(
                        settings.get(
                            "media_darkness",
                            settings.get("density", settings.get("darkness", 0)),
                        )
                        or 0
                    )
                )
            )
        except (TypeError, ValueError):
            self.media_darkness_spin.setValue(0)
        self._default_media_darkness = int(self.media_darkness_spin.value())

        self.media_fine_offset_spin = QDoubleSpinBox()
        self.media_fine_offset_spin.setRange(-20.0, 20.0)
        self.media_fine_offset_spin.setDecimals(2)
        self.media_fine_offset_spin.setSingleStep(0.05)
        self.media_fine_offset_spin.setValue(
            float(settings.get("media_fine_offset_mm", 0.0) or 0.0)
        )
        self._default_media_fine_offset = float(self.media_fine_offset_spin.value())

        media_type = str(settings.get("media_type", "gap") or "gap").lower()
        idx = self.media_type_combo.findData(
            "black_mark" if media_type in {"black_mark", "blackmark", "mark"} else "gap"
        )
        if idx >= 0:
            self.media_type_combo.setCurrentIndex(idx)
        self._default_media_type = str(self.media_type_combo.currentData())

        self.media_calibrate_check = QCheckBox("Calibrar na próxima impressão")
        self.media_calibrate_check.setChecked(bool(settings.get("media_calibrate_next")))
        self._default_media_calibrate = bool(self.media_calibrate_check.isChecked())

        media_form.addRow("Tipo de mídia:", self.media_type_combo)
        media_form.addRow(self.media_size_label, self.media_size_spin)
        media_form.addRow(self.media_offset_label, self.media_offset_spin)
        media_form.addRow("Velocidade (ips):", self.media_speed_spin)
        media_form.addRow("Escuridão/densidade:", self.media_darkness_spin)
        media_form.addRow("Ajuste fino (mm):", self.media_fine_offset_spin)
        media_form.addRow(self.media_calibrate_check)

        layout.addWidget(media_group)

        self.media_type_combo.currentIndexChanged.connect(self._update_media_fields)
        self.media_size_spin.valueChanged.connect(self._store_media_values)
        self.media_offset_spin.valueChanged.connect(self._store_media_values)
        self._update_media_fields()

        botoes = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)

    def showEvent(self, event: QCloseEvent) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, self._preparar_campos)

    def _refresh_db_info(self) -> None:
        self._db_path = db_store.default_db_path()
        self.db_path_label.setText(str(self._db_path))
        try:
            if self._db_path.exists():
                size = self._db_path.stat().st_size
                self.db_size_label.setText(self._format_size(size))
            else:
                self.db_size_label.setText("Arquivo não encontrado")
        except OSError:
            self.db_size_label.setText("Erro ao ler tamanho")

    @staticmethod
    def _format_size(size: int) -> str:
        if size < 1024:
            return f"{size} B"
        units = ["KB", "MB", "GB", "TB"]
        value = float(size)
        for unit in units:
            value /= 1024.0
            if value < 1024.0:
                return f"{value:.2f} {unit}"
        return f"{value:.2f} PB"

    def _set_db_buttons_enabled(self, enabled: bool) -> None:
        self.backup_button.setEnabled(enabled)
        self.vacuum_button.setEnabled(enabled)
        self.integrity_button.setEnabled(enabled)

    def _emit_status(self, message: str, color: str) -> None:
        if self._status_callback is None:
            return
        try:
            self._status_callback(message, color)
        except TypeError:
            self._status_callback(message)

    def _describe_action(self, action: str) -> str:
        descriptions = {
            "backup": "o backup",
            "vacuum": "o vacuum",
            "integrity": "a verificação de integridade",
        }
        return descriptions.get(action, action)

    def _submit_db_task(
        self,
        action: str,
        function: Callable[..., Any],
        *args: Any,
        context: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        self._set_db_buttons_enabled(False)
        self._start_worker(action, function, args, kwargs, context)

    def _start_worker(
        self,
        action: str,
        function: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        context: dict[str, Any] | None,
    ) -> None:
        worker = _DatabaseWorker(action, function, args, kwargs, context)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(partial(self._handle_worker_success, thread, worker))
        worker.error.connect(partial(self._handle_worker_error, thread, worker))
        self._active_threads.append(thread)
        self._workers[thread] = worker
        thread.start()

    def _handle_worker_success(
        self,
        thread: QThread | None,
        worker: _DatabaseWorker | None,
        action: str,
        result: object,
        context: object,
    ) -> None:
        self._cleanup_worker(thread, worker)
        self._set_db_buttons_enabled(True)
        payload = context if isinstance(context, dict) else {}
        if action == "backup":
            out_path = payload.get("out_path")
            message = "💾 Backup concluído"
            if out_path:
                message = f"{message} ({out_path})"
                logger.info("Backup do banco de dados salvo em %s", out_path)
            else:
                logger.info("Backup do banco de dados concluído")
            self._emit_status(message, "lightblue")
        elif action == "vacuum":
            self._emit_status("🧹 Vacuum concluído", "lightgreen")
            logger.info("Vacuum do banco de dados concluído")
        elif action == "integrity":
            ok = bool(result)
            if ok:
                self._emit_status("✅ Banco de dados íntegro", "lightgreen")
                logger.info("Verificação de integridade do banco concluída sem erros")
            else:
                self._emit_status("⚠️ Banco de dados com inconsistências", "orange")
                logger.error(
                    "Verificação de integridade do banco encontrou inconsistências"
                )
        self._refresh_db_info()

    def _handle_worker_error(
        self,
        thread: QThread | None,
        worker: _DatabaseWorker | None,
        action: str,
        error: Exception,
        context: object,
    ) -> None:
        self._cleanup_worker(thread, worker)
        self._set_db_buttons_enabled(True)
        description = self._describe_action(action)
        message = f"⚠️ Erro ao executar {description}"
        self._emit_status(message, "orange")
        logger.error("Falha ao executar %s: %s", description, error)
        QMessageBox.critical(
            self,
            "Banco de dados",
            f"Não foi possível executar {description} do banco de dados.\n\n{error}",
        )
        self._refresh_db_info()

    def _cleanup_worker(
        self,
        thread: QThread | None,
        worker: _DatabaseWorker | None,
    ) -> None:
        if thread is None:
            return
        managed_worker = worker or self._workers.pop(thread, None)
        if thread in self._active_threads:
            self._active_threads.remove(thread)
        thread.quit()
        thread.wait(2000)
        thread.deleteLater()
        if managed_worker is not None:
            managed_worker.deleteLater()

    def _teardown_workers(self) -> None:
        for thread in list(self._active_threads):
            worker = self._workers.pop(thread, None)
            self._cleanup_worker(thread, worker)
        self._active_threads.clear()
        self._workers.clear()

    def _on_backup_clicked(self) -> None:
        self._refresh_db_info()
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        default_name = f"{self._db_path.stem}-{timestamp}.sqlite"
        initial_path = str(self._db_path.with_name(default_name))
        out_path, _ = QFileDialog.getSaveFileName(
            self,
            "Salvar backup do banco de dados",
            initial_path,
            "SQLite (*.sqlite);;Todos os arquivos (*)",
        )
        if not out_path:
            self._set_db_buttons_enabled(True)
            return
        save_path = Path(out_path)
        context = {"out_path": save_path}
        self._submit_db_task(
            "backup",
            db_store.backup,
            self._db_path,
            save_path,
            context=context,
        )

    def _on_vacuum_clicked(self) -> None:
        self._refresh_db_info()
        self._submit_db_task("vacuum", db_store.vacuum, self._db_path)

    def _on_integrity_clicked(self) -> None:
        self._refresh_db_info()
        self._submit_db_task("integrity", db_store.integrity_check, self._db_path)

    def _preparar_campos(self) -> None:
        self._preencher_impressoras()
        self._preencher_templates()

    def _preencher_impressoras(self) -> None:
        self.printer_combo.clear()
        impressoras = listar_impressoras()
        if impressoras:
            self.printer_combo.addItems(impressoras)

        preferida = str(self._settings.get("ultima_impressora", "")).strip()
        if not preferida:
            preferida = descobrir_impressora_padrao() or ""

        if preferida:
            idx = self.printer_combo.findText(preferida)
            if idx >= 0:
                self.printer_combo.setCurrentIndex(idx)
            else:
                self.printer_combo.setEditText(preferida)
        elif self.printer_combo.isEditable():
            self.printer_combo.clearEditText()

        self._load_selected_printer_profile()

    def _preencher_templates(self) -> None:
        self.template_combo.clear()
        self.template_combo.addItems(listar_templates())
        preferido = self._settings.get("template", "")
        idx = self.template_combo.findText(preferido)
        if idx >= 0:
            self.template_combo.setCurrentIndex(idx)

    def _update_media_fields(self) -> None:
        current = str(self.media_type_combo.currentData())
        label_gap = current == "gap"
        self.media_size_label.setText(
            "Tamanho do gap (mm):" if label_gap else "Comprimento da marca (mm):"
        )
        self.media_offset_label.setText(
            "Offset do gap (mm):" if label_gap else "Offset da marca (mm):"
        )

        self.media_size_spin.blockSignals(True)
        self.media_offset_spin.blockSignals(True)
        try:
            if label_gap:
                self.media_size_spin.setValue(self._gap_size)
                self.media_offset_spin.setValue(self._gap_offset)
            else:
                self.media_size_spin.setValue(self._mark_size)
                self.media_offset_spin.setValue(self._mark_offset)
        finally:
            self.media_size_spin.blockSignals(False)
            self.media_offset_spin.blockSignals(False)

    def _store_media_values(self) -> None:
        current = str(self.media_type_combo.currentData())
        if current == "gap":
            self._gap_size = self.media_size_spin.value()
            self._gap_offset = self.media_offset_spin.value()
        else:
            self._mark_size = self.media_size_spin.value()
            self._mark_offset = self.media_offset_spin.value()

    def _on_printer_changed(self, _: str) -> None:
        self._load_selected_printer_profile()

    def _load_selected_printer_profile(self) -> None:
        printer = self.printer_combo.currentText().strip()
        profile: Mapping[str, Any] | None = None
        if printer:
            try:
                profile = db_store.load_printer_profile(printer)
            except Exception:  # pragma: no cover - defensive logging
                logger.exception("Falha ao carregar perfil da impressora %s", printer)
                profile = None
        self._apply_profile_settings(profile)

    def _apply_profile_settings(self, profile: Mapping[str, Any] | None) -> None:
        data = dict(profile) if profile else {}

        def _coerce_float(value: Any, default: float) -> float:
            try:
                return float(value)
            except (TypeError, ValueError):
                return default

        def _coerce_int(value: Any, default: int) -> int:
            try:
                return int(float(value))
            except (TypeError, ValueError):
                return default

        self._gap_size = _coerce_float(data.get("media_gap_mm"), self._default_gap_size)
        self._gap_offset = _coerce_float(
            data.get("media_gap_offset_mm"), self._default_gap_offset
        )
        self._mark_size = _coerce_float(data.get("media_mark_mm"), self._default_mark_size)
        self._mark_offset = _coerce_float(
            data.get("media_mark_offset_mm"), self._default_mark_offset
        )

        media_type = str(data.get("media_type", self._default_media_type) or "gap").lower()
        media_type = "black_mark" if media_type in {"black_mark", "blackmark", "mark"} else "gap"
        current_type = str(self.media_type_combo.currentData())
        if media_type != current_type:
            block = self.media_type_combo.blockSignals(True)
            try:
                idx = self.media_type_combo.findData(media_type)
                if idx >= 0:
                    self.media_type_combo.setCurrentIndex(idx)
            finally:
                self.media_type_combo.blockSignals(block)

        speed = data.get("media_speed")
        if speed in (None, ""):
            speed_value = self._default_media_speed
        else:
            speed_value = _coerce_int(speed, self._default_media_speed)
        self.media_speed_spin.setValue(speed_value)

        darkness = data.get("media_darkness", data.get("darkness"))
        if darkness in (None, ""):
            darkness_value = self._default_media_darkness
        else:
            darkness_value = _coerce_int(darkness, self._default_media_darkness)
        self.media_darkness_spin.setValue(darkness_value)

        fine_offset_value = _coerce_float(
            data.get("media_fine_offset_mm"), self._default_media_fine_offset
        )
        self.media_fine_offset_spin.setValue(fine_offset_value)

        calibrate = bool(data.get("media_calibrate_next", self._default_media_calibrate))
        self.media_calibrate_check.setChecked(calibrate)

        self._update_media_fields()

    def obter_config(self) -> dict[str, Any]:
        self._store_media_values()
        profile_settings = {
            "media_type": str(self.media_type_combo.currentData()),
            "media_gap_mm": float(self._gap_size),
            "media_gap_offset_mm": float(self._gap_offset),
            "media_mark_mm": float(self._mark_size),
            "media_mark_offset_mm": float(self._mark_offset),
            "media_speed": int(self.media_speed_spin.value()),
            "media_darkness": int(self.media_darkness_spin.value()),
            "media_fine_offset_mm": float(self.media_fine_offset_spin.value()),
            "media_calibrate_next": bool(self.media_calibrate_check.isChecked()),
        }

        printer = self.printer_combo.currentText().strip()
        if printer:
            try:
                db_store.save_printer_profile(printer, profile_settings)
            except Exception:  # pragma: no cover - defensive logging
                logger.exception("Falha ao salvar perfil da impressora %s", printer)

        config = {
            "ultima_impressora": printer,
            "template": self.template_combo.currentText(),
            "retry_automatico": self.retry_check.isChecked(),
            "backup_horario": self.time_edit.time().toString("HH:mm"),
        }
        config.update(profile_settings)
        return config


class EtiquetaInfo(TypedDict):
    saida: int
    categoria: str
    emissor: str
    municipio: str
    volumes: int
    data_hora: str
    template: str  # <- modelo usado na impressão
    job_id: int | None


class EtiquetaApp(QWidget):
    """Janela principal do gerador de etiquetas."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Gerador de Etiquetas CONIMS")
        # tamanho inicial (aplicado já aqui, e reforçado no showEvent)
        self.resize(600, 800)
        self.setWindowIcon(QIcon(recurso_caminho("color.png")))
        self.config = carregar_config()
        self.contagem_total, self.contagem_mensal = carregar_contagem()
        self.ultima_etiqueta: EtiquetaInfo | None = None
        self._ultimo_job_id: int | None = None
        self._pending_jobs: dict[int, dict[str, Any]] = {}
        self._job_poll_timer = QTimer(self)
        self._job_poll_timer.setInterval(1500)
        self._job_poll_timer.timeout.connect(self._poll_pending_jobs)

        self._impressao_template: str | None = None  # <- lembra o modelo usado
        self._template: Template | None = None
        self._tem_impressora: bool | None = None
        self._editor_window: LabelEditorWindow | None = None
        self._quick_print_dialog: QuickPrintDialog | None = None
        self._quick_shortcut: QShortcut | None = None

        # Estilo base precisa existir antes de sinais dispararem
        self._input_style_base = (
            "background:#191919;color:#e5e5e5;padding:7px;"
            "border:1px solid #282828;border-radius: 6px;font-size: 14px;"
        )
        self._ui_ready = False
        self._contagem_label = QLabel()
        self._contagem_label.setStyleSheet(
            "color: #CCCCCC; font-size: 15px; font-weight: 500; padding: 8px; "
            "letter-spacing: 1px;"
        )
        self._atualizar_contagem_label()

        self._logo_pixmap: QPixmap | None = None
        logo_path = recurso_caminho("color.png")
        if os.path.exists(logo_path):
            self._logo_pixmap = QPixmap(logo_path).scaledToWidth(
                120, Qt.SmoothTransformation
            )

        self._setup_ui()
        self._aplicar_tema_escuro()
        self._registrar_logger_ui()

        # Validação dinâmica
        self._wire_validation_signals()
        self._ui_ready = True
        self._update_print_button_state()

        self._atualizar_status("🟢 Pronto")
        QTimer.singleShot(0, self._agendar_backup_diario)
        QTimer.singleShot(0, self._verificar_impressora)

        template_store.templateSaved.connect(self._on_template_saved)

        self._printer_refresh_timer = QTimer(self)
        self._printer_refresh_timer.setInterval(60000)
        self._printer_refresh_timer.timeout.connect(self._verificar_impressora)
        self._printer_refresh_timer.start()

        # flag para aplicar o tamanho/centralização só uma vez após mostrar
        self._aplicou_tamanho_inicial = False

    # --- garante 600x1080 e centraliza DEPOIS que o layout calculou tudo ---
    def showEvent(self, event: QCloseEvent) -> None:
        super().showEvent(event)
        if not getattr(self, "_aplicou_tamanho_inicial", False):
            # reaplica para vencer size hints dos filhos
            self.resize(600, 800)
            # centraliza na tela disponível (desconta barra de tarefas)
            geo = self.frameGeometry()
            centro = self.screen().availableGeometry().center()
            geo.moveCenter(centro)
            self.move(geo.topLeft())
            self._aplicou_tamanho_inicial = True
            QTimer.singleShot(0, self._carregar_templates)
            QTimer.singleShot(
                0,
                lambda: self._aplicar_template(self.template_input.currentText()),
            )
            QTimer.singleShot(0, self._carregar_listas)

    def _agendar_backup_diario(self) -> None:
        horario = str(self.config.get("backup_horario", "17:10"))
        try:
            horas, minutos = [int(x) for x in horario.split(":", 1)]
        except Exception:
            horas, minutos = 17, 10

        agora = QDateTime.currentDateTime()
        fim_do_dia = QDateTime(agora.date(), QTime(horas, minutos, 0))
        if agora > fim_do_dia:
            fim_do_dia = fim_do_dia.addDays(1)
        ms_ate_backup = agora.msecsTo(fim_do_dia)

        if hasattr(self, "_timer_backup"):
            self._timer_backup.stop()
        self._timer_backup = QTimer(self)
        self._timer_backup.setSingleShot(True)
        self._timer_backup.timeout.connect(self._executar_backup_diario)
        self._timer_backup.start(ms_ate_backup)

    def _executar_backup_diario(self) -> None:
        backup_automatico()
        self._agendar_backup_diario()

    def closeEvent(self, event: QCloseEvent) -> None:
        backup_automatico()
        event.accept()

    def _setup_ui(self) -> None:
        layout_base = QVBoxLayout(self)
        layout_base.setContentsMargins(0, 0, 0, 0)
        layout_base.addSpacerItem(
            QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding)
        )

        layout_central = QVBoxLayout()
        layout_central.setAlignment(Qt.AlignTop)
        layout_central.setContentsMargins(50, 30, 50, 30)
        layout_central.setSpacing(20)
        layout_base.addLayout(layout_central)

        # Logo e título
        logo_area = QVBoxLayout()
        logo_area.setAlignment(Qt.AlignCenter)
        logo_label = QLabel()
        logo_label.setAlignment(Qt.AlignCenter)
        logo_path = recurso_caminho("color.png")
        if os.path.exists(logo_path) and self._logo_pixmap is None:
            self._logo_pixmap = QPixmap(logo_path).scaledToWidth(
                120, Qt.SmoothTransformation
            )
        if self._logo_pixmap is not None:
            logo_label.setPixmap(self._logo_pixmap)
        logo_area.addWidget(logo_label)
        titulo = QLabel("Gerador de Etiquetas CONIMS")
        titulo.setFont(QFont("Segoe UI", 14, QFont.Bold))
        titulo.setAlignment(Qt.AlignCenter)
        logo_area.addWidget(titulo)
        layout_central.addLayout(logo_area)
        layout_central.addWidget(self._contagem_label)

        # Formulário
        quadro = QFrame()
        quadro.setStyleSheet(
            "QFrame{background:#232323;border-radius:12px;border: 1px solid #333;}"
        )
        layout_quadro = QVBoxLayout(quadro)
        layout_quadro.setContentsMargins(40, 30, 40, 30)
        layout_central.addWidget(quadro)

        self.print_history = PrintHistoryWidget(self)
        self.print_history.reprintRequested.connect(self._reprint_from_history)
        layout_central.addWidget(self.print_history)

    def _refresh_print_history(self) -> None:
        if hasattr(self, "print_history") and self.print_history is not None:
            self.print_history.refresh()

    def _register_pending_job(self, job_id: int | None, context: dict[str, Any]) -> None:
        if job_id is None:
            return
        self._pending_jobs[job_id] = context
        if not self._job_poll_timer.isActive():
            self._job_poll_timer.start()

    def _poll_pending_jobs(self) -> None:
        if not self._pending_jobs:
            if self._job_poll_timer.isActive():
                self._job_poll_timer.stop()
            return

        finished: list[int] = []
        for job_id, context in list(self._pending_jobs.items()):
            try:
                record = db_store.get_print_job(job_id=job_id)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Falha ao consultar status do job %s: %s", job_id, exc)
                continue
            if not record:
                continue
            status = str(record.get("status") or "").lower()
            if status in {"done", "failed"}:
                self._handle_job_completion(job_id, status, record, context)
                finished.append(job_id)

        for job_id in finished:
            self._pending_jobs.pop(job_id, None)

        if not self._pending_jobs and self._job_poll_timer.isActive():
            self._job_poll_timer.stop()

    def _handle_job_completion(
        self,
        job_id: int,
        status: str,
        record: Mapping[str, Any],
        context: dict[str, Any],
    ) -> None:
        if status == "done":
            self._on_job_success(job_id, record, context)
        else:
            self._on_job_failure(job_id, record, context)
        self._refresh_print_history()

    def _on_job_success(
        self,
        job_id: int,
        record: Mapping[str, Any],
        context: dict[str, Any],
    ) -> None:
        kind = context.get("kind")
        if kind == "primary":
            try:
                volumes = int(context.get("volumes") or 0)
            except (TypeError, ValueError):
                volumes = 0
            if volumes:
                self.contagem_total += volumes
                self.contagem_mensal += volumes
                salvar_contagem(self.contagem_total, self.contagem_mensal)
                mes_atual = datetime.now().strftime("%m-%Y")
                registrar_contagem_mensal(mes_atual, volumes)
                self._atualizar_contagem_label()

            try:
                saida = int(context.get("saida") or 0)
            except (TypeError, ValueError):
                saida = 0
            categoria = str(context.get("categoria") or "")
            emissor = str(context.get("emissor") or "")
            municipio = str(context.get("municipio") or "")
            data_hora = str(context.get("data_hora") or "")
            template = str(
                context.get("template")
                or self._impressao_template
                or self.template_input.currentText().strip()
                or ""
            )

            self.ultima_etiqueta = EtiquetaInfo(
                saida=saida,
                categoria=categoria,
                emissor=emissor,
                municipio=municipio,
                volumes=volumes,
                data_hora=data_hora,
                template=template,
                job_id=job_id,
            )

            if context.get("update_recent"):
                self._atualizar_listas_recentes(categoria, emissor, municipio)

            message = str(context.get("success_message") or "✅ Impressão concluída")
            self._atualizar_status(message, "lightgreen")
            QTimer.singleShot(30000, self._limpar_campos)
        else:
            try:
                increment = int(context.get("increment_counts") or 0)
            except (TypeError, ValueError):
                increment = 0
            if increment:
                self.contagem_total += increment
                self.contagem_mensal += increment
                salvar_contagem(self.contagem_total, self.contagem_mensal)
                self._atualizar_contagem_label()

            message = str(context.get("success_message") or "♻️ Reimpressão concluída")
            self._atualizar_status(message, "lightblue")
            if self.ultima_etiqueta is not None:
                self.ultima_etiqueta["job_id"] = job_id

        self._ultimo_job_id = job_id

    def _on_job_failure(
        self,
        job_id: int,
        record: Mapping[str, Any],
        context: dict[str, Any],
    ) -> None:
        error_text = str(record.get("error_text") or "Erro desconhecido")
        message = str(context.get("error_message") or "⚠️ Erro na impressão")
        display_message = message
        if error_text:
            display_message = f"{message} ({error_text})"
        self._atualizar_status(display_message, "orange")
        title = "Reimpressão" if context.get("kind") == "reprint" else "Impressão"
        if context.get("show_error_dialog", True):
            QMessageBox.critical(self, title, error_text)
        logger.error("Trabalho de impressão %s falhou: %s", job_id, error_text)

    def _resend_job(
        self,
        job_id: int,
        *,
        success_message: str,
        error_message: str,
        count_increment: int = 0,
        update_last_label: bool = True,
        show_error_dialog: bool = True,
    ) -> int | None:
        record = db_store.get_print_job(job_id=job_id)
        if record is None:
            QMessageBox.warning(
                self,
                "Reimpressão",
                "Não foi possível localizar o trabalho de impressão selecionado.",
            )
            return None

        payload = db_store.get_job_payload(job_id=job_id)
        if payload is None:
            QMessageBox.warning(
                self,
                "Reimpressão",
                "O comando original desta impressão não está disponível.",
            )
            return None

        raw_settings = record.get("media_settings")
        media_settings = None
        if isinstance(raw_settings, str) and raw_settings:
            try:
                media_settings = json.loads(raw_settings)
            except json.JSONDecodeError:
                media_settings = None

        transport = str(record.get("printer_transport") or "win32")
        backend = str(
            record.get("printer_backend")
            or record.get("template_backend")
            or "tspl"
        )
        template_backend = (
            str(record.get("template_backend"))
            if record.get("template_backend")
            else backend
        )

        config = PrinterConfig(
            backend=backend,
            transport=transport,
            printer_name=str(record.get("printer_name") or "") or None,
        )

        if config.transport.lower() == "tcp":
            host = record.get("printer_host")
            port = record.get("printer_port")
            if host:
                config.host = str(host)
            if port:
                try:
                    config.port = int(port)
                except (TypeError, ValueError):
                    pass

        try:
            printer = Printer(config, logger=logger)
        except Exception as exc:
            logger.exception("Falha ao preparar reimpressão")
            QMessageBox.critical(
                self,
                "Reimpressão",
                f"Não foi possível preparar a impressora selecionada:\n{exc}",
            )
            return None

        target = PrinterTarget(
            name=config.printer_name,
            backend=config.backend,
            transport=config.transport,
            send=printer.transport.send,
            logger=logger,
        )

        params = {
            "template_backend": template_backend,
            "printer_backend": config.backend,
            "printer_transport": config.transport,
            "media_settings": media_settings,
        }

        template_name = str(record.get("template_name") or "") or None

        try:
            novo_job, status = enqueue_job(template_name, payload, target, copies=1, params=params)
        except Exception as exc:
            logger.exception("Erro ao reenfileirar trabalho salvo")
            QMessageBox.critical(
                self,
                "Reimpressão",
                f"Não foi possível enfileirar o trabalho selecionado:\n{exc}",
            )
            return None

        status_text = str(status or "pending").lower()
        if status_text == "failed":
            self._atualizar_status(error_message, "orange")
            if show_error_dialog:
                QMessageBox.critical(
                    self,
                    "Reimpressão",
                    "Não foi possível iniciar o trabalho de reimpressão.",
                )
            return None

        pending_message = f"🕒 Trabalho reenfileirado (#{novo_job})"
        self._atualizar_status(pending_message, "lightblue")

        context = {
            "kind": "reprint",
            "success_message": success_message,
            "error_message": error_message,
            "increment_counts": count_increment,
            "show_error_dialog": show_error_dialog,
        }
        self._register_pending_job(novo_job, context)

        if update_last_label and self.ultima_etiqueta is not None:
            self.ultima_etiqueta["job_id"] = novo_job
        self._ultimo_job_id = novo_job
        self._refresh_print_history()

        if status_text in {"done", "failed"}:
            record = db_store.get_print_job(job_id=novo_job)
            if record:
                self._handle_job_completion(novo_job, status_text, record, context)
                self._pending_jobs.pop(novo_job, None)

        return novo_job

    def _reprint_from_history(self, job_id: int) -> None:
        self._resend_job(
            job_id,
            success_message="♻️ Reimpressão reenviada",
            error_message="⚠️ Erro na reimpressão",
        )

        grid = QGridLayout()
        layout_quadro.addLayout(grid)

        self.saida_input = QLineEdit()
        self.saida_input.setValidator(
            QRegularExpressionValidator(QRegularExpression(r"\d*"))
        )
        self.saida_input.returnPressed.connect(self._imprimir_etiqueta)

        self.categoria_input = QComboBox()
        self.categoria_input.setEditable(True)
        self.categoria_input.lineEdit().returnPressed.connect(self._imprimir_etiqueta)

        self.emissor_input = QComboBox()
        self.emissor_input.setEditable(True)
        self.emissor_input.lineEdit().returnPressed.connect(self._imprimir_etiqueta)

        self.municipio_input = QComboBox()
        self.municipio_input.setEditable(True)
        self.municipio_input.lineEdit().returnPressed.connect(self._imprimir_etiqueta)

        self.volumes_input = QSpinBox()
        self.volumes_input.setMinimum(1)
        self.volumes_input.lineEdit().returnPressed.connect(self._imprimir_etiqueta)
        self.template_input = QComboBox()
        self.template_input.currentTextChanged.connect(self._aplicar_template)
        self.template_input.currentTextChanged.connect(self._salvar_template_config)
        self.template_input.currentTextChanged.connect(self._update_print_button_state)

        self.toggle_template_btn = QPushButton("Alternar modelo")
        self.toggle_template_btn.clicked.connect(self._toggle_template)

        # Estilo base para inputs (reaplicado nas validações)
        def _estilo(w):
            w.setStyleSheet(self._input_style_base)

        for w in (
            self.saida_input,
            self.categoria_input,
            self.emissor_input,
            self.municipio_input,
            self.volumes_input,
            self.template_input,
        ):
            _estilo(w)

        def _lbl(texto: str) -> QLabel:
            label = QLabel(texto)
            label.setStyleSheet(
                "color: #bbb; font-size: 13px; border: none; background: none;"
            )
            return label

        grid.addWidget(_lbl("Saída:"), 0, 0)
        grid.addWidget(self.saida_input, 0, 1)
        grid.addWidget(_lbl("Categoria:"), 1, 0)
        grid.addWidget(self.categoria_input, 1, 1)
        grid.addWidget(_lbl("Emissor:"), 2, 0)
        grid.addWidget(self.emissor_input, 2, 1)
        grid.addWidget(_lbl("Município:"), 3, 0)
        grid.addWidget(self.municipio_input, 3, 1)
        grid.addWidget(_lbl("Número de Volumes:"), 4, 0)
        grid.addWidget(self.volumes_input, 4, 1)
        grid.addWidget(_lbl("Modelo:"), 5, 0)
        grid.addWidget(self.template_input, 5, 1)
        grid.addWidget(self.toggle_template_btn, 5, 2)

        self.retry_checkbox = QCheckBox("Repetir automaticamente em falha (3x)")
        self.retry_checkbox.setStyleSheet(
            "color: #bbb; font-size: 13px; padding: 5px; border: none;"
        )
        self.retry_checkbox.setChecked(bool(self.config.get("retry_automatico")))
        self.retry_checkbox.stateChanged.connect(self._salvar_retry_config)
        layout_quadro.addWidget(self.retry_checkbox)

        # Botões
        botoes = QGridLayout()
        self.imprimir_btn = QPushButton("Imprimir\nAgora")
        self.imprimir_btn.setDefault(True)
        self.imprimir_btn.clicked.connect(self._imprimir_etiqueta)

        self.reimprimir_btn = QPushButton("Reimprimir\nÚltima")
        self.reimprimir_btn.clicked.connect(self._reimprimir_ultima)

        self.cancelar_btn = QPushButton("Cancelar")
        self.cancelar_btn.clicked.connect(self._cancelar_impressao)

        self.editor_btn = QPushButton("Edição de\nEtiqueta")
        self.editor_btn.clicked.connect(self._abrir_editor_etiqueta)

        self.exportar_btn = QPushButton("Exportar\nEtiqueta")
        export_menu = QMenu(self.exportar_btn)
        export_menu.addAction(
            "Como PNG…", lambda: self._exportar_etiqueta("png", batch=False)
        )
        export_menu.addAction(
            "Como PDF…", lambda: self._exportar_etiqueta("pdf", batch=False)
        )
        export_menu.addAction(
            "Como SVG…", lambda: self._exportar_etiqueta("svg", batch=False)
        )
        lote_menu = export_menu.addMenu("Exportar lote")
        lote_menu.addAction(
            "PNG…", lambda: self._exportar_etiqueta("png", batch=True)
        )
        lote_menu.addAction(
            "PDF…", lambda: self._exportar_etiqueta("pdf", batch=True)
        )
        lote_menu.addAction(
            "SVG…", lambda: self._exportar_etiqueta("svg", batch=True)
        )
        self.exportar_btn.setMenu(export_menu)

        self.menu_btn = QToolButton()
        self.menu_btn.setIcon(QIcon(recurso_caminho("menu-aberto.png")))
        self.menu_btn.setAutoRaise(True)  # remove relevo
        self.menu_btn.setStyleSheet("border: none;")  # evita moldura/ fundo
        self.menu_btn.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(self.menu_btn)
        self.menu_btn.setMenu(menu)

        ac_faltantes = menu.addAction(
            "Reimprimir Faltantes", self._reimprimir_faltantes
        )
        ac_faltantes.setShortcut("Ctrl+F")
        ac_intervalo = menu.addAction(
            "Reimprimir Intervalo…", self._reimprimir_intervalo
        )
        ac_intervalo.setShortcut("Ctrl+I")
        ac_hist = menu.addAction("Abrir Histórico", self._abrir_historico)
        ac_hist.setShortcut("Ctrl+H")
        ac_hist_mes = menu.addAction("Histórico Mensal", self._mostrar_historico_mensal)
        ac_hist_mes.setShortcut("Ctrl+M")
        ac_relatorio = menu.addAction(
            "Exportar relatório do mês atual", self._exportar_relatorio_mes_atual
        )
        ac_relatorio.setShortcut("Ctrl+E")
        ac_log = menu.addAction("Ver Log", self._abrir_log)
        ac_log.setShortcut("Ctrl+L")
        ac_teste = menu.addAction("Imprimir página de teste", self._imprimir_teste)
        ac_teste.setShortcut("Ctrl+T")
        ac_config = menu.addAction("Configurações", self._abrir_configuracoes)
        ac_config.setShortcut("Ctrl+,")
        ac_verificar = menu.addAction("Testar conexão", self._verificar_impressora)
        ac_verificar.setShortcut("F5")
        ac_quick = menu.addAction(
            "Impressão Rápida (F6)", self._abrir_impressao_rapida
        )
        ac_quick.setShortcut("F6")

        self._quick_shortcut = QShortcut(QKeySequence("F6"), self)
        self._quick_shortcut.activated.connect(self._abrir_impressao_rapida)

        for b in (
            self.imprimir_btn,
            self.reimprimir_btn,
            self.cancelar_btn,
            self.editor_btn,
            self.exportar_btn,
        ):
            b.setStyleSheet(
                "background:#24292e;color:#eeeeee;padding:8px 18px;border-radius:6px;"
                "font-size: 14px;border: none;",
            )

        self.cancelar_btn.setStyleSheet(
            "background:#24292e;color:#ff5555;padding:8px 18px;border-radius:6px;"
            "font-size: 14px;border: none;",
        )

        botoes.addWidget(self.imprimir_btn, 0, 0)
        botoes.addWidget(self.reimprimir_btn, 0, 1)
        botoes.addWidget(self.exportar_btn, 0, 2)
        botoes.addWidget(self.cancelar_btn, 1, 0)
        botoes.addWidget(self.menu_btn, 1, 1)
        botoes.addWidget(self.editor_btn, 2, 0, 1, 3)

        layout_quadro.addLayout(botoes)

        # Status
        self.status_label = QLabel()
        self.status_label.setStyleSheet(
            "color: #8bc34a; font-size: 13px; border: none; background: none; "
            "padding: 5px;"
        )
        layout_quadro.addWidget(self.status_label)

        layout_base.addSpacerItem(
            QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding)
        )

        self._footer_label = QLabel(
            "Feito por Pedro Luiz Bortot Monteiro do Rosário 2025 — "
            f"Versão {__version__}"
        )
        self._footer_label.setAlignment(Qt.AlignCenter)
        self._footer_label.setStyleSheet(
            "color: #555; font-size: 12px; border: none; "
            "background: none; padding: 10px;"
        )
        layout_base.addWidget(self._footer_label)

    def _aplicar_tema_escuro(self) -> None:
        p = QPalette()
        p.setColor(QPalette.Window, QColor(30, 30, 30))
        p.setColor(QPalette.WindowText, Qt.white)
        p.setColor(QPalette.Base, QColor(45, 45, 45))
        p.setColor(QPalette.Text, Qt.white)
        p.setColor(QPalette.Button, QColor(45, 45, 45))
        p.setColor(QPalette.ButtonText, Qt.white)
        self.setPalette(p)

    # =========================
    # Validação dinâmica
    # =========================
    def _wire_validation_signals(self) -> None:
        self.saida_input.textChanged.connect(self._update_print_button_state)
        for combo in (self.categoria_input, self.emissor_input, self.municipio_input):
            combo.currentTextChanged.connect(self._update_print_button_state)
            if combo.isEditable() and combo.lineEdit() is not None:
                combo.lineEdit().textChanged.connect(self._update_print_button_state)
        self.volumes_input.valueChanged.connect(self._update_print_button_state)

    def _is_form_valid(self) -> tuple[bool, str]:
        saida_ok = bool(self.saida_input.text().strip())
        cat_ok = bool(self.categoria_input.currentText().strip())
        emi_ok = bool(self.emissor_input.currentText().strip())
        mun_ok = bool(self.municipio_input.currentText().strip())
        vol_ok = self.volumes_input.value() >= 1

        if not saida_ok:
            return False, "Preencha o campo 'Saída'."
        if not cat_ok:
            return False, "Preencha o campo 'Categoria'."
        if not emi_ok:
            return False, "Preencha o campo 'Emissor'."
        if not mun_ok:
            return False, "Preencha o campo 'Município'."
        if not vol_ok:
            return False, "O campo 'Número de Volumes' deve ser ≥ 1."
        return True, ""

    def _apply_field_highlights(self) -> None:
        base = getattr(
            self,
            "_input_style_base",
            (
                "background:#191919;color:#e5e5e5;padding:7px;border:1px solid "
                "#282828;border-radius: 6px;font-size: 14px;"
            ),
        )

        def mark(widget, bad: bool):
            widget.setStyleSheet(base + ("border:1px solid #ff4d4d;" if bad else ""))

        saida_bad = not bool(self.saida_input.text().strip())
        cat_bad = not bool(self.categoria_input.currentText().strip())
        emi_bad = not bool(self.emissor_input.currentText().strip())
        mun_bad = not bool(self.municipio_input.currentText().strip())
        vol_bad = self.volumes_input.value() < 1

        mark(self.saida_input, saida_bad)
        mark(self.categoria_input, cat_bad)
        mark(self.emissor_input, emi_bad)
        mark(self.municipio_input, mun_bad)
        mark(self.volumes_input, vol_bad)

    def _update_print_button_state(self) -> None:
        # Evita rodar antes de a UI terminar de montar
        if not getattr(self, "_ui_ready", False):
            return
        ok, _ = self._is_form_valid()
        self._apply_field_highlights()
        tem_imp = bool(self._tem_impressora)
        if hasattr(self, "imprimir_btn"):
            self.imprimir_btn.setEnabled(ok and tem_imp)

    # =========================
    # Listas e normalização
    # =========================
    def _carregar_templates(self) -> None:
        self.template_input.clear()
        self.template_input.addItems(listar_templates())
        preferido = self.config.get("template", "")
        idx_tpl = self.template_input.findText(preferido)
        if idx_tpl < 0:
            idx_tpl = self.template_input.findText("100x30")
            if idx_tpl < 0:
                idx_tpl = self.template_input.findText("60x80")
            if idx_tpl < 0 and self.template_input.count() > 0:
                idx_tpl = 0
        if idx_tpl >= 0:
            self.template_input.setCurrentIndex(idx_tpl)

    def _on_template_saved(self, path: str) -> None:
        self._carregar_templates()
        try:
            document = TemplateDocument.from_file(path)
            name = document.name
        except Exception:
            name = Path(path).stem
        if not name:
            return
        idx = self.template_input.findText(name)
        if idx >= 0:
            self.template_input.setCurrentIndex(idx)

    def _popular_combo(
        self, combo: QComboBox, recentes: list[str], padroes: list[str]
    ) -> None:
        combo.clear()
        combo.addItem("")
        for item in recentes:
            combo.addItem(item)
        for item in padroes:
            if item not in recentes:
                combo.addItem(item)

    def _reordenar_combo(self, combo: QComboBox, recentes: list[str]) -> None:
        atuais = [combo.itemText(i) for i in range(combo.count()) if combo.itemText(i)]
        restantes = [item for item in atuais if item not in recentes]
        combo.clear()
        combo.addItem("")
        combo.addItems(recentes + restantes)

    def _carregar_listas(self) -> None:
        recentes = carregar_recentes_listas()
        self._popular_combo(
            self.categoria_input, recentes.get("categoria", []), CATEGORIAS_PADRAO
        )
        self._popular_combo(
            self.emissor_input, recentes.get("emissor", []), EMISSORES_PADRAO
        )
        self._popular_combo(
            self.municipio_input, recentes.get("municipio", []), MUNICIPIOS_PADRAO
        )
        self._update_print_button_state()

    def _coletar_campos(self) -> tuple[int, str, str, str, int, str]:
        saida_texto = self.saida_input.text().strip()
        saida = int(saida_texto) if saida_texto else 0
        categoria = self.categoria_input.currentText().strip()
        emissor = self.emissor_input.currentText().strip()
        municipio = self.municipio_input.currentText().strip()
        categoria, _ = normalize_text(categoria, max_len=50)
        emissor, _ = normalize_text(emissor, max_len=50)
        municipio, _ = normalize_text(municipio, max_len=50)
        volumes = int(self.volumes_input.value())
        data_hora = datetime.now().strftime("%d/%m/%Y %H:%M")
        return saida, categoria, emissor, municipio, volumes, data_hora

    def _atualizar_listas_recentes(
        self, categoria: str, emissor: str, municipio: str
    ) -> None:
        atualizar_recentes(categoria, emissor, municipio)
        recentes = carregar_recentes_listas()
        self._reordenar_combo(self.categoria_input, recentes.get("categoria", []))
        self._reordenar_combo(self.emissor_input, recentes.get("emissor", []))
        self._reordenar_combo(self.municipio_input, recentes.get("municipio", []))

    def _limpar_campos(self) -> None:
        self.saida_input.clear()
        for combo in (self.categoria_input, self.emissor_input, self.municipio_input):
            combo.setCurrentIndex(0)
        self.volumes_input.setValue(1)
        self._update_print_button_state()

    def _aplicar_template(self, nome: str) -> None:
        try:
            template = aplicar_template(nome)
        except ValueError as e:
            QMessageBox.critical(self, "Erro", str(e))
            return
        base_settings = self._media_settings(consume=False)
        self._template = apply_media_settings(template, base_settings)
        self._impressao_template = nome  # lembra o modelo atual

    def _media_settings(self, *, consume: bool) -> dict[str, Any]:
        printer_hint = str(self.config.get("ultima_impressora", "")).strip() or None
        profile = None
        if printer_hint:
            try:
                profile = db_store.load_printer_profile(printer_hint)
            except Exception:  # pragma: no cover - defensive logging only
                logger.exception(
                    "Falha ao carregar perfil da impressora %s", printer_hint
                )
                profile = None

        settings = resolve_media_settings(self.config, printer_profile=profile)
        calibrate = bool(settings.get("calibrate_next_print"))

        profile_calibrate = False
        if profile:
            raw_flag = None
            for key in ("media_calibrate_next", "calibrate_next", "calibrate_next_print"):
                if key in profile:
                    raw_flag = profile[key]
                    break
            profile_calibrate = bool(raw_flag)

        if consume:
            if calibrate:
                if profile_calibrate and printer_hint:
                    try:
                        db_store.save_printer_profile(
                            printer_hint, {"media_calibrate_next": False}
                        )
                    except Exception:  # pragma: no cover - defensive logging only
                        logger.exception(
                            "Falha ao atualizar calibracao da impressora %s",
                            printer_hint,
                        )
                else:
                    self.config["media_calibrate_next"] = False
                    salvar_config(self.config)
        else:
            settings["calibrate_next_print"] = False
        return settings

    def _refresh_template_media(self) -> None:
        if not self._impressao_template:
            return
        try:
            template = aplicar_template(self._impressao_template)
        except ValueError:
            return
        base_settings = self._media_settings(consume=False)
        self._template = apply_media_settings(template, base_settings)

    def _toggle_template(self) -> None:
        atual = self.template_input.currentText()
        novo = "60x80" if atual == "100x30" else "100x30"
        idx = self.template_input.findText(novo)
        if idx >= 0:
            self.template_input.setCurrentIndex(idx)

    def _abrir_editor_etiqueta(self) -> None:
        if self._editor_window is None:
            self._editor_window = LabelEditorWindow()
            self._editor_window.destroyed.connect(self._editor_window_closed)
        self._editor_window.show()
        self._editor_window.raise_()
        self._editor_window.activateWindow()

    def _editor_window_closed(self, _obj: QObject | None = None) -> None:
        self._editor_window = None

    def _abrir_impressao_rapida(self) -> None:
        if self._quick_print_dialog is None:
            self._quick_print_dialog = QuickPrintDialog(self)
            self._quick_print_dialog.finished.connect(self._quick_print_closed)
            ultima = self.config.get("ultima_impressora")
            if ultima:
                self._quick_print_dialog.set_printer_hint(str(ultima))
        self._quick_print_dialog.show()
        self._quick_print_dialog.raise_()
        self._quick_print_dialog.activateWindow()

    def _quick_print_closed(self, _result: int) -> None:
        if self._quick_print_dialog is not None:
            self._quick_print_dialog.deleteLater()
            self._quick_print_dialog = None

    # =========================
    # Persistência e ações
    # =========================
    def _salvar_template_config(self, texto: str) -> None:
        self.config["template"] = texto
        salvar_config(self.config)

    def _salvar_retry_config(self, estado: int) -> None:
        self.config["retry_automatico"] = bool(estado)
        salvar_config(self.config)

    def _abrir_configuracoes(self) -> None:
        dlg = ConfigDialog(self, self.config)
        if dlg.exec_():
            self.config.update(dlg.obter_config())
            salvar_config(self.config)
            # tenta posicionar no combo o mesmo template salvo
            idx = self.template_input.findText(self.config.get("template", ""))
            if idx >= 0:
                self.template_input.setCurrentIndex(idx)
            self.retry_checkbox.setChecked(bool(self.config.get("retry_automatico")))
            self._agendar_backup_diario()
            self._refresh_template_media()
            self._verificar_impressora()

    def _verificar_impressora(self) -> None:
        nome = descobrir_impressora_padrao()
        self._tem_impressora = nome is not None
        self._update_print_button_state()
        if nome is None:
            self._atualizar_status("⚠️ Nenhuma impressora detectada", "orange")
        else:
            self._atualizar_status("🟢 Pronto")
            self.config["ultima_impressora"] = nome
            salvar_config(self.config)

    def _atualizar_status(
        self, mensagem: str = "🟢 Pronto", cor: str = "white"
    ) -> None:
        self.status_label.setText(mensagem)
        self.status_label.setStyleSheet(f"color:{cor};padding:5px")

    def _registrar_logger_ui(self) -> None:
        def _cb(msg: str) -> None:
            QTimer.singleShot(0, lambda: self._atualizar_status(f"⚠️ {msg}", "orange"))

        register_status_callback(_cb)

    # =========================
    # Ações de impressão e utilitários
    # =========================
    def _abrir_historico(self) -> None:
        self._refresh_print_history()
        if self.print_history is not None:
            self.print_history.setFocus()
        QMessageBox.information(
            self,
            "Histórico",
            "O histórico recente está disponível no painel abaixo.",
        )

    def _imprimir_etiqueta(self) -> None:
        self._update_print_button_state()
        ok, msg = self._is_form_valid()
        if not ok:
            self._atualizar_status("⚠️ Campos obrigatórios", "orange")
            QMessageBox.warning(self, "Campos obrigatórios", msg)
            return

        self._atualizar_status("🖨️ Preparando impressão…")
        (
            saida,
            categoria,
            emissor,
            municipio,
            volumes,
            data_hora,
        ) = self._coletar_campos()

        # pega o modelo exibido no combo (o mesmo que foi aplicado)
        tpl = (
            self.template_input.currentText().strip()
            or (self._impressao_template or "")
        )
        if not tpl:
            QMessageBox.warning(self, "Modelo", "Selecione um modelo de etiqueta.")
            return
        self._impressao_template = tpl  # reforça

        dados = {
            "saida": str(saida),
            "categoria": categoria,
            "emissor": emissor,
            "municipio": municipio,
            "volumes": volumes,
            "data_hora": data_hora,
        }
        if self._template is None:
            QMessageBox.warning(self, "Modelo", "Selecione um modelo de etiqueta.")
            return
        media_settings = self._media_settings(consume=True)
        tspl = montar_tspl(self._template, dados, media_settings)
        logger.debug("TSPL gerado:\n%s", tspl)

        printer_hint = str(self.config.get("ultima_impressora", "")).strip() or None
        config = PrinterConfig(
            backend="tspl",
            transport="win32",
            printer_name=printer_hint,
        )

        try:
            printer = Printer(config, logger=logger)
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Erro ao preparar impressora para impressão principal")
            self._atualizar_status("⚠️ Erro ao preparar impressora", "orange")
            QMessageBox.critical(
                self,
                "Impressão",
                f"Não foi possível preparar a impressora selecionada:\n{exc}",
            )
            return

        payload = printer._prepare_payload(tspl, config.backend, config.encoding)
        target = PrinterTarget(
            name=config.printer_name,
            backend=config.backend,
            transport=config.transport,
            send=printer.transport.send,
            logger=logger,
        )

        params = {
            "template_backend": config.backend,
            "printer_backend": config.backend,
            "printer_transport": config.transport,
            "media_settings": media_settings,
        }

        try:
            job_id, status = enqueue_job(tpl, payload, target, copies=1, params=params)
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Erro ao enfileirar impressão principal")
            self._atualizar_status("⚠️ Erro ao enfileirar impressão", "orange")
            QMessageBox.critical(
                self,
                "Impressão",
                f"Não foi possível enfileirar o trabalho de impressão:\n{exc}",
            )
            return

        self._impressao_template = tpl
        self._ultimo_job_id = job_id
        self.ultima_etiqueta = EtiquetaInfo(
            saida=saida,
            categoria=categoria,
            emissor=emissor,
            municipio=municipio,
            volumes=volumes,
            data_hora=data_hora,
            template=tpl,
            job_id=job_id,
        )

        context = {
            "kind": "primary",
            "saida": saida,
            "categoria": categoria,
            "emissor": emissor,
            "municipio": municipio,
            "volumes": volumes,
            "data_hora": data_hora,
            "template": tpl,
            "media_settings": media_settings,
            "success_message": "✅ Impressão concluída",
            "error_message": "⚠️ Erro na impressão",
            "increment_counts": volumes,
            "update_recent": True,
            "show_error_dialog": True,
        }
        self._register_pending_job(job_id, context)

        status_text = str(status or "pending").lower()
        if status_text == "failed":
            self._atualizar_status("⚠️ Erro ao enfileirar impressão", "orange")
            QMessageBox.critical(
                self,
                "Impressão",
                "Não foi possível iniciar o trabalho de impressão.",
            )
            self._pending_jobs.pop(job_id, None)
            return

        color = "lightgreen" if status_text == "done" else "lightblue"
        self._atualizar_status(f"🕒 Impressão enfileirada (#{job_id})", color)
        self._refresh_print_history()

        if status_text in {"done", "failed"}:
            try:
                record = db_store.get_print_job(job_id=job_id)
            except Exception:  # pragma: no cover - defensive
                record = None
            if record:
                self._handle_job_completion(job_id, status_text, record, context)
                self._pending_jobs.pop(job_id, None)

    def _exportar_etiqueta(self, formato: str, *, batch: bool) -> None:
        self._update_print_button_state()
        ok, msg = self._is_form_valid()
        if not ok:
            QMessageBox.warning(self, "Campos obrigatórios", msg)
            return

        if self._template is None:
            QMessageBox.warning(self, "Modelo", "Selecione um modelo de etiqueta.")
            return

        (
            saida,
            categoria,
            emissor,
            municipio,
            volumes,
            data_hora,
        ) = self._coletar_campos()

        dados = {
            "saida": str(saida),
            "categoria": categoria,
            "emissor": emissor,
            "municipio": municipio,
            "volumes": volumes,
            "data_hora": data_hora,
        }

        filtros = {
            "png": "Imagem PNG (*.png)",
            "pdf": "Documento PDF (*.pdf)",
            "svg": "Imagem SVG (*.svg)",
        }
        formato_norm = formato.lower()
        filtro = filtros.get(formato_norm, "Todos os arquivos (*)")

        sufixo = {
            "png": ".png",
            "pdf": ".pdf",
            "svg": ".svg",
        }.get(formato_norm, ".dat")

        sugestao = f"etiqueta-{saida or datetime.now().strftime('%Y%m%d-%H%M%S')}{sufixo}"
        caminho, _ = QFileDialog.getSaveFileName(
            self,
            "Exportar etiquetas",
            sugestao,
            filtro,
        )
        if not caminho:
            return

        try:
            media_settings = self._media_settings(consume=False)
            caminhos, total = export_labels(
                self._template,
                dados,
                caminho,
                formato_norm,
                media_settings=media_settings,
                batch=batch,
            )
        except Exception as exc:
            logger.exception("Erro na exportação de etiquetas")
            self._atualizar_status("⚠️ Erro na exportação", "orange")
            QMessageBox.critical(
                self,
                "Exportação",
                f"Não foi possível exportar a etiqueta:\n{exc}",
            )
            return

        exportados = len(caminhos)
        destino = Path(caminhos[0])
        if batch:
            if formato_norm == "pdf" and total > 1:
                mensagem = (
                    f"Lote com {total} etiquetas exportado para:\n{destino}"
                )
            elif exportados > 1:
                pasta = destino.parent
                mensagem = (
                    f"{exportados} etiquetas exportadas para a pasta:\n{pasta}"
                )
            else:
                mensagem = f"Etiqueta exportada para:\n{destino}"
        else:
            if total > 1:
                mensagem = (
                    f"Etiqueta exportada para:\n{destino}\n\n"
                    "Apenas a primeira etiqueta do lote foi salva."
                    " Use Exportar lote para gerar todas."
                )
            else:
                mensagem = f"Etiqueta exportada para:\n{destino}"

        self._atualizar_status("💾 Exportação concluída", "lightblue")
        QMessageBox.information(self, "Exportação", mensagem)

    def _cancelar_impressao(self) -> None:
        QMessageBox.information(
            self,
            "Cancelamento",
            "Os trabalhos enviados para a fila não podem ser cancelados "
            "automaticamente. Se necessário, cancele diretamente na impressora.",
        )
        self._atualizar_status("ℹ️ Cancelamento indisponível para a fila", "orange")

    def _imprimir_teste(self) -> None:
        self._atualizar_status("🖨️ Imprimindo teste…")
        if self._template is None:
            QMessageBox.warning(self, "Modelo", "Selecione um modelo de etiqueta.")
            return
        ok, erro, job_id = imprimir_pagina_teste(
            self._template, repetir_em_falha=self.retry_checkbox.isChecked()
        )
        if ok:
            self._ultimo_job_id = job_id
            self._atualizar_status("✅ Página de teste impressa", "lightgreen")
        else:
            self._atualizar_status("⚠️ Erro na impressão de teste", "orange")
            logger.error("Erro na impressão de teste: %s", erro)
            QMessageBox.critical(self, "Erro", f"{erro['code']}: {erro['message']}")

    def _reimprimir_ultima(self) -> None:
        job_id: int | None = None
        if self.ultima_etiqueta is not None:
            maybe = self.ultima_etiqueta.get("job_id")
            if isinstance(maybe, int):
                job_id = maybe
        if job_id is None:
            job_id = self._ultimo_job_id
        if job_id is None:
            QMessageBox.information(
                self, "Nenhuma etiqueta", "Nenhuma etiqueta foi impressa ainda."
            )
            return

        self._resend_job(
            job_id,
            success_message="♻️ Reimpressão concluída",
            error_message="⚠️ Erro na reimpressão",
        )

    def _reimprimir_faltantes(self) -> None:
        if self.ultima_etiqueta is None:
            QMessageBox.information(
                self, "Nenhuma etiqueta", "Nenhuma etiqueta foi impressa ainda."
            )
            return

        dados = self.ultima_etiqueta
        total = int(dados["volumes"])
        job_id = dados.get("job_id") or self._ultimo_job_id
        if job_id is None:
            QMessageBox.information(
                self,
                "Nenhuma etiqueta",
                "O registro da última impressão não está disponível.",
            )
            return

        faltantes, ok = QInputDialog.getInt(
            self,
            "Reimprimir Faltantes",
            f"Quantas etiquetas faltaram desse lote de {total}?",
            1,
            1,
            total,
            1,
        )
        if not ok:
            return

        if faltantes != total:
            resposta = QMessageBox.question(
                self,
                "Reimpressão parcial",
                "Apenas é possível reenviar o trabalho completo. Deseja "
                "reimprimir todas as etiquetas deste lote?",
            )
            if resposta != QMessageBox.Yes:
                return

        self._resend_job(
            int(job_id),
            success_message="♻️ Faltantes reimpressas",
            error_message="⚠️ Erro na reimpressão de faltantes",
            count_increment=total,
        )

    def _reimprimir_intervalo(self) -> None:
        if self.ultima_etiqueta is None:
            QMessageBox.information(
                self, "Nenhuma etiqueta", "Nenhuma etiqueta foi impressa ainda."
            )
            return

        dados = self.ultima_etiqueta
        total = int(dados["volumes"])
        job_id = dados.get("job_id") or self._ultimo_job_id
        if job_id is None:
            QMessageBox.information(
                self,
                "Nenhuma etiqueta",
                "O registro da última impressão não está disponível.",
            )
            return

        intervalo, ok = QInputDialog.getText(
            self,
            "Reimprimir Intervalo",
            f"Informe o intervalo (1-{total}, ex.: 5-8):",
        )
        if not ok or not intervalo:
            return

        try:
            intervalo = intervalo.replace("–", "-").replace(" ", "")
            inicio_str, fim_str = intervalo.split("-")
            inicio = int(inicio_str)
            fim = int(fim_str)
        except ValueError:
            QMessageBox.warning(
                self,
                "Intervalo inválido",
                "Use o formato início-fim, ex.: 5-8.",
            )
            return

        if inicio < 1 or fim > total or inicio > fim:
            QMessageBox.warning(
                self,
                "Intervalo inválido",
                f"O intervalo deve estar entre 1 e {total}.",
            )
            return

        if inicio != 1 or fim != total:
            resposta = QMessageBox.question(
                self,
                "Reimpressão parcial",
                "Só é possível reenviar o trabalho completo pelo histórico. "
                "Deseja reimprimir todas as etiquetas deste lote?",
            )
            if resposta != QMessageBox.Yes:
                return

        self._resend_job(
            int(job_id),
            success_message="♻️ Intervalo reimpresso",
            error_message="⚠️ Erro na reimpressão do intervalo",
        )

    def _abrir_log(self) -> None:
        if not os.path.exists(LOG_FILE):
            QMessageBox.information(
                self, "Log", "O arquivo de log ainda não foi criado."
            )
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(LOG_FILE))

    def _mostrar_historico_mensal(self) -> None:
        hist = carregar_historico_mensal()
        if not hist:
            QMessageBox.information(self, "Histórico Mensal", "Nenhum dado encontrado.")
            return
        texto = "Histórico de Etiquetas por Mês:\n\n"
        for mes, total in sorted(hist.items()):
            texto += f"Mês: {mes}   —   Total: {total}\n"
        QMessageBox.information(self, "Histórico Mensal", texto)

    def _exportar_relatorio_mes_atual(self) -> None:
        mes = datetime.now().strftime("%Y-%m")
        try:
            caminho = gerar_relatorio_mensal(mes)
            QMessageBox.information(
                self,
                "Relatório Mensal",
                f"Relatório salvo em:\n{caminho}",
            )
        except FileNotFoundError:
            QMessageBox.information(
                self,
                "Relatório Mensal",
                "Histórico de impressões não encontrado.",
            )
        except Exception as e:
            logger.exception("Erro ao gerar relatório mensal")
            QMessageBox.critical(self, "Erro", str(e))

    def _atualizar_contagem_label(self) -> None:
        nome_mes = datetime.now().strftime("%m/%Y")
        self._contagem_label.setText(
            "Etiquetas do mês: "
            f"<span style='font-weight:600'>{self.contagem_mensal}</span> "
            "&nbsp;|&nbsp; "
            f"Total geral: <span style='font-weight:600'>{self.contagem_total}</span> "
            f"<span style='color:#888;font-size:13px'>(Mês: {nome_mes})</span>"
        )
