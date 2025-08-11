# Labels-App

Aplicativo desktop para **geração e impressão de etiquetas térmicas** no padrão
CONIMS. Desenvolvido em Python, ele facilita o controle de saídas de material,
mantém histórico de impressões e permite personalizar o layout das etiquetas.

---

## Descrição Geral

O Labels-App ajuda instituições que precisam emitir etiquetas de identificação
para caixas e volumes. A aplicação gera etiquetas de 60x80&nbsp;mm, envia a
impressão diretamente para impressoras térmicas compatíveis com TSPL e armazena
todo o histórico gerado. É possível escolher modelos de layout, reimprimir
etiquetas e realizar backup automático dos dados.

---

## Funcionalidades

- Seleção da impressora padrão e configuração de modelos de etiqueta.
- Geração e impressão imediata de etiquetas térmicas.
- Reimpressão do último lote, de volumes faltantes ou de um intervalo
  específico.
- Histórico completo das impressões com exportação para CSV.
- Relatório mensal consolidado por categoria, município e emissor.
- Backup automático diário dos arquivos de dados.
- Personalização de layout através de templates definidos em `assets/templates.json`.

---

## Requisitos do Sistema

- **Python 3.11 ou superior**
- **PyQt5** para a interface gráfica
- **Pillow** para tratamento de imagens
- **pywin32** (somente no Windows) para envio direto à impressora
- Impressora térmica compatível com **TSPL** (ex.: Gainscha GS‑2406T)

Instale as dependências com:

```bash
pip install -r requirements.txt
```

---

## Instalação

### Ambiente de desenvolvimento

1. Clone o repositório e entre na pasta do projeto.
2. Crie um ambiente virtual opcional e instale as dependências.
3. Execute o aplicativo:

   ```bash
   python main.py
   ```

### Versão compilada (Windows)

1. Baixe `GeradorEtiquetas.exe` nas releases ou como artifact do fluxo de CI.
2. Coloque o arquivo em uma pasta com permissão de escrita.
3. Execute o `.exe` para abrir o aplicativo.

---

## Build no Windows via .spec

### Pré-requisitos

- Python 3.11 ou superior instalado e acessível pelo `python`.
- PowerShell.
- (Opcional) ambiente virtual em `.venv` ou `venv`.
- Pacotes `pyinstaller`, `pyqt5`, `pillow` e `pywin32` (instalados automaticamente pelos scripts).

### Comandos

```powershell
# executável único, sem console
scripts\build_onefile.ps1

# modo pasta para depuração
scripts\build_onedir.ps1
```

Os scripts ativam o ambiente virtual (se existir), instalam dependências
ausentes, rodam os arquivos `.spec` e copiam o executável final para
`dist\GeradorEtiquetas_v{versão}.exe`. É possível alterar o nome do
executável e o ícone definindo as variáveis de ambiente `APP_NAME` e
`APP_ICON` antes da execução.

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

## Atualizações

O arquivo `Updater.bat` automatiza a atualização do executável e dos dados.
Coloque `Updater.bat`, `manifest.json` e o novo `GeradorEtiquetas.exe` na mesma
pasta e execute:

```bat
Updater.bat /D   :: simula a atualização (dry‑run)
Updater.bat      :: aplica a atualização
```

O script valida o hash SHA256, cria backups e migra arquivos de histórico para a
pasta `assets/`. Mantenha sempre um backup do diretório antes de atualizar.

---

## Estrutura do Projeto

- `main.py` – ponto de entrada da aplicação.
- `ui.py` – interface gráfica e fluxo de interação com o usuário.
- `printing.py` – montagem das etiquetas e comunicação com a impressora.
- `persistence.py` – salvamento de configurações, contadores e histórico.
- `utils.py` – utilitários, backup automático e migração de dados legados.
- `assets/` – ícones, configurações, modelos e arquivos de histórico.
- `Updater.bat` – script de atualização do executável e dos dados.

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

