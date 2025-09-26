from types import SimpleNamespace

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
    QuickPrintDialog._last_template = None
    sent: list[tuple[str | None, bytes]] = []

    monkeypatch.setattr(quick_print, "listar_templates", lambda: ["Modelo"])
    monkeypatch.setattr(quick_print, "listar_impressoras", lambda: [])
    monkeypatch.setattr(quick_print, "compile_model_silent", lambda *a, **k: b"")
    monkeypatch.setattr(
        quick_print,
        "prepare_quick_job",
        lambda *a, **k: (SimpleNamespace(document=SimpleNamespace(page={}, elements=[]), calibration=None), {}),
    )

    def fake_send(printer, payload, **kwargs):
        sent.append((printer, payload))
        return True, None, 1

    monkeypatch.setattr(quick_print, "send", fake_send)

    QuickPrintDialog._last_payload = b"PRINT"
    QuickPrintDialog._last_printer = "Impressora X"
    QuickPrintDialog._last_job_id = None

    dialog = QuickPrintDialog()
    try:
        dialog._on_reprint_last()
        assert sent and sent[0] == ("Impressora X", b"PRINT")
    finally:
        dialog.close()


def test_quick_print_print_sends_payload(monkeypatch):
    _ensure_app()
    QuickPrintDialog._last_payload = None
    QuickPrintDialog._last_printer = None
    sent: list[tuple[str | None, bytes]] = []

    monkeypatch.setattr(quick_print, "listar_templates", lambda: ["Modelo"])
    monkeypatch.setattr(quick_print, "listar_impressoras", lambda: ["IMP"])

    def fake_prepare(model, overrides, silent=True):
        return SimpleNamespace(document=SimpleNamespace(page={}, elements=[]), calibration=None), overrides

    monkeypatch.setattr(quick_print, "prepare_quick_job", fake_prepare)
    monkeypatch.setattr(quick_print, "compile_model_silent", lambda *a, **k: b"PRINT 1\r\n")

    def fake_send(printer, payload, **kwargs):
        sent.append((printer, payload))
        return True, None, 42

    monkeypatch.setattr(quick_print, "send", fake_send)

    dialog = QuickPrintDialog()
    try:
        dialog.model_combo.setCurrentIndex(0)
        dialog.printer_combo.setCurrentIndex(1)
        dialog.preview_check.setChecked(False)
        dialog._on_print()

        assert sent and sent[0] == ("IMP", b"PRINT 1\r\n")
        assert QuickPrintDialog._last_payload == b"PRINT 1\r\n"
        assert QuickPrintDialog._last_job_id == 42
    finally:
        dialog.close()
