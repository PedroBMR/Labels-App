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

## Testes

Para executar a suíte de testes automatizados, instale as dependências e rode:

```
pytest -q
```

## Como buildar local

1. Instale as dependências:

   ```
   pip install pyinstaller pyqt5 pillow pywin32
   ```

2. Gere o executável:

   ```
   pyinstaller GeradorEtiquetas_onefile.spec
   ```

   O binário será criado em `dist/GeradorEtiquetas.exe`.

## Como baixar o artifact

Após um push ou pull request, o workflow **Build Windows Executable** gera um artifact com o executável.

1. Acesse a aba **Actions** do repositório no GitHub.
2. Abra a execução mais recente do workflow.
3. Baixe o artifact **GeradorEtiquetas** para obter `GeradorEtiquetas.exe`.

## Atualização do aplicativo

O pacote de atualização deve conter `Updater.bat`, `manifest.json` e o novo `GeradorEtiquetas.exe`.

Exemplo de `manifest.json`:

```json
{
  "exe": "GeradorEtiquetas.exe",
  "version": "1.2.3",
  "sha256": "EXEMPLODEHASH..."
}
```

Sequência de uso:

1. **Simular ações (dry-run)**:

   ```
   Updater.bat /D
   ```

   Saída típica:

   ```
   [Dry-run] Nenhuma alteracao sera feita.
   [DRY-RUN] copy "GeradorEtiquetas.exe" "GeradorEtiquetas.exe"
   [DRY-RUN] certutil -hashfile "GeradorEtiquetas.exe" SHA256
   [DRY-RUN] echo 1.2.3 > version.txt
   [DRY-RUN] copy "_internal\historico_impressoes.csv" "assets\historico_impressoes.csv"
   [DRY-RUN] ren "_internal" "_internal.bak-AAAAMMDD_HHMM"
   ```

2. **Aplicar atualização**:

   ```
   Updater.bat
   ```

   Saída típica:

   ```
   Copiando novo executavel...
   Hash SHA256 validado com sucesso.
   Copiando historico_impressoes.csv para assets.
   Renomeando _internal para _internal.bak-AAAAMMDD_HHMM.
   Atualizacao concluida.
   ```

---

## Autor

