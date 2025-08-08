"""Funções de persistência de dados do aplicativo."""

import csv
import json
import os
from datetime import datetime

from utils import recurso_caminho

def carregar_contagem() -> tuple[int, int]:
    """Lê os contadores de impressão.

    Returns:
        tuple[int, int]: Total geral e total do mês atual.
    """

    caminho = recurso_caminho("contagem.json")
    mes_atual = datetime.now().strftime("%m-%Y")
    contagem_total = 0
    contagem_mensal = 0
    if os.path.exists(caminho):
        with open(caminho, "r", encoding="utf-8") as arquivo:
            dados = json.load(arquivo)
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
    dados = {
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
        
def registrar_contagem_mensal(mes: str, quantidade: int) -> None:
    """Atualiza o total de etiquetas por mês.

    Args:
        mes (str): Mês no formato ``MM-YYYY``.
        quantidade (int): Quantidade de etiquetas a somar.
    """

    caminho = recurso_caminho("contagem_mensal.json")
    if os.path.exists(caminho):
        with open(caminho, "r", encoding="utf-8") as arquivo:
            dados = json.load(arquivo)
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
            return json.load(arquivo)
    return {}
