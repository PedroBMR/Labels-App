"""Funções de persistência de dados do aplicativo."""

import csv
import json
import os
from datetime import datetime
from typing import Any, cast

from utils import recurso_caminho


DEFAULT_CONFIG: dict[str, Any] = {
    "ultima_impressora": "",
    "template": "Padrão",
    "retry_automatico": False,
    "backup_horario": "17:10",
}


def carregar_config() -> dict[str, Any]:
    """Lê as configurações persistidas do aplicativo."""

    caminho = recurso_caminho("settings.json")
    if os.path.exists(caminho):
        with open(caminho, "r", encoding="utf-8") as arquivo:
            try:
                dados: dict[str, Any] = json.load(arquivo)
            except Exception:
                dados = {}
    else:
        dados = {}
    config = DEFAULT_CONFIG.copy()
    config.update(dados)
    return config


def salvar_config(dados: dict[str, Any]) -> None:
    """Persiste as configurações do aplicativo."""

    caminho = recurso_caminho("settings.json")
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, ensure_ascii=False, indent=4)


def carregar_contagem() -> tuple[int, int]:
    """Lê os contadores de impressão.

    Returns:
        tuple[int, int]: Total geral e total do mês atual.
    """

    caminho = recurso_caminho("contagem.json")
    mes_atual = datetime.now().strftime("%m-%Y")
    contagem_total: int = 0
    contagem_mensal: int = 0
    if os.path.exists(caminho):
        with open(caminho, "r", encoding="utf-8") as arquivo:
            dados: dict[str, int | str] = json.load(arquivo)
        if dados.get("mes_atual") == mes_atual:
            contagem_total = int(dados.get("total_geral") or 0)
            contagem_mensal = int(dados.get("total_mes") or 0)
        else:
            contagem_total = int(dados.get("total_geral") or 0)
            contagem_mensal = 0
            salvar_contagem(contagem_total, contagem_mensal)
    else:
        salvar_contagem(0, 0)
    return contagem_total, contagem_mensal


def salvar_contagem(contagem_total: int, contagem_mensal: int) -> None:
    """Persiste os contadores de impressão.

    Args:
        contagem_total (int): Quantidade total de etiquetas impressas.
        contagem_mensal (int): Quantidade de etiquetas impressas no mês.
    """

    caminho = recurso_caminho("contagem.json")
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    dados: dict[str, int | str] = {
        "total_geral": int(contagem_total or 0),
        "total_mes": int(contagem_mensal or 0),
        "mes_atual": datetime.now().strftime("%m-%Y"),
    }
    with open(caminho, "w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, ensure_ascii=False, indent=4)


def salvar_historico(
    saida: str,
    categoria: str,
    emissor: str,
    municipio: str,
    volumes: int,
    data_hora: str,
) -> None:
    """Adiciona registro ao histórico de impressões.

    Args:
        saida (str): Número da saída.
        categoria (str): Categoria da etiqueta.
        emissor (str): Nome de quem emitiu a etiqueta.
        municipio (str): Município de destino.
        volumes (int): Quantidade de volumes impressos.
        data_hora (str): Data e hora da impressão.
    """

    caminho = recurso_caminho("historico_impressoes.csv")
    existe = os.path.exists(caminho)
    with open(caminho, "a", newline="", encoding="utf-8-sig") as arquivo:
        writer = csv.writer(arquivo, delimiter=";")
        if not existe:
            writer.writerow(
                ["Data e Hora", "Saída", "Categoria", "Emissor", "Município", "Volumes"]
            )
        writer.writerow([data_hora, saida, categoria, emissor, municipio, volumes])


def carregar_recentes() -> dict[str, dict[str, int]]:
    """Lê as listas de valores usados recentemente."""

    caminho = recurso_caminho("recentes.json")
    if os.path.exists(caminho):
        with open(caminho, "r", encoding="utf-8") as arquivo:
            return cast(dict[str, dict[str, int]], json.load(arquivo))
    return {"categoria": {}, "emissor": {}, "municipio": {}}


def atualizar_recentes(categoria: str, emissor: str, municipio: str) -> None:
    """Atualiza o contador de valores mais utilizados."""

    dados = carregar_recentes()
    for campo, valor in (
        ("categoria", categoria),
        ("emissor", emissor),
        ("municipio", municipio),
    ):
        valor = valor.strip()
        if not valor:
            continue
        mapa = dados.setdefault(campo, {})
        mapa[valor] = mapa.get(valor, 0) + 1
        ordenado = sorted(mapa.items(), key=lambda x: x[1], reverse=True)[:20]
        dados[campo] = {k: v for k, v in ordenado}

    caminho = recurso_caminho("recentes.json")
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, ensure_ascii=False, indent=4)


def carregar_recentes_listas() -> dict[str, list[str]]:
    """Obtém as listas de valores recentes ordenadas por uso."""

    dados = carregar_recentes()
    return {
        campo: [k for k, _ in sorted(val.items(), key=lambda x: x[1], reverse=True)]
        for campo, val in dados.items()
    }


def registrar_contagem_mensal(mes: str, quantidade: int) -> None:
    """Atualiza o total de etiquetas por mês.

    Args:
        mes (str): Mês no formato ``MM-YYYY``.
        quantidade (int): Quantidade de etiquetas a somar.
    """

    caminho = recurso_caminho("contagem_mensal.json")
    if os.path.exists(caminho):
        with open(caminho, "r", encoding="utf-8") as arquivo:
            dados: dict[str, int] = json.load(arquivo)
    else:
        dados = {}
    dados[mes] = dados.get(mes, 0) + quantidade
    with open(caminho, "w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, ensure_ascii=False, indent=2)


def carregar_historico_mensal() -> dict[str, int]:
    """Obtém os dados de impressão por mês.

    Returns:
        dict[str, int]: Mapeamento de ``mes`` para ``total`` de etiquetas.
    """

    caminho = recurso_caminho("contagem_mensal.json")
    if os.path.exists(caminho):
        with open(caminho, "r", encoding="utf-8") as arquivo:
            return cast(dict[str, int], json.load(arquivo))
    return {}


def gerar_relatorio_mensal(mes: str) -> str:
    """Gera um relatório consolidado de um mês específico.

    O relatório contém os totais de etiquetas agrupados por categoria,
    município e emissor. O arquivo é salvo na pasta ``reports`` na raiz do
    aplicativo, com o nome ``relatorio_YYYY-MM.csv``.

    Args:
        mes (str): Mês desejado no formato ``YYYY-MM``.

    Returns:
        str: Caminho absoluto do relatório gerado.
    """

    hist_path = recurso_caminho("historico_impressoes.csv")
    if not os.path.exists(hist_path):
        raise FileNotFoundError("Histórico de impressões não encontrado")

    totais: dict[tuple[str, str, str], int] = {}
    with open(hist_path, newline="", encoding="utf-8-sig") as arquivo:
        reader = csv.DictReader(arquivo, delimiter=";")
        for row in reader:
            data = datetime.strptime(row["Data e Hora"], "%d/%m/%Y %H:%M:%S")
            if data.strftime("%Y-%m") != mes:
                continue
            chave = (row["Categoria"], row["Município"], row["Emissor"])
            totais[chave] = totais.get(chave, 0) + int(row["Volumes"])

    base_dir = os.path.dirname(recurso_caminho(""))
    reports_dir = os.path.join(base_dir, "reports")
    os.makedirs(reports_dir, exist_ok=True)
    relatorio_path = os.path.join(reports_dir, f"relatorio_{mes}.csv")

    with open(relatorio_path, "w", newline="", encoding="utf-8-sig") as arquivo:
        writer = csv.writer(arquivo, delimiter=";")
        writer.writerow(["Categoria", "Município", "Emissor", "Volumes"])
        for (categoria, municipio, emissor), total in sorted(totais.items()):
            writer.writerow([categoria, municipio, emissor, total])

    return relatorio_path
