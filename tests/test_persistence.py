import csv
import json
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))


def _patch_paths(monkeypatch, tmp_path):
    import persistence

    monkeypatch.setattr(
        persistence,
        "recurso_caminho",
        lambda p: os.path.join(tmp_path, p),
    )
    return persistence


def test_salvar_e_carregar_contagem(monkeypatch, tmp_path):
    persistence = _patch_paths(monkeypatch, tmp_path)
    persistence.salvar_contagem(5, 2)
    assert json.loads((tmp_path / "contagem.json").read_text())["total_geral"] == 5
    total, mensal = persistence.carregar_contagem()
    assert (total, mensal) == (5, 2)


def test_carregar_contagem_reseta_mes(monkeypatch, tmp_path):
    persistence = _patch_paths(monkeypatch, tmp_path)
    dados = {"total_geral": 7, "total_mes": 4, "mes_atual": "01-2000"}
    (tmp_path / "contagem.json").write_text(json.dumps(dados))
    total, mensal = persistence.carregar_contagem()
    assert total == 7
    assert mensal == 0


def test_salvar_historico_e_registrar(monkeypatch, tmp_path):
    persistence = _patch_paths(monkeypatch, tmp_path)
    persistence.salvar_historico("s", "c", "e", "m", 3, "data")
    with open(
        tmp_path / "historico_impressoes.csv",
        newline="",
        encoding="utf-8-sig",
    ) as f:
        rows = list(csv.reader(f, delimiter=";"))
    assert rows[0] == [
        "Data e Hora",
        "Saída",
        "Categoria",
        "Emissor",
        "Município",
        "Volumes",
    ]
    assert rows[1] == ["data", "s", "c", "e", "m", "3"]

    persistence.registrar_contagem_mensal("05-2024", 3)
    assert persistence.carregar_historico_mensal() == {"05-2024": 3}


def test_gerar_relatorio_mensal(monkeypatch, tmp_path):
    persistence = _patch_paths(monkeypatch, tmp_path)
    with open(
        tmp_path / "historico_impressoes.csv",
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as f:
        f.write("Data e Hora;Saída;Categoria;Emissor;Município;Volumes\n")
        f.write("06/08/2025 09:30:13;1;Cat;Emi;Mun;1\n")
        f.write("07/08/2025 10:00:00;2;Cat;Emi;Mun;2\n")
        f.write("01/09/2025 00:00:00;3;Cat2;Emi2;Mun2;3\n")

    path = persistence.gerar_relatorio_mensal("2025-08")
    assert (tmp_path / "reports" / "relatorio_2025-08.csv").exists()
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f, delimiter=";"))
    assert rows == [
        ["Categoria", "Município", "Emissor", "Volumes"],
        ["Cat", "Mun", "Emi", "3"],
    ]


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
