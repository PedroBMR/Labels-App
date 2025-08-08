# Gerador de Etiquetas CONIMS

**Aplicação modular para geração e impressão de etiquetas térmicas (60x80mm) no padrão CONIMS.**

---

## Estrutura do Projeto


*(Os outros módulos serão adicionados nas próximas etapas)*

---

## Requisitos

- **Python 3.11+**
- **Pillow** (`pip install Pillow`)
- **PyQt5** (`pip install PyQt5`)
- **pywin32** (`pip install pywin32`)  *(Para impressão direta no Windows)*
- **Impressora térmica compatível com TSPL (ex: Gainscha GS-2406T)*

---

## Modo de uso (após todos os arquivos prontos)

1. Instale as dependências:

2. Coloque sua logo em `_internal/logo.png` e/ou outros recursos.

3. Rode o app com:

4. Use o formulário para gerar e imprimir etiquetas.

---

## Organização Modular

- **utils.py**: Funções auxiliares (caminhos de recursos, tratamento da logo, etc)
- **persistence.py**: Funções de salvar e carregar histórico/contagem
- **printing.py**: Função de montar e enviar etiquetas TSPL para impressora
- **ui.py**: Interface gráfica (PyQt5), formulário, status, integração total dos módulos.
- **main.py**: Ponto de entrada do app (executável principal)

---

## Autor

Desenvolvido por Pedro Luiz Bortot  
Consultoria e modularização por IA (OpenAI GPT)

---
