# Labels-App

Aplicativo desktop para **geração e impressão de etiquetas térmicas** no padrão
CONIMS. Desenvolvido em Python, ele facilita o controle de saídas de material,
mantém histórico de impressões e permite personalizar o layout das etiquetas.

---

## Descrição Geral

O Labels-App ajuda instituições que precisam emitir etiquetas de identificação
para caixas e volumes. A aplicação gera etiquetas de 60x80&nbsp;mm e 100x30&nbsp;mm,
envia a impressão diretamente para impressoras térmicas compatíveis com TSPL e
armazena todo o histórico gerado. É possível escolher modelos de layout,
reimprimir etiquetas e realizar backup automático dos dados.

---

## Funcionalidades

- Seleção da impressora padrão e configuração de modelos de etiqueta.
- Geração e impressão imediata de etiquetas térmicas nos modelos 60x80&nbsp;mm e
  100x30&nbsp;mm.
- Reimpressão do último lote, de volumes faltantes ou de um intervalo
  específico.
- Histórico completo das impressões com exportação para CSV.
- Relatório mensal consolidado por categoria, município e emissor.
- Backup automático diário dos arquivos de dados.
- Personalização de layout através de templates definidos em `assets/templates.json`.

---

## Requisitos do Sistema

- **Python 3.11 ou superior**
- **PyQt5** (até Python 3.12) ou **PySide6** (Python 3.13+) para a interface gráfica
- **Pillow** para tratamento de imagens
- **pywin32** (somente no Windows) para envio direto à impressora
- Impressora térmica compatível com **TSPL** (ex.: Gainscha GS‑2406T)

As bindings Qt são opcionais e instaladas separadamente. Instale primeiro as
dependências base (ou de desenvolvimento, que já incluem as base) e, em
seguida, escolha a binding desejada:

```bash
pip install -r requirements.txt          # dependências de runtime
# ou, para desenvolvimento (inclui as dependências de runtime)
pip install -r requirements-dev.txt
```

Depois selecione uma das bindings Qt:

```bash
pip install -r requirements-pyqt5.txt    # usa PyQt5
# ou
pip install -r requirements-pyside6.txt  # usa PySide6
```

---

## Ambiente Python 3.13

Para testar o projeto com o **Python 3.13**, utilize um ambiente virtual
apontando para a versão, instale as dependências de desenvolvimento e, em
seguida, a binding Qt desejada (`requirements-pyside6.txt` ou
`requirements-pyqt5.txt`):
```bash
python3.13 -m venv .venv
source .venv/bin/activate  # Linux/macOS
venv\Scripts\activate     # Windows
pip install -r requirements-dev.txt
pip install -r requirements-pyside6.txt  # ou requirements-pyqt5.txt
```

---

## Instalação

### Ambiente de desenvolvimento

1. Clone o repositório e entre na pasta do projeto.
2. Crie um ambiente virtual opcional e instale as dependências:

   ```bash
   pip install -r requirements-dev.txt
   pip install -r requirements-pyqt5.txt   # ou requirements-pyside6.txt
   ```
3. Execute o aplicativo:

   ```bash
   python main.py
   ```

### Versão compilada (Windows)

1. Baixe `GeradorEtiquetas.exe` nas releases ou como artifact do fluxo de CI.
2. Coloque o arquivo em uma pasta com permissão de escrita.
3. Execute o `.exe` para abrir o aplicativo.

---

## Build com PyInstaller

### Pré-requisitos

- Python 3.11 ou superior instalado e acessível pelo `python`.
- PowerShell.
- (Opcional) ambiente virtual em `.venv` ou `venv`.
- Dependências de runtime listadas em `requirements.txt` (instaladas junto com
  `requirements-dev.txt`, quando aplicável) e a binding Qt escolhida
  (`requirements-pyqt5.txt` ou `requirements-pyside6.txt`), além das de
  desenvolvimento em `requirements-dev.txt` (instaladas automaticamente pelos
  scripts).

### Comandos

```powershell
# executável único com pasta `assets` gravável
scripts\build_with_assets.ps1

# executável único, sem console
scripts\build_onefile.ps1

# modo pasta para depuração (usa `GeradorEtiquetas_onedir.spec` sem UPX)
scripts\build_onedir.ps1
```

