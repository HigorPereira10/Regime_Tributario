# Consulta de Regime Tributário em Lote

Aplicativo desktop para consultar em lote o regime tributário (Simples
Nacional, MEI ou Regime Normal/Lucro) de uma lista de CNPJs, a partir de uma
planilha Excel ou CSV, usando a [BrasilAPI](https://brasilapi.com.br/).

Interface construída em Streamlit e empacotada como aplicativo desktop nativo
(janela própria, sem navegador nem terminal) usando `pywebview` + PyInstaller.

## Estrutura do projeto

```
main.py                 Ponto de entrada do app desktop (sobe o servidor e abre a janela)
app.py                  Interface Streamlit
src/
  cnpj_utils.py          Limpeza, validação (dígito verificador) e formatação de CNPJ
  api_client.py           Cliente HTTP da BrasilAPI, com retry/backoff
  classifier.py            Regra de negócio de classificação do regime
  processor.py             Orquestração do lote (threads + progresso)
  excel_io.py               Leitura do upload e geração do Excel de resultado
.streamlit/config.toml   Tema visual (cores, tipografia)
assets/style.css          CSS customizado (cabeçalho, cards, badges)
assets/icon.ico            Ícone do executável/janela
build.spec                Configuração do PyInstaller
requirements.txt          Dependências da interface (usado também pelo Streamlit Community Cloud)
requirements-desktop.txt   Dependências extras só para rodar/empacotar a versão desktop (pywebview, PyInstaller)
```

## Rodando em modo desenvolvimento (desktop)

```powershell
py -m venv .venv
.venv\Scripts\pip install -r requirements-desktop.txt
.venv\Scripts\python main.py
```

Isso abre a janela do aplicativo diretamente. Para depurar a interface no
navegador (com auto-reload), rode o Streamlit puro em vez do launcher:

```powershell
.venv\Scripts\streamlit run app.py
```

## Gerando o executável (.exe)

```powershell
.venv\Scripts\pip install -r requirements-desktop.txt
.venv\Scripts\python -m PyInstaller build.spec --noconfirm
```

O resultado fica em `dist\RegimeTributario\` — uma pasta completa (modo
`--onedir`) contendo `RegimeTributario.exe` e todas as dependências. Essa
pasta inteira é o que deve ser distribuída/copiada para a máquina de cada
colaborador; o `.exe` não funciona sozinho, fora da pasta.

Para distribuir, compacte a pasta `dist\RegimeTributario` (ou embrulhe num
instalador, ex: Inno Setup) e envie para os colaboradores. Um atalho para
`RegimeTributario.exe` pode ser criado na área de trabalho ou no menu iniciar.

**Observação:** o pacote gerado tem ~230MB (inclui o runtime Python e todas
as bibliotecas). Isso é esperado para apps empacotados com PyInstaller.

## Uso

1. Abra o aplicativo pelo atalho.
2. Envie uma planilha `.xlsx` ou `.csv` contendo uma coluna com os CNPJs.
3. Confirme (ou selecione manualmente) qual coluna contém os CNPJs.
4. Clique em "Iniciar Consulta" e acompanhe a barra de progresso.
5. Veja o resumo por regime tributário e baixe a planilha de resultados.

CNPJs mal formatados, inválidos, não encontrados na Receita ou com falha de
conexão são marcados na respectiva linha ("CNPJ inválido", "CNPJ não
encontrado" ou "Erro na consulta") sem interromper o processamento do lote.

## Atualizando o app nos computadores do escritório

Como cada colaborador tem uma cópia local instalada, atualizações de código
exigem gerar um novo build (`PyInstaller build.spec`) e redistribuir a pasta
`dist\RegimeTributario` novamente para cada máquina.

## Deploy na nuvem (Streamlit Community Cloud)

A interface (`app.py`) também roda como site, sem precisar do launcher
desktop (`main.py`, que depende de `pywebview` e só funciona localmente).
No Streamlit Community Cloud, ao criar o app, configure:

- **Main file path:** `app.py`
- Dependências: o serviço já lê o `requirements.txt` da raiz automaticamente
  (não usa o `requirements-desktop.txt`).
