"""In-process printer job queue with retry handling."""

from __future__ import annotations

import atexit
import logging
import queue
import threading
import time

from dataclasses import dataclass
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    Mapping,
    Optional,
)

from db import store as db_store

JobStatus = str

_RETRY_DELAYS = (1.0, 3.0, 9.0)


@dataclass(frozen=True)
class PrinterTarget:
    """Descriptor for a logical printer handled by the queue."""

    name: str | None
    backend: str | None
    transport: str | None
    send: Callable[[bytes], None]
    logger: logging.Logger | None = None

    def key(self) -> tuple[str | None, str | None, str | None]:
        return (self.transport, self.backend, self.name)


@dataclass
class _QueueJob:
    job_id: int


class _PrinterWorker:
    def __init__(self, target: PrinterTarget) -> None:
        self.target = target
        self._queue: "queue.Queue[Optional[_QueueJob]]" = queue.Queue()
        self._thread = threading.Thread(
            target=self._run, name=f"printer-worker-{self._key_for_name()}", daemon=True
        )
        self._stop_event = threading.Event()
        self._idle_event = threading.Event()
        self._idle_event.set()

    def start(self) -> None:
        if not self._thread.is_alive():
            self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._queue.put(None)

    def join(self, timeout: float | None = None) -> None:
        self._thread.join(timeout)

    def submit(self, job_id: int) -> None:
        self._idle_event.clear()
        self._queue.put(_QueueJob(job_id))

    def wait_idle(self, timeout: float | None = None) -> bool:
        return self._idle_event.wait(timeout)

    def prime_pending(self) -> None:
        for job in _find_pending_jobs(self.target):
            self.submit(job)

    def _run(self) -> None:
        while True:
            try:
                job = self._queue.get(timeout=0.5)
            except queue.Empty:
                if self._stop_event.is_set():
                    break
                continue
            if job is None:
                break
            try:
                self._process(job.job_id)
            finally:
                self._queue.task_done()
        self._idle_event.set()

    def _process(self, job_id: int) -> None:
        target = self.target
        logger = target.logger or logging.getLogger("app")
        record = db_store.get_print_job(job_id=job_id)
        payload = db_store.get_job_payload(job_id=job_id)
        if record is None or payload is None:
            db_store.update_print_job_status(
                job_id=job_id,
                status="failed",
                error_text="Payload ausente",
            )
            logger.error("Job %s sem payload para impressora %s", job_id, target.name)
            return

        copies_value = record.get("copies", 1)
        try:
            copies = int(copies_value)
        except (TypeError, ValueError):
            copies = 1
        if copies < 1:
            copies = 1

        last_error: Optional[str] = None
        for attempt, delay in enumerate(_RETRY_DELAYS, start=1):
            if self._stop_event.is_set():
                break
            db_store.update_print_job_status(job_id=job_id, status="running")
            try:
                for _ in range(copies):
                    target.send(payload)
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                db_store.update_print_job_status(
                    job_id=job_id,
                    status="failed",
                    error_text=last_error,
                )
                logger.warning(
                    "Falha ao enviar job %s (tentativa %s/%s): %s",
                    job_id,
                    attempt,
                    len(_RETRY_DELAYS),
                    exc,
                )
                if attempt == len(_RETRY_DELAYS):
                    break
                if self._stop_event.wait(delay):
                    break
                continue
            else:
                db_store.update_print_job_status(job_id=job_id, status="done")
                logger.debug("Job %s enviado com sucesso", job_id)
                break
        if last_error and not _job_succeeded(job_id):
            logger.error("Job %s falhou apos tentativas: %s", job_id, last_error)
        self._idle_event.set()

    def _key_for_name(self) -> str:
        transport, backend, name = self.target.key()
        parts = [p for p in (transport, backend, name) if p]
        return "-".join(parts) or "default"


_workers: Dict[tuple[str | None, str | None, str | None], _PrinterWorker] = {}
_lock = threading.Lock()
_started = False
_shutdown = False


def start() -> None:
    global _started
    with _lock:
        if _started:
            return
        atexit.register(shutdown)
        _started = True


def shutdown(timeout: float | None = None) -> None:
    global _shutdown
    with _lock:
        if _shutdown:
            return
        workers = list(_workers.values())
        _workers.clear()
        _shutdown = True
    for worker in workers:
        worker.stop()
    for worker in workers:
        worker.join(timeout)


def wait_for_all(timeout: float | None = None) -> bool:
    """Block until all workers are idle or ``timeout`` expires."""

    deadline = None if timeout is None else time.monotonic() + timeout
    workers: Iterable[_PrinterWorker]
    with _lock:
        workers = list(_workers.values())
    for worker in workers:
        remaining = None
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
        if not worker.wait_idle(remaining):
            return False
    return True


def enqueue_job(
    template_id: str | None,
    payload: bytes | bytearray | memoryview,
    printer: PrinterTarget,
    copies: int,
    params: Mapping[str, Any] | None = None,
) -> tuple[int, JobStatus]:
    """Insert a job into the queue returning its identifier and status."""

    start()
    payload_bytes = bytes(payload)
    params = dict(params or {})
    payload_hash = params.get("payload_hash")
    if not payload_hash:
        import hashlib

        payload_hash = hashlib.sha256(payload_bytes).hexdigest()

    job_id = db_store.insert_print_job(
        payload_hash=payload_hash,
        payload=payload_bytes,
        copies=max(1, int(copies)),
        template_name=template_id,
        template_backend=params.get("template_backend"),
        printer_name=printer.name,
        printer_backend=params.get("printer_backend", printer.backend),
        printer_transport=params.get("printer_transport", printer.transport),
        printer_host=params.get("printer_host"),
        printer_port=params.get("printer_port"),
        media_settings=params.get("media_settings"),
    )

    worker, created = _get_or_create_worker(printer)
    if not created:
        worker.submit(job_id)
    return job_id, "pending"


def _get_or_create_worker(printer: PrinterTarget) -> tuple[_PrinterWorker, bool]:
    created = False
    with _lock:
        if _shutdown:
            raise RuntimeError("Queue already shut down")
        key = printer.key()
        worker = _workers.get(key)
        if worker is None:
            worker = _PrinterWorker(printer)
            _workers[key] = worker
            created = True
    if created:
        worker.prime_pending()
        worker.start()
    return worker, created


def _find_pending_jobs(printer: PrinterTarget) -> Iterable[int]:
    pending = db_store.list_print_jobs(status=["pending"], limit=500)
    for job in pending:
        if (
            job.get("printer_name") == printer.name
            and job.get("printer_backend") == printer.backend
            and job.get("printer_transport") == printer.transport
        ):
            job_id = job.get("id")
            if isinstance(job_id, int):
                yield job_id


def _job_succeeded(job_id: int) -> bool:
    record = db_store.get_print_job(job_id=job_id)
    if not record:
        return False
    return str(record.get("status")).lower() == "done"