Os scripts ativam o ambiente virtual (se existir), instalam dependências
ausentes, rodam os arquivos `.spec` com o **PyInstaller** e copiam o executável
final para `dist\GeradorEtiquetas_v{versão}.exe`. A versão exibida é lida da
constante `__version__` definida em `_version.py`; não edite `version.txt`, pois
ele é recriado automaticamente por `main.ensure_version_file()` ao iniciar o
aplicativo. Execute `scripts\build_with_assets.ps1` para gerar um `.exe`
acompanhado de uma pasta `assets` gravável para os arquivos de histórico. É
possível alterar o nome do executável e o ícone definindo as variáveis de
ambiente `APP_NAME` e `APP_ICON` antes da execução.

Use `scripts\build_onedir.ps1` para gerar um build de desenvolvimento baseado
em diretório através de `GeradorEtiquetas_onedir.spec`. Nessa configuração, a
compressão UPX é desativada para acelerar a compilação e evitar problemas de
depuração.

---

## Testes e Lint

Antes de enviar contribuições, instale as dependências de desenvolvimento e
execute a suíte de testes e a verificação de estilo:

```bash
pip install -r requirements-dev.txt
pip install -r requirements-pyqt5.txt   # ou requirements-pyside6.txt
ruff .
pytest
```

## Manutenção de Dependências

As versões listadas em `requirements.txt` estão fixadas para garantir
reprodutibilidade. Revise-as periodicamente seguindo os passos abaixo:

1. Atualize os pacotes para versões recentes e edite `requirements.txt` com os
   novos números de versão.
2. Reinstale o ambiente (comece pelas dependências base ou de desenvolvimento e
   finalize com a binding Qt):
   ```bash
   pip install -r requirements-dev.txt
   pip install -r requirements-pyqt5.txt   # ou requirements-pyside6.txt
   ```
   Para um ambiente somente de runtime, substitua o primeiro comando por
   `pip install -r requirements.txt`.
3. Verifique vulnerabilidades com [`pip-audit`](https://pypi.org/project/pip-audit/)
   ou [`safety`](https://pyup.io/safety/):
   ```bash
   pip-audit -r requirements.txt -r requirements-dev.txt -r requirements-pyqt5.txt
   # ou troque pelo arquivo requirements-pyside6.txt
   ```
4. Execute `ruff` e `pytest` para validar as atualizações.

Realize essa revisão com regularidade, por exemplo a cada mês ou quando novas
falhas críticas forem divulgadas.

---

## Uso

1. Na tela inicial informe **Saída**, **Categoria**, **Emissor**,
   **Município** e **Volumes**.
2. Escolha o modelo de etiqueta e pressione **Imprimir Agora**.
3. Utilize os botões de reimpressão para repetir o último lote ou corrigir
   faltantes.

![Tela principal](assets/color.png)

> *Exemplo de formulário principal. Substitua a imagem por capturas reais do
> seu fluxo de impressão.*
---


## Estrutura de templates

Os modelos de etiqueta são definidos em `assets/templates.json`. Cada entrada
contém `largura_mm`, `altura_mm` e `gap_mm` em milímetros. Edite esse arquivo
para ajustar layouts existentes ou adicionar novos modelos. Reinicie o
aplicativo para aplicar as mudanças.

Backups automáticos do histórico são gravados em `_backup/` e os registros de
log ficam em `logs/app.log` com rotação automática de arquivos.

---

## Estrutura do Projeto

- `main.py` – ponto de entrada da aplicação.
- `ui.py` – interface gráfica e fluxo de interação com o usuário.
- `printing.py` – montagem das etiquetas e comunicação com a impressora.
- `persistence.py` – salvamento de configurações, contadores e histórico.
- `utils.py` – utilitários, backup automático e migração de dados legados.
- `assets/` – ícones, configurações, modelos e arquivos de histórico.

---

## Arquitetura em 5 minutos

1. `main.py` inicializa o aplicativo e configura captura de falhas precoces.
2. `ui.py` constrói a interface gráfica utilizando `qt_compat`, que abstrai
   PyQt5 e PySide6.
3. `printing.py` monta comandos TSPL e envia dados para a impressora.
4. `persistence.py` gerencia arquivos de configuração, contadores e histórico.
5. `utils.py` fornece funções auxiliares como normalização de texto e backups.
6. `log.py` centraliza o registro de mensagens com rotação de arquivos.

---

## Contribuição

Contribuições são bem-vindas! Para sugerir melhorias ou reportar problemas:

1. Abra uma *issue* descrevendo o que deseja corrigir ou implementar.
2. Faça um *fork* do projeto, crie um *branch* e envie um *pull request* com a
   alteração proposta.
3. Sempre inclua testes e descreva claramente as mudanças.

---

## Licença

Este projeto é distribuído sob a **licença MIT**. Você pode usar, copiar,
modificar e distribuir o software, desde que preserve o aviso de copyright e a
licença original.

