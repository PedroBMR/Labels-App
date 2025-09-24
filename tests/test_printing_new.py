from __future__ import annotations

import pytest

from compile import Calibration
from model.template import TemplateDocument, TemplateVariable

from printing import (
    Printer,
    PrinterConfig,
    Template,
    apply_calibration_adjustment,
    build_calibration_template,
    build_label_series,
    compile_template,
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
    assert "BOX" in commands


def test_apply_calibration_adjustment_updates_scales():
    original = Calibration(scale_x=1.0, scale_y=1.0)
    adjusted = apply_calibration_adjustment(original, 48.0, 52.0, square_mm=50.0)
    assert adjusted.scale_x == pytest.approx(50.0 / 48.0)
    assert adjusted.scale_y == pytest.approx(50.0 / 52.0)


def test_compile_template_explicit_backend():
    template = _simple_template()
    backend_name, commands = compile_template(template, {"items": [{"nome": "Joao"}]}, backend_name="tspl")
    assert backend_name == "tspl"
    assert "Joao" in commands
