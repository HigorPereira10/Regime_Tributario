"""Leitura da planilha enviada pelo usuário e geração do Excel de resultados formatado."""
from io import BytesIO
from typing import IO, Optional

import pandas as pd

from .classifier import MEI, REGIME_NORMAL, SIMPLES_NACIONAL
from .processor import STATUS_E_CPF, STATUS_ERRO, STATUS_INVALIDO, STATUS_NAO_ENCONTRADO

# Colunas candidatas a conter CNPJs ou nomes de empresas, usadas para detecção automática.
COLUNAS_CANDIDATAS_CNPJ = ("cnpj",)
COLUNAS_CANDIDATAS_EMPRESA = ("empresa", "nome", "razao social", "razão social", "cliente")

_CORES_LINHA = {
    SIMPLES_NACIONAL: "#DCFCE7",
    MEI: "#FEF3C7",
    REGIME_NORMAL: "#E2E8F0",
}
_COR_ERRO = "#FEE2E2"
_STATUS_ERRO_TIPOS = {STATUS_ERRO, STATUS_INVALIDO, STATUS_E_CPF, STATUS_NAO_ENCONTRADO}

_LEGENDA = [
    (SIMPLES_NACIONAL, "#DCFCE7", "Empresa optante pelo Simples Nacional"),
    (MEI, "#FEF3C7", "Microempreendedor Individual"),
    (REGIME_NORMAL, "#E2E8F0", "Lucro Presumido / Lucro Real"),
    ("Erro / CNPJ inválido ou é CPF / não encontrado", "#FEE2E2", "Falha na consulta, ver coluna Status da Consulta"),
]


def ler_planilha(arquivo: IO, nome_arquivo: str) -> pd.DataFrame:
    """Lê um arquivo .xlsx ou .csv enviado pelo usuário em um DataFrame."""
    if nome_arquivo.lower().endswith(".csv"):
        return pd.read_csv(arquivo, dtype=str)
    return pd.read_excel(arquivo, dtype=str)


def detectar_coluna_cnpj(colunas: list[str]) -> Optional[str]:
    """Tenta detectar automaticamente qual coluna contém os CNPJs pelo nome."""
    for coluna in colunas:
        nome_normalizado = str(coluna).strip().lower()
        if any(candidata in nome_normalizado for candidata in COLUNAS_CANDIDATAS_CNPJ):
            return coluna
    return None


def detectar_coluna_empresa(colunas: list[str]) -> Optional[str]:
    """Tenta detectar automaticamente qual coluna contém o nome da empresa."""
    for coluna in colunas:
        nome_normalizado = str(coluna).strip().lower()
        if any(candidata in nome_normalizado for candidata in COLUNAS_CANDIDATAS_EMPRESA):
            return coluna
    return None


def montar_dataframe_resultado(
    df_original: pd.DataFrame,
    resultados: list[dict],
    coluna_cnpj: str,
    coluna_empresa: Optional[str] = None,
) -> pd.DataFrame:
    """Monta a planilha de resultado com CNPJ, Nome da Empresa e Regime Tributário logo nas três primeiras colunas.
    O nome da empresa vem da planilha original quando disponível; caso contrário (ou se a célula estiver vazia), 
    usa a razão social retornada pela BrasilAPI.
    """
    df_original = df_original.reset_index(drop=True)

    nomes_planilha = (
        df_original[coluna_empresa] if coluna_empresa else pd.Series([None] * len(df_original))
    )

    def nome_final(indice: int) -> str:
        valor_planilha = nomes_planilha.iloc[indice]
        if pd.notna(valor_planilha) and str(valor_planilha).strip():
            return str(valor_planilha).strip()
        return resultados[indice]["razao_social"]

    df_resultado = pd.DataFrame({
        "CNPJ": [linha["cnpj_formatado"] for linha in resultados],
        "Nome da Empresa": [nome_final(i) for i in range(len(resultados))],
        "Regime Tributário": [linha["regime_tributario"] for linha in resultados],
        "Situação Cadastral": [linha["situacao_cadastral"] for linha in resultados],
        "Status da Consulta": [linha["status"] for linha in resultados],
    })

    colunas_extras = [c for c in df_original.columns if c not in (coluna_cnpj, coluna_empresa)]
    for coluna in colunas_extras:
        df_resultado[coluna] = df_original[coluna].values

    return df_resultado


def gerar_excel_resultado(df_resultado: pd.DataFrame) -> BytesIO:
    """Gera um .xlsx formatado (cores por regime/status, colunas ajustadas) em memória."""
    buffer = BytesIO()

    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        df_resultado.to_excel(writer, index=False, sheet_name="Resultado")

        workbook = writer.book
        worksheet = writer.sheets["Resultado"]

        formato_cabecalho = workbook.add_format({
            "bold": True,
            "bg_color": "#1E3A8A",
            "font_color": "#FFFFFF",
            "border": 1,
        })
        for coluna_idx, nome_coluna in enumerate(df_resultado.columns):
            worksheet.write(0, coluna_idx, nome_coluna, formato_cabecalho)
            maior_valor = df_resultado[nome_coluna].fillna("").astype(str).map(len).max() if len(df_resultado) else 0
            largura = max(len(str(nome_coluna)), maior_valor) + 2
            worksheet.set_column(coluna_idx, coluna_idx, min(largura, 45))

        formatos_regime = {
            regime: workbook.add_format({"bg_color": cor}) for regime, cor in _CORES_LINHA.items()
        }
        formato_erro = workbook.add_format({"bg_color": _COR_ERRO})

        coluna_status_idx = df_resultado.columns.get_loc("Status da Consulta")
        coluna_regime_idx = df_resultado.columns.get_loc("Regime Tributário")
        num_colunas = len(df_resultado.columns)

        for linha_idx in range(len(df_resultado)):
            status = df_resultado.iat[linha_idx, coluna_status_idx]
            regime = df_resultado.iat[linha_idx, coluna_regime_idx]

            formato = formato_erro if status in _STATUS_ERRO_TIPOS else formatos_regime.get(regime)
            if formato is None:
                continue
            for coluna_idx in range(num_colunas):
                valor = df_resultado.iat[linha_idx, coluna_idx]
                valor = "" if pd.isna(valor) else valor
                worksheet.write(linha_idx + 1, coluna_idx, valor, formato)

        if len(df_resultado):
            worksheet.autofilter(0, 0, len(df_resultado), num_colunas - 1)
        worksheet.freeze_panes(1, 0)

        _escrever_legenda(workbook)

    buffer.seek(0)
    return buffer


def _escrever_legenda(workbook) -> None:
    """Cria uma aba separada explicando o que cada cor da tabela significa."""
    aba = workbook.add_worksheet("Legenda")

    formato_titulo = workbook.add_format({"bold": True, "font_size": 13})
    formato_cabecalho = workbook.add_format({
        "bold": True,
        "bg_color": "#1E3A8A",
        "font_color": "#FFFFFF",
        "border": 1,
    })

    aba.write(0, 0, "Legenda de cores, Resultado da consulta", formato_titulo)
    aba.write(2, 0, "Regime / Status", formato_cabecalho)
    aba.write(2, 1, "Cor", formato_cabecalho)
    aba.write(2, 2, "Descrição", formato_cabecalho)

    for linha_idx, (rotulo, cor, descricao) in enumerate(_LEGENDA, start=3):
        formato_swatch = workbook.add_format({"bg_color": cor, "border": 1})
        aba.write(linha_idx, 0, rotulo)
        aba.write(linha_idx, 1, "", formato_swatch)
        aba.write(linha_idx, 2, descricao)

    aba.set_column(0, 0, 38)
    aba.set_column(1, 1, 8)
    aba.set_column(2, 2, 55)
