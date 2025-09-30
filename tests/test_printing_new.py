from __future__ import annotations

import pytest

from compile import Calibration
from db import store as db_store
from model.template import TemplateDocument, TemplateVariable
from printing import (
    Printer,
    PrinterConfig,
    Template,
    TransportError,
    apply_calibration_adjustment,
    apply_media_settings,
    build_calibration_template,
    build_label_series,
    compile_model_silent,
    compile_template,
    load_csv_items,
    prepare_quick_job,
    prepare_variable_contexts,
    resolve_media_settings,
    wait_for_all_jobs,
)


@pytest.fixture(autouse=True)
def _configure_store(tmp_path):
    db_store.configure_default_path(tmp_path / "app.sqlite")



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


def _template_with_required_template_scope() -> Template:
    document = TemplateDocument(
        name="required_template_scope",
        page={"backend": "tspl", "width_mm": 40, "height_mm": 20, "gap_mm": 2},
        elements=[
            {
                "type": "text",
                "x_mm": 2,
                "y_mm": 2,
                "font": {"name": "3", "x": 1, "y": 1},
                "content": "Titulo: {titulo}",
            }
        ],
        variables={
            "items": TemplateVariable(name="items", scope="template", required=True),
            "titulo": TemplateVariable(
                name="titulo", scope="template", required=True
            ),
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


def _batch_template() -> Template:
    document = TemplateDocument(
        name="batch",
        page={"backend": "tspl", "width_mm": 40, "height_mm": 30, "dpi": 203},
        elements=[
            {
                "type": "text",
                "x_mm": 2,
                "y_mm": 2,
                "content": "{NOME} - {CODIGO}",
            }
        ],
        variables={
            "items": TemplateVariable(name="items", scope="template", required=True),
            "NOME": TemplateVariable(name="NOME", default=""),
            "CODIGO": TemplateVariable(name="CODIGO", default=""),
        },
    )
    return Template(document)


def test_build_label_series_with_items_override():
    template = _batch_template()
    dados = {
        "items": [
            {"NOME": "Ana", "CODIGO": "001"},
            {"NOME": "Bia", "CODIGO": "002"},
        ],
        "inicio_indice": 2,
        "total_exibicao": 5,
    }
    series = build_label_series(dados, template)
    assert [item["NOME"] for item in series] == ["Ana", "Bia"]
    assert [item["numero"] for item in series] == [2, 3]
    assert all(item["total"] == 5 for item in series)


def test_prepare_variable_contexts_combines_template_and_items():
    template = _batch_template()
    dados = {
        "titulo": "Lote Especial",
        "items": [{"NOME": "Ana", "CODIGO": "001"}],
    }
    contexts = prepare_variable_contexts(template, dados)
    assert len(contexts) == 1
    assert contexts[0]["titulo"] == "Lote Especial"
    assert contexts[0]["NOME"] == "Ana"
    assert contexts[0]["CODIGO"] == "001"


def test_load_csv_items_normalises_headers(tmp_path):
    csv_path = tmp_path / "dados.csv"
    csv_path.write_text("Nome;Código\n Ana ; 001 \n", encoding="utf-8")
    items = load_csv_items(csv_path, delimiter=";")
    assert len(items) == 1
    entry = items[0]
    assert entry["Nome"] == "Ana"
    assert entry["nome"] == "Ana"
    assert entry["NOME"] == "Ana"
    assert entry["codigo"] == "001"


def test_printer_print_template_uses_transport():
    template = _simple_template()
    config = PrinterConfig(backend="tspl", transport="tcp", host="127.0.0.1")
    printer = Printer(config)
    stub = StubTransport()
    printer.transport = stub

    ok, status, job_id = printer.print_template(
        template, {"nome": "Mundo", "volumes": 1}
    )
    assert ok and status is not None and status.get("status") == "pending"
    assert job_id is not None
    assert wait_for_all_jobs(2.0)
    assert stub.payloads, "nenhum payload enviado"
    texto = stub.payloads[0].decode("cp1252")
    assert "Ola Mundo" in texto


def test_printer_print_template_allows_template_scope_overrides():
    template = _template_with_required_template_scope()
    config = PrinterConfig(backend="tspl", transport="tcp", host="127.0.0.1")
    printer = Printer(config)
    stub = StubTransport()
    printer.transport = stub

    ok, status, job_id = printer.print_template(
        template,
        {"titulo": "Custom", "volumes": 1},
    )

    assert ok and status is not None and status.get("status") == "pending"
    assert job_id is not None
    assert wait_for_all_jobs(2.0)
    assert stub.payloads, "nenhum payload enviado"
    texto = stub.payloads[0].decode("cp1252")
    assert "Custom" in texto


def test_printer_print_calibration(monkeypatch):
    config = PrinterConfig(backend="tspl", transport="tcp", host="127.0.0.1")
    printer = Printer(config)
    stub = StubTransport()
    printer.transport = stub

    ok, status, job_id = printer.print_calibration(square_mm=30)
    assert ok and status is not None and status.get("status") == "pending"
    assert job_id is not None
    assert wait_for_all_jobs(2.0)
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


def test_resolve_media_settings_prefers_printer_profile():
    config = {
        "media_gap_mm": 2.0,
        "media_gap_offset_mm": 0.1,
        "media_mark_mm": 5.0,
        "media_mark_offset_mm": 0.2,
        "media_speed": 4,
        "media_darkness": 9,
    }
    profile = {
        "media_gap_mm": 3.3,
        "media_mark_mm": 6.6,
        "media_mark_offset_mm": 1.5,
        "media_fine_offset_mm": 0.25,
        "media_calibrate_next": True,
        "media_speed": 8,
        "media_darkness": 17,
    }

    settings = resolve_media_settings(config, printer_profile=profile)

    assert settings["gap_mm"] == pytest.approx(3.3)
    assert settings["gap_offset_mm"] == pytest.approx(0.1)
    assert settings["mark_mm"] == pytest.approx(6.6)
    assert settings["mark_offset_mm"] == pytest.approx(1.5)
    assert settings["fine_offset_mm"] == pytest.approx(0.25)
    assert settings["calibrate_next_print"] is True
    assert settings["speed"] == 8
    assert settings["density"] == 17
    assert settings["print_rate"] == "8"


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


def test_compile_model_silent_consumes_printer_profile():
    db_store.save_printer_profile("IMP", {"media_calibrate_next": True})

    payload = compile_model_silent("100x30", printer_name="IMP")

    assert isinstance(payload, bytes)
    assert b"GAPDETECT" in payload or b"BLINEDETECT" in payload
    assert b"FORMFEED" in payload

    profile = db_store.load_printer_profile("IMP")
    assert profile is not None
    assert profile.get("media_calibrate_next") is False


def test_printer_print_job_status_updates(monkeypatch):
    template = _simple_template()
    config = PrinterConfig(backend="tspl", transport="tcp", host="127.0.0.1")
    printer = Printer(config)
    stub = StubTransport()
    printer.transport = stub

    ok, status, job_id = printer.print_template(
        template, {"nome": "Ok", "volumes": 1}
    )
    assert ok and status is not None and status.get("status") == "pending"
    assert job_id is not None
    assert wait_for_all_jobs(2.0)

    with db_store.get_conn(db_store.default_db_path()) as conn:
        row = conn.execute(
            "SELECT status, error_text FROM print_jobs WHERE id = ?", (job_id,)
        ).fetchone()
        assert row is not None
        assert row["status"] == "done"
        assert row["error_text"] is None

    class FailingTransport(StubTransport):
        def send(self, payload: bytes) -> None:  # type: ignore[override]
            raise TransportError("boom", code=99)

    from printing import queue as print_queue

    monkeypatch.setattr(print_queue, "_RETRY_DELAYS", (0.01, 0.02, 0.04))

    printer.transport = FailingTransport()
    ok, status_info, failed_job_id = printer.print_template(
        template, {"nome": "Fail", "volumes": 1}
    )
    assert ok and status_info is not None and status_info.get("status") == "pending"
    assert failed_job_id is not None
    assert wait_for_all_jobs(1.0)

    with db_store.get_conn(db_store.default_db_path()) as conn:
        row = conn.execute(
            "SELECT status, error_text FROM print_jobs WHERE id = ?", (failed_job_id,)
        ).fetchone()
        assert row is not None
        assert row["status"] == "failed"
        assert row["error_text"] == "boom"


def test_list_print_jobs_returns_recent_entries():
    template = _simple_template()
    config = PrinterConfig(backend="tspl")
    printer = Printer(config)
    stub = StubTransport()
    printer.transport = stub

    ok, status, job_id = printer.print_template(
        template, {"nome": "Teste", "volumes": 1}
    )
    assert ok and status is not None and status.get("status") == "pending"
    assert job_id is not None
    assert wait_for_all_jobs(2.0)

    jobs = db_store.list_print_jobs(limit=5)
    assert any(job.get("id") == job_id for job in jobs)


def test_reprint_uses_saved_payload():
    template = _simple_template()
    printer = Printer(PrinterConfig(backend="tspl"))
    first_stub = StubTransport()
    printer.transport = first_stub

    ok, status, original_job_id = printer.print_template(
        template, {"nome": "Primeiro", "volumes": 1}
    )
    assert ok and status is not None and status.get("status") == "pending"
    assert original_job_id is not None
    assert wait_for_all_jobs(2.0)
    assert first_stub.payloads, "A impressão inicial deve enviar comandos"
    original_payload = first_stub.payloads[0]

    stored_payload = db_store.get_job_payload(job_id=original_job_id)
    assert stored_payload == original_payload

    record = db_store.get_print_job(job_id=original_job_id)
    assert record is not None

    reprint_config = PrinterConfig(
        backend=str(record.get("printer_backend") or "tspl"),
        transport=str(record.get("printer_transport") or "win32"),
        printer_name=str(record.get("printer_name") or "") or None,
    )
    reprint_printer = Printer(reprint_config)
    reprint_stub = StubTransport()
    reprint_printer.transport = reprint_stub

    ok2, status2, new_job_id = reprint_printer.send_commands(
        stored_payload,
        backend=str(record.get("template_backend") or "tspl"),
        template_name=str(record.get("template_name") or "") or None,
        template_backend=str(record.get("template_backend") or "") or None,
    )

    assert ok2 and status2 is not None and status2.get("status") == "pending"
    assert new_job_id is not None
    assert wait_for_all_jobs(2.0)
    assert reprint_stub.payloads == [original_payload]
    assert new_job_id != original_job_id
