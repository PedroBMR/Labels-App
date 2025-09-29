from __future__ import annotations

from typing import Any

import pytest

try:
    from qt_compat import QApplication
except ModuleNotFoundError:  # pragma: no cover - environment without Qt
    pytest.skip("Qt bindings are not installed", allow_module_level=True)

import ui
from db import store as db_store
from ui import ConfigDialog


def _ensure_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture(autouse=True)
def _configure_store(tmp_path):
    db_store.configure_default_path(tmp_path / "app.sqlite")


def _base_settings() -> dict[str, Any]:
    return {
        "ultima_impressora": "IMP_A",
        "retry_automatico": False,
        "backup_horario": "17:10",
        "media_type": "gap",
        "media_gap_mm": 2.0,
        "media_gap_offset_mm": 0.2,
        "media_mark_mm": 2.0,
        "media_mark_offset_mm": 0.2,
        "media_speed": 0,
        "media_darkness": 0,
        "media_fine_offset_mm": 0.0,
        "media_calibrate_next": False,
    }


def test_config_dialog_switches_printer_profiles(monkeypatch):
    _ensure_app()

    db_store.save_printer_profile(
        "IMP_A",
        {
            "media_type": "gap",
            "media_gap_mm": 3.5,
            "media_gap_offset_mm": 0.4,
            "media_mark_mm": 3.5,
            "media_mark_offset_mm": 0.4,
            "media_speed": 6,
            "media_darkness": 10,
            "media_fine_offset_mm": 0.3,
            "media_calibrate_next": True,
        },
    )
    db_store.save_printer_profile(
        "IMP_B",
        {
            "media_type": "black_mark",
            "media_gap_mm": 2.0,
            "media_gap_offset_mm": 0.2,
            "media_mark_mm": 8.1,
            "media_mark_offset_mm": 1.7,
            "media_speed": 9,
            "media_darkness": 18,
            "media_fine_offset_mm": -0.6,
            "media_calibrate_next": False,
        },
    )

    monkeypatch.setattr(ui, "listar_impressoras", lambda: ["IMP_A", "IMP_B"])
    monkeypatch.setattr(ui, "listar_templates", lambda: ["Modelo"])
    monkeypatch.setattr(ui, "descobrir_impressora_padrao", lambda: "IMP_A")

    dialog = ConfigDialog(None, _base_settings())
    try:
        dialog._preparar_campos()

        assert dialog.printer_combo.currentText() == "IMP_A"
        assert dialog.media_type_combo.currentData() == "gap"
        assert dialog.media_size_spin.value() == pytest.approx(3.5)
        assert dialog.media_offset_spin.value() == pytest.approx(0.4)
        assert dialog.media_speed_spin.value() == 6
        assert dialog.media_darkness_spin.value() == 10
        assert dialog.media_fine_offset_spin.value() == pytest.approx(0.3)
        assert dialog.media_calibrate_check.isChecked()

        dialog.printer_combo.setCurrentIndex(1)
        QApplication.processEvents()

        assert dialog.printer_combo.currentText() == "IMP_B"
        assert dialog.media_type_combo.currentData() == "black_mark"
        assert dialog.media_size_spin.value() == pytest.approx(8.1)
        assert dialog.media_offset_spin.value() == pytest.approx(1.7)
        assert dialog.media_speed_spin.value() == 9
        assert dialog.media_darkness_spin.value() == 18
        assert dialog.media_fine_offset_spin.value() == pytest.approx(-0.6)
        assert not dialog.media_calibrate_check.isChecked()
    finally:
        dialog.close()


def test_config_dialog_accept_persists_profiles(monkeypatch):
    _ensure_app()

    monkeypatch.setattr(ui, "listar_impressoras", lambda: ["IMP_A", "IMP_B"])
    monkeypatch.setattr(ui, "listar_templates", lambda: ["Modelo"])
    monkeypatch.setattr(ui, "descobrir_impressora_padrao", lambda: "IMP_A")

    dialog = ConfigDialog(None, _base_settings())
    try:
        dialog._preparar_campos()

        dialog.media_type_combo.setCurrentIndex(0)
        dialog.media_size_spin.setValue(4.2)
        dialog.media_offset_spin.setValue(0.9)
        dialog.media_speed_spin.setValue(7)
        dialog.media_darkness_spin.setValue(15)
        dialog.media_fine_offset_spin.setValue(0.25)
        dialog.media_calibrate_check.setChecked(True)

        config_a = dialog.obter_config()
        profile_a = db_store.load_printer_profile("IMP_A")

        assert config_a["ultima_impressora"] == "IMP_A"
        assert config_a["media_gap_mm"] == pytest.approx(4.2)
        assert config_a["media_gap_offset_mm"] == pytest.approx(0.9)
        assert config_a["media_speed"] == 7
        assert config_a["media_darkness"] == 15
        assert config_a["media_fine_offset_mm"] == pytest.approx(0.25)
        assert config_a["media_calibrate_next"] is True
        assert profile_a is not None
        assert profile_a["media_gap_mm"] == pytest.approx(4.2)
        assert profile_a["media_calibrate_next"] is True

        dialog.printer_combo.setCurrentIndex(1)
        QApplication.processEvents()

        dialog.media_type_combo.setCurrentIndex(1)
        dialog.media_size_spin.setValue(6.8)
        dialog.media_offset_spin.setValue(1.1)
        dialog.media_speed_spin.setValue(5)
        dialog.media_darkness_spin.setValue(9)
        dialog.media_fine_offset_spin.setValue(-0.3)
        dialog.media_calibrate_check.setChecked(False)

        config_b = dialog.obter_config()
        profile_b = db_store.load_printer_profile("IMP_B")

        assert config_b["ultima_impressora"] == "IMP_B"
        assert config_b["media_type"] == "black_mark"
        assert config_b["media_mark_mm"] == pytest.approx(6.8)
        assert config_b["media_mark_offset_mm"] == pytest.approx(1.1)
        assert config_b["media_speed"] == 5
        assert config_b["media_darkness"] == 9
        assert config_b["media_fine_offset_mm"] == pytest.approx(-0.3)
        assert config_b["media_calibrate_next"] is False
        assert profile_b is not None
        assert profile_b["media_mark_mm"] == pytest.approx(6.8)
        assert profile_b["media_mark_offset_mm"] == pytest.approx(1.1)
        assert profile_b["media_type"] == "black_mark"

        profile_a_again = db_store.load_printer_profile("IMP_A")
        assert profile_a_again is not None
        assert profile_a_again["media_gap_mm"] == pytest.approx(4.2)
    finally:
        dialog.close()
