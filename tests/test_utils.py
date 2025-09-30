"""Testes para utilitários do aplicativo.

Responsabilidade:
    Validar funções auxiliares como melhoria de logo e backup automático.

Dependências:
    - utils

Exemplo:
    $ pytest tests/test_utils.py
"""

import logging
import os
import sys
from datetime import datetime

import pytest

pytest.importorskip("PIL")

from PIL import Image

try:
    Image.new("1", (1, 1))
except Exception:
    pytest.skip("Pillow não está disponível", allow_module_level=True)

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import utils
from db import store as db_store


def test_melhorar_logo_shape(tmp_path):
    img_path = tmp_path / "logo.png"
    Image.new("L", (8, 8), color=255).save(img_path)

    bitmap, largura_bytes, altura = utils.melhorar_logo(
        str(img_path), largura_desejada=8
    )

    assert largura_bytes == 1
    assert altura == 8
    assert len(bitmap) == largura_bytes * altura


def test_melhorar_logo_cache(monkeypatch, tmp_path):
    img_path = tmp_path / "logo.png"
    Image.new("L", (8, 8), color=255).save(img_path)

    original_open = utils.load_image
    calls = {"count": 0}

    def counting_open(path: str):
        calls["count"] += 1
        return original_open(path)

    monkeypatch.setattr(utils, "load_image", counting_open)
    utils.melhorar_logo.cache_clear()

    utils.melhorar_logo(str(img_path), largura_desejada=8)
    utils.melhorar_logo(str(img_path), largura_desejada=8)

    assert calls["count"] == 1


def test_backup_limite(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(utils, "_base_dir", lambda: str(tmp_path))

    assets = tmp_path / "assets"
    assets.mkdir()
    for nome in ["contagem.json", "contagem_mensal.json"]:
        (assets / nome).write_text("dados")

    (assets / "settings.json").write_text("{\"backup_quantidade\": 2}")

    db_store.configure_default_path(tmp_path / "_data" / "app.sqlite")
    db_path = db_store.default_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.write_text("db")

    class FakeDateTime:
        counter = 0

        @classmethod
        def now(cls):
            cls.counter += 1
            return datetime(2024, 1, 1, 0, 0, cls.counter)

    monkeypatch.setattr(utils, "datetime", FakeDateTime)

    with caplog.at_level(logging.INFO, logger="app"):
        from log import logger as app_logger
        app_logger.addHandler(caplog.handler)
        try:
            utils.backup_automatico()
            utils.backup_automatico()
            utils.backup_automatico()
        finally:
            app_logger.removeHandler(caplog.handler)

    destino = tmp_path / "_backup"
    backups = sorted(destino.glob("app_*.sqlite"))
    assert len(backups) == 2
    assert not (destino / "app_2024-01-01_00-00-01.sqlite").exists()
    assert any("Backup removido" in record.message for record in caplog.records)
