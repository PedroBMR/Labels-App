import json
import csv
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import persistence

def _patch_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(persistence, "recurso_caminho", lambda p: os.path.join(tmp_path, p))

def test_salvar_e_carregar_contagem(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    persistence.salvar_contagem(5, 2)
    assert json.loads((tmp_path / "contagem.json").read_text())["total_geral"] == 5
    total, mensal = persistence.carregar_contagem()
    assert (total, mensal) == (5, 2)

def test_carregar_contagem_reseta_mes(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    dados = {"total_geral": 7, "total_mes": 4, "mes_atual": "01-2000"}
    (tmp_path / "contagem.json").write_text(json.dumps(dados))
    total, mensal = persistence.carregar_contagem()
    assert total == 7
    assert mensal == 0

def test_salvar_historico_e_registrar(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    persistence.salvar_historico("s", "c", "e", "m", 3, "data")
    with open(tmp_path / "historico_impressoes.csv", newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f, delimiter=";"))
    assert rows[0] == ["Data e Hora", "Saída", "Categoria", "Emissor", "Município", "Volumes"]
    assert rows[1] == ["data", "s", "c", "e", "m", "3"]

    persistence.registrar_contagem_mensal("05-2024", 3)
    assert persistence.carregar_historico_mensal() == {"05-2024": 3}
