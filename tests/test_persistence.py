"""Testes para funções de persistência de dados.

Responsabilidade:
    Verificar salvamento e carregamento de configurações e contagens.

Dependências:
    - persistence

Exemplo:
    $ pytest tests/test_persistence.py
"""

import json
import os
import sys
from datetime import datetime

import pytest

sys.path.append(os.path.dirname(os.path.dirname(__file__)))


def _patch_paths(monkeypatch, tmp_path):
    import persistence
    from db import store as db_store

    monkeypatch.setattr(
        persistence,
        "recurso_caminho",
        lambda p: os.path.join(tmp_path, p),
    )
    db_store.configure_default_path(tmp_path / "app.sqlite")
    return persistence


def test_carregar_config_template(monkeypatch, tmp_path):
    persistence = _patch_paths(monkeypatch, tmp_path)
    (tmp_path / "settings.json").write_text(json.dumps({"template": "60x80"}))
    config = persistence.carregar_config()
    assert config["template"] == "60x80"


def test_salvar_e_carregar_contagem(monkeypatch, tmp_path):
    persistence = _patch_paths(monkeypatch, tmp_path)
    persistence.salvar_contagem(5, 2)
    conteudo = (tmp_path / "contagem.json").read_text()
    assert json.loads(conteudo)["total_geral"] == 5

    def falha(*_):
        raise OSError

    monkeypatch.setattr(persistence.os, "replace", falha)
    with pytest.raises(OSError):
        persistence.salvar_contagem(7, 3)

    assert (tmp_path / "contagem.json").read_text() == conteudo
    assert json.loads((tmp_path / "contagem.json.bak").read_text())["total_geral"] == 5

    total, mensal = persistence.carregar_contagem()
    assert (total, mensal) == (5, 2)


def test_carregar_contagem_reseta_mes(monkeypatch, tmp_path):
    persistence = _patch_paths(monkeypatch, tmp_path)
    dados = {"total_geral": 7, "total_mes": 4, "mes_atual": "01-2000"}
    (tmp_path / "contagem.json").write_text(json.dumps(dados))
    total, mensal = persistence.carregar_contagem()
    assert total == 7
    assert mensal == 0


def test_gerar_relatorio_mensal(monkeypatch, tmp_path):
    import csv
    from db import store as db_store

    persistence = _patch_paths(monkeypatch, tmp_path)

    job_id = db_store.insert_print_job(
        payload_hash="abc",
        payload=b"TEST",
        template_name="demo",
        template_backend="tspl",
        printer_name="IMP",
        printer_backend="tspl",
        printer_transport="win32",
        media_settings=None,
    )
    db_store.update_print_job_status(job_id=job_id, status="done")

    mes = datetime.now().strftime("%Y-%m")
    path = persistence.gerar_relatorio_mensal(mes)
    assert (tmp_path / "reports" / f"relatorio_{mes}.csv").exists()
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f, delimiter=";"))
    assert rows[0] == [
        "ID",
        "Criado em",
        "Status",
        "Template",
        "Backend",
        "Impressora",
        "Transporte",
        "Iniciado",
        "Concluído",
        "Falhou em",
        "Erro",
    ]
    assert len(rows) == 2
    assert rows[1][2] == "done"


def test_registrar_contagem_mensal(monkeypatch, tmp_path):
    persistence = _patch_paths(monkeypatch, tmp_path)
    persistence.registrar_contagem_mensal("05-2024", 3)
    assert persistence.carregar_historico_mensal() == {"05-2024": 3}


def test_atualizar_recentes(monkeypatch, tmp_path):
    persistence = _patch_paths(monkeypatch, tmp_path)
    persistence.atualizar_recentes("cat1", "emi1", "mun1")
    persistence.atualizar_recentes("cat1", "emi2", "mun2")
    dados = persistence.carregar_recentes()
    assert dados["categoria"]["cat1"] == 2
    listas = persistence.carregar_recentes_listas()
    assert listas["categoria"][0] == "cat1"
    for i in range(25):
        persistence.atualizar_recentes(f"c{i}", f"e{i}", f"m{i}")
    dados = persistence.carregar_recentes()
    assert len(dados["categoria"]) == 20
