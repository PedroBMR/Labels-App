# persistence.py
import os
import json
import csv
from datetime import datetime
from utils import recurso_caminho

def carregar_contagem():
    """Lê o arquivo de contagem.json e retorna total_geral, total_mes."""
    caminho = recurso_caminho("contagem.json")
    mes_atual = datetime.now().strftime("%m-%Y")
    contagem_total = 0
    contagem_mensal = 0
    if os.path.exists(caminho):
        with open(caminho, "r", encoding="utf-8") as f:
            dados = json.load(f)
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

def salvar_contagem(contagem_total, contagem_mensal):
    """Salva os contadores em contagem.json."""
    caminho = recurso_caminho("contagem.json")
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    dados = {
        "total_geral": int(contagem_total or 0),
        "total_mes": int(contagem_mensal or 0),
        "mes_atual": datetime.now().strftime("%m-%Y"),
    }
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=4)

def salvar_historico(saida, categoria, emissor, municipio, volumes, data_hora):
    """Adiciona uma linha no histórico de impressões (CSV)."""
    caminho = recurso_caminho("historico_impressoes.csv")
    existe = os.path.exists(caminho)
    with open(caminho, "a", newline="", encoding="utf-8-sig") as arq:
        w = csv.writer(arq, delimiter=";")
        if not existe:
            w.writerow(
                ["Data e Hora", "Saída", "Categoria",
                 "Emissor", "Município", "Volumes"]
            )
        w.writerow([data_hora, saida, categoria, emissor, municipio, volumes])
        
def registrar_contagem_mensal(mes, quantidade):
    """Soma ao mês informado a quantidade de etiquetas impressas."""
    caminho = recurso_caminho("contagem_mensal.json")
    if os.path.exists(caminho):
        with open(caminho, "r", encoding="utf-8") as f:
            dados = json.load(f)
    else:
        dados = {}
    dados[mes] = dados.get(mes, 0) + quantidade
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)

def carregar_historico_mensal():
    """Retorna o dicionário mês:total."""
    caminho = recurso_caminho("contagem_mensal.json")
    if os.path.exists(caminho):
        with open(caminho, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}