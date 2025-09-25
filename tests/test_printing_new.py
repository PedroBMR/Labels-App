from __future__ import annotations

import pytest

from compile import Calibration
from model.template import TemplateDocument, TemplateVariable
from printing import (
    Printer,
    PrinterConfig,
    Template,
    apply_calibration_adjustment,
    apply_media_settings,
    build_calibration_template,
    build_label_series,
    compile_model_silent,
    compile_template,
    resolve_media_settings,
    prepare_quick_job,
)


class StubTransport:
    def __init__(self) -> None:
        self.payloads: list[bytes] = []

    def send(self, payload: bytes) -> None:
        self.payloads.append(payload)


def _simple_template() -> Template:
    document = TemplateDocument(
        name="demo",
        page={"backend": "tspl", "width_mm": 40, "height_mm": 20, "gap_mm": 2},
        elements=[
            {
                "type": "text",
                "x_mm": 2,
                "y_mm": 2,
                "font": {"name": "3", "x": 1, "y": 1},
                "content": "Ola {nome}",
            }
        ],
        variables={
            "items": TemplateVariable(name="items", scope="template", required=True),
            "nome": TemplateVariable(name="nome", default=""),
        },
    )
    return Template(document)


def test_build_label_series_generates_sequence():
    dados = {
        "volumes": 3,
        "inicio_indice": 5,
        "total_exibicao": 10,
        "nome": "Fulano",
    }
    series = build_label_series(dados)
    assert [ctx["numero"] for ctx in series] == [5, 6, 7]
    assert all(ctx["total"] == 10 for ctx in series)
    assert series[0]["logo"]


def test_printer_print_template_uses_transport():
    template = _simple_template()
    config = PrinterConfig(backend="tspl", transport="tcp", host="127.0.0.1")
    printer = Printer(config)
    stub = StubTransport()
    printer.transport = stub

    ok, error = printer.print_template(template, {"nome": "Mundo", "volumes": 1})
    assert ok and error is None
    assert stub.payloads, "nenhum payload enviado"
    texto = stub.payloads[0].decode("cp1252")
    assert "Ola Mundo" in texto


def test_printer_print_calibration(monkeypatch):
    config = PrinterConfig(backend="tspl", transport="tcp", host="127.0.0.1")
    printer = Printer(config)
    stub = StubTransport()
    printer.transport = stub

    ok, error = printer.print_calibration(square_mm=30)
    assert ok and error is None
    texto = stub.payloads[0].decode("cp1252")
    assert "BOX" in texto


def test_build_calibration_template_compiles_tspl():
    template = build_calibration_template(square_mm=40, backend="tspl")
    backend_name, commands = compile_template(template, {})
    assert backend_name == "tspl"
    assert isinstance(commands, bytes)
    assert b"BOX" in commands


def test_apply_calibration_adjustment_updates_scales():
    original = Calibration(scale_x=1.0, scale_y=1.0)
    adjusted = apply_calibration_adjustment(original, 48.0, 52.0, square_mm=50.0)
    assert adjusted.scale_x == pytest.approx(50.0 / 48.0)
    assert adjusted.scale_y == pytest.approx(50.0 / 52.0)


def test_compile_template_explicit_backend():
    template = _simple_template()
    backend_name, commands = compile_template(
        template,
        {"items": [{"nome": "Joao"}]},
        backend_name="tspl",
    )
    assert backend_name == "tspl"
    assert isinstance(commands, bytes)
    assert b"Joao" in commands


def test_prepare_quick_job_provides_defaults():
    template, variables = prepare_quick_job("100x30")
    assert template.name
    assert variables["copies"] == 1
    assert isinstance(variables.get("items"), list)
    assert variables["items"]


def test_compile_model_silent_returns_bytes():
    payload = compile_model_silent("100x30")
    assert isinstance(payload, bytes)
    assert b"PRINT" in payload.upper()


def test_resolve_media_settings_includes_speed_and_darkness():
    settings = resolve_media_settings(
        {
            "media_type": "black_mark",
            "media_gap_mm": 2.5,
            "media_gap_offset_mm": 0.4,
            "media_mark_mm": 7.2,
            "media_mark_offset_mm": 1.1,
            "media_fine_offset_mm": 0.3,
            "media_calibrate_next": True,
            "media_speed": 6,
            "media_darkness": 13,
        }
    )

    assert settings["media_type"] == "black_mark"
    assert settings["speed"] == 6
    assert settings["density"] == 13
    assert settings["darkness"] == 13
    assert settings["print_rate"] == "6"
    assert settings["calibrate_next_print"] is True


def test_apply_media_settings_updates_speed_and_darkness():
    template = _simple_template()
    updated = apply_media_settings(
        template,
        {
            "media_type": "gap",
            "gap_mm": 2.0,
            "gap_offset_mm": 0.1,
            "mark_mm": 3.0,
            "mark_offset_mm": 0.2,
            "speed": 5,
            "density": 11,
            "print_rate": "7",
            "calibrate_next_print": True,
        },
    )

    page = updated.document.page
    assert page["speed"] == 5
    assert page["density"] == 11
    assert page["darkness"] == 11
    assert page["print_rate"] == "7"
    assert page["print_speed"] == "7"
    assert page["calibrate_next_print"] is True
