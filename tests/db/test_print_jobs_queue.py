import sys
import threading
import types
from typing import Dict, List

import pytest

if "PIL" not in sys.modules:
    pil_module = types.ModuleType("PIL")
    image_module = types.ModuleType("PIL.Image")
    image_draw_module = types.ModuleType("PIL.ImageDraw")
    image_font_module = types.ModuleType("PIL.ImageFont")
    image_filter_module = types.ModuleType("PIL.ImageFilter")
    image_ops_module = types.ModuleType("PIL.ImageOps")

    class _Resampling:
        LANCZOS = 1

    class _Dither:
        FLOYDSTEINBERG = 1

    image_module.Resampling = _Resampling
    image_module.Dither = _Dither

    def _unavailable(*_args, **_kwargs):  # pragma: no cover - stub helper
        raise RuntimeError("PIL stub does not implement image operations")

    image_module.open = _unavailable
    image_module.new = _unavailable
    image_module.Image = image_module

    image_draw_module.Draw = _unavailable
    image_draw_module.ImageDraw = image_draw_module

    image_font_module.truetype = _unavailable
    image_font_module.ImageFont = image_font_module

    image_filter_module.UnsharpMask = _unavailable

    image_ops_module.grayscale = _unavailable

    pil_module.Image = image_module
    pil_module.ImageDraw = image_draw_module
    pil_module.ImageFont = image_font_module
    pil_module.ImageFilter = image_filter_module
    pil_module.ImageOps = image_ops_module

    sys.modules["PIL"] = pil_module
    sys.modules["PIL.Image"] = image_module
    sys.modules["PIL.ImageDraw"] = image_draw_module
    sys.modules["PIL.ImageFont"] = image_font_module
    sys.modules["PIL.ImageFilter"] = image_filter_module
    sys.modules["PIL.ImageOps"] = image_ops_module

from db import store as db_store
from printing import queue as print_queue


@pytest.fixture(autouse=True)
def queue_test_environment(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Reset queue state and configure an isolated database for each test."""

    # Ensure any previous workers are stopped before resetting globals.
    print_queue.shutdown()

    monkeypatch.setattr(print_queue, "_workers", {})
    monkeypatch.setattr(print_queue, "_started", False)
    monkeypatch.setattr(print_queue, "_shutdown", False)
    monkeypatch.setattr(print_queue, "_RETRY_DELAYS", (0.01, 0.02, 0.05))

    monkeypatch.setattr(db_store, "_DEFAULT_DB_PATH", None)
    monkeypatch.setattr(db_store, "_INITIALISED", set())

    db_path = tmp_path / "queue.sqlite"
    db_store.configure_default_path(db_path)
    db_store.init(db_path)

    try:
        yield
    finally:
        print_queue.shutdown(timeout=1.0)


def test_print_job_processed_successfully():
    payloads: List[bytes] = []
    processed = threading.Event()

    def send(data: bytes) -> None:
        payloads.append(data)
        processed.set()

    printer = print_queue.PrinterTarget(
        name="Printer A",
        backend="mock",
        transport="usb",
        send=send,
    )

    job_id, status = print_queue.enqueue_job(
        template_id=None,
        payload=b"payload-data",
        printer=printer,
        copies=1,
    )
    assert status == "pending"

    assert print_queue.wait_for_all(timeout=2.0)
    assert processed.wait(timeout=1.0)

    record = db_store.get_print_job(job_id=job_id)
    assert record is not None
    assert record["status"] == "done"
    assert payloads == [b"payload-data"]


def test_print_job_retries_and_failure(monkeypatch: pytest.MonkeyPatch):
    status_transitions: Dict[int, List[str]] = {}
    real_update = db_store.update_print_job_status

    def tracking_update(
        *, status: str, job_id: int | None = None, payload_hash: str | None = None, **kwargs
    ):
        if job_id is not None:
            status_transitions.setdefault(job_id, []).append(status)
        return real_update(
            status=status,
            job_id=job_id,
            payload_hash=payload_hash,
            **kwargs,
        )

    monkeypatch.setattr(db_store, "update_print_job_status", tracking_update)

    attempts = {"count": 0}
    success_signal = threading.Event()

    def flaky_send(data: bytes) -> None:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("transient error")
        success_signal.set()

    printer_retry = print_queue.PrinterTarget(
        name="Printer Retry",
        backend="mock",
        transport="usb",
        send=flaky_send,
    )

    job_id_retry, _ = print_queue.enqueue_job(
        template_id=None,
        payload=b"retry-payload",
        printer=printer_retry,
        copies=1,
    )

    assert print_queue.wait_for_all(timeout=3.0)
    assert success_signal.wait(timeout=1.0)

    retry_record = db_store.get_print_job(job_id=job_id_retry)
    assert retry_record is not None
    assert retry_record["status"] == "done"
    assert attempts["count"] == 2
    assert status_transitions[job_id_retry][:4] == [
        "running",
        "failed",
        "running",
        "done",
    ]

    failure_attempts = {"count": 0}
    failure_error = "permanent failure"

    def always_fail_send(_: bytes) -> None:
        failure_attempts["count"] += 1
        raise RuntimeError(failure_error)

    printer_fail = print_queue.PrinterTarget(
        name="Printer Fail",
        backend="mock",
        transport="usb",
        send=always_fail_send,
    )

    job_id_fail, _ = print_queue.enqueue_job(
        template_id=None,
        payload=b"will-fail",
        printer=printer_fail,
        copies=1,
    )

    assert print_queue.wait_for_all(timeout=3.0)

    fail_record = db_store.get_print_job(job_id=job_id_fail)
    assert fail_record is not None
    assert fail_record["status"] == "failed"
    assert failure_attempts["count"] == len(print_queue._RETRY_DELAYS)
    assert status_transitions[job_id_fail][-1] == "failed"
    assert fail_record["error_text"] == failure_error
