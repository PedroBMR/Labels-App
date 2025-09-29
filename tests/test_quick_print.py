from types import SimpleNamespace
from typing import Any

import pytest

try:
    from qt_compat import QApplication
except ModuleNotFoundError:  # pragma: no cover - environment without Qt
    pytest.skip("Qt bindings are not installed", allow_module_level=True)

import quick_print
from quick_print import QuickPrintDialog

from db import store as db_store


def _ensure_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture(autouse=True)
def _configure_store(tmp_path):
    db_store.configure_default_path(tmp_path / "app.sqlite")


def test_quick_print_updates_templates(monkeypatch):
    _ensure_app()
    QuickPrintDialog._last_payload = None
    QuickPrintDialog._last_printer = None
    QuickPrintDialog._last_job_id = None
    QuickPrintDialog._last_backend = "tspl"
    QuickPrintDialog._last_template = None
    templates = ["Modelo A"]

    def fake_templates() -> list[str]:
        return list(templates)

    monkeypatch.setattr(quick_print, "listar_templates", fake_templates)
    monkeypatch.setattr(quick_print, "listar_impressoras", lambda: [])
    monkeypatch.setattr(quick_print, "compile_model_silent", lambda *a, **k: b"")
    monkeypatch.setattr(
        quick_print,
        "prepare_quick_job",
        lambda *a, **k: (SimpleNamespace(document=SimpleNamespace(page={}, elements=[]), calibration=None), {}),
    )

    dialog = QuickPrintDialog()
    try:
        assert dialog.model_combo.findText("Modelo A") >= 0

        templates.append("Modelo B")
        quick_print.template_store.templateSaved.emit("dummy")
        QApplication.processEvents()

        assert dialog.model_combo.findText("Modelo B") >= 0
    finally:
        dialog.close()


def test_quick_print_reprint_uses_last_payload(monkeypatch):
    _ensure_app()
    QuickPrintDialog._last_payload = None
    QuickPrintDialog._last_printer = None
    QuickPrintDialog._last_job_id = None
    QuickPrintDialog._last_backend = "tspl"
    QuickPrintDialog._last_template = "Modelo"
    QuickPrintDialog._last_media_settings = {"media_type": "gap"}

    monkeypatch.setattr(quick_print, "listar_templates", lambda: ["Modelo"])
    monkeypatch.setattr(quick_print, "listar_impressoras", lambda: [])

    jobs: list[tuple[str | None, bytes, quick_print.PrinterTarget, int, dict]] = []

    def fake_enqueue(template, payload, target, copies, params):
        jobs.append((template, payload, target, copies, dict(params)))
        return 7, "pending"

    monkeypatch.setattr(quick_print, "enqueue_job", fake_enqueue)

    QuickPrintDialog._last_payload = b"PRINT"
    QuickPrintDialog._last_printer = "Impressora X"
    QuickPrintDialog._last_job_id = None

    dialog = QuickPrintDialog()
    try:
        dialog._on_reprint_last()
        assert jobs, "Nenhum job reenfileirado"
        template, payload, target, copies, params = jobs[0]
        assert template == "Modelo"
        assert payload == b"PRINT"
        assert target.name == "Impressora X"
        assert copies == dialog.copies_spin.value()
        assert params.get("media_settings") == {"media_type": "gap"}
    finally:
        dialog.close()


def test_quick_print_print_sends_payload(monkeypatch):
    _ensure_app()
    QuickPrintDialog._last_payload = None
    QuickPrintDialog._last_printer = None
    QuickPrintDialog._last_media_settings = None

    monkeypatch.setattr(quick_print, "listar_templates", lambda: ["Modelo"])
    monkeypatch.setattr(quick_print, "listar_impressoras", lambda: ["IMP"])

    config = {"ultima_impressora": "PADRAO"}
    profile = {"media_speed": 5}
    media_settings = {"media_type": "gap", "calibrate_next_print": False}

    monkeypatch.setattr(quick_print, "carregar_config", lambda: dict(config))
    monkeypatch.setattr(quick_print.db_store, "load_printer_profile", lambda name: profile)

    captured_prepare: dict[str, Any] = {}

    def fake_prepare(model, overrides, *, silent, config, printer_name, printer_profile):
        captured_prepare.update(
            {
                "model": model,
                "overrides": overrides,
                "silent": silent,
                "config": config,
                "printer_name": printer_name,
                "printer_profile": printer_profile,
            }
        )
        return (
            SimpleNamespace(document=SimpleNamespace(page={}, elements=[]), calibration=None),
            overrides,
        )

    monkeypatch.setattr(quick_print, "prepare_quick_job", fake_prepare)

    captured_compile: dict[str, Any] = {}

    def fake_compile(model, overrides, *, silent, printer_name, printer_profile):
        captured_compile.update(
            {
                "model": model,
                "overrides": overrides,
                "silent": silent,
                "printer_name": printer_name,
                "printer_profile": printer_profile,
            }
        )
        return b"PRINT 1\r\n"

    monkeypatch.setattr(quick_print, "compile_model_silent", fake_compile)
    monkeypatch.setattr(quick_print, "resolve_media_settings", lambda *a, **k: dict(media_settings))

    jobs: list[tuple[str | None, bytes, quick_print.PrinterTarget, int, dict]] = []

    def fake_enqueue(template, payload, target, copies, params):
        jobs.append((template, payload, target, copies, dict(params)))
        return 42, "pending"

    monkeypatch.setattr(quick_print, "enqueue_job", fake_enqueue)

    dialog = QuickPrintDialog()
    try:
        dialog.model_combo.setCurrentIndex(0)
        dialog.printer_combo.setCurrentIndex(1)
        dialog.preview_check.setChecked(False)
        dialog._on_print()

        assert jobs, "Nenhum job enfileirado"
        template, payload, target, copies, params = jobs[0]
        assert template == "Modelo"
        assert payload == b"PRINT 1\r\n"
        assert target.name == "IMP"
        assert copies == dialog.copies_spin.value()
        assert params.get("media_settings") == media_settings
        assert QuickPrintDialog._last_payload == b"PRINT 1\r\n"
        assert QuickPrintDialog._last_job_id == 42
        assert QuickPrintDialog._last_media_settings == media_settings
        assert captured_prepare["printer_name"] == "IMP"
        assert captured_prepare["printer_profile"] == profile
        assert captured_prepare["config"] == config
        assert captured_compile["printer_name"] == "IMP"
        assert captured_compile["printer_profile"] == profile
    finally:
        dialog.close()
