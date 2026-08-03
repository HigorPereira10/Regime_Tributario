"""Interface Streamlit"""
import re
from pathlib import Path

import pandas as pd
import streamlit as st

from src.classifier import MEI, REGIME_NORMAL, SIMPLES_NACIONAL
from src.excel_io import (
    detectar_coluna_cnpj,
    detectar_coluna_empresa,
    gerar_excel_resultado,
    ler_planilha,
    montar_dataframe_resultado,
)
from src.processor import (
    STATUS_E_CPF,
    STATUS_ERRO,
    STATUS_INVALIDO,
    STATUS_NAO_ENCONTRADO,
    processar_lote,
)

# Configurações da página e estilo
BASE_DIR = Path(__file__).parent
STATUS_COM_FALHA = {STATUS_INVALIDO, STATUS_E_CPF, STATUS_NAO_ENCONTRADO, STATUS_ERRO}

_CORES_POR_REGIME = {
    SIMPLES_NACIONAL: ("#123524", "#7FE3AA"),
    MEI: ("#3A2A0A", "#F5C24D"),
    REGIME_NORMAL: ("#1E2836", "#B9C4D3"),
}
_COR_FALHA = ("#3A1414", "#F5A3A3")


def estilizar_resultado(df: pd.DataFrame) -> "pd.io.formats.style.Styler":
    """Aplica cores de fundo e texto as linhas do DataFrame de resultado, de acordo com o regime tributário ou status da consulta."""
    def cor_da_linha(linha: pd.Series) -> list[str]:
        if linha["Status da Consulta"] in STATUS_COM_FALHA:
            bg, cor_texto = _COR_FALHA
        else:
            bg, cor_texto = _CORES_POR_REGIME.get(linha["Regime Tributário"], ("", ""))
        estilo = f"background-color: {bg}; color: {cor_texto};" if bg else ""
        return [estilo] * len(linha)

    return df.style.apply(cor_da_linha, axis=1)


def legenda_cores() -> None:
    """Exibe a legenda de cores para os regimes tributários e erros."""
    itens = [(regime, bg, texto) for regime, (bg, texto) in _CORES_POR_REGIME.items()]
    itens.append(("Erro / não encontrado", _COR_FALHA[0], _COR_FALHA[1]))

    chips = "".join(
        f'<span class="legend__item"><span class="legend__dot" '
        f'style="background:{texto}"></span>{regime}</span>'
        for regime, _, texto in itens
    )
    st.markdown(f'<div class="legend">{chips}</div>', unsafe_allow_html=True)


st.set_page_config(
    page_title="Regime Tributário | Consulta em Lote",
    page_icon="🧾",
    layout="wide",
)


def carregar_css() -> None:
    """Carrega o CSS customizado para a interface Streamlit."""
    caminho_css = BASE_DIR / "assets" / "style.css"
    st.markdown(f"<style>{caminho_css.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


def cabecalho() -> None:
    """Exibe o cabeçalho da página contendo o título e subtítulo do app."""
    st.markdown(
        """
        <div class="app-header">
            <div class="app-header__icon">🧾</div>
            <div>
                <p class="app-header__title">Consulta de Regime Tributário</p>
                <p class="app-header__subtitle">Classificação em lote de CNPJs via BrasilAPI</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def indicador_de_etapas(fase_atual: str) -> None:
    """Exibe a barra de progresso com as etapas do fluxo: upload, processamento e resultado."""
    etapas = [("upload", "① Upload"), ("processando", "② Processamento"), ("resultado", "③ Resultado")]
    ordem = [chave for chave, _ in etapas]
    indice_atual = ordem.index(fase_atual)

    partes = []
    for i, (chave, rotulo) in enumerate(etapas):
        if i < indice_atual:
            classe = "is-done"
        elif i == indice_atual:
            classe = "is-active"
        else:
            classe = ""
        partes.append(f'<div class="step-indicator__item {classe}">{rotulo}</div>')
        if i < len(etapas) - 1:
            partes.append('<div class="step-indicator__line"></div>')

    st.markdown(f'<div class="step-indicator">{"".join(partes)}</div>', unsafe_allow_html=True)


def resetar_para_upload() -> None:
    """Limpa o estado da sessão para permitir uma nova consulta."""
    for chave in ("fase", "df_original", "coluna_cnpj", "coluna_empresa", "resultados", "nome_arquivo"):
        st.session_state.pop(chave, None)


def parse_cnpjs_manuais(texto: str) -> list[str]:
    """Quebra o texto digitado em CNPJs individuais (um por linha, ou separados por vírgula/ponto e vírgula)."""
    partes = re.split(r"[\n,;]+", texto)
    return [p.strip() for p in partes if p.strip()]


def tela_upload() -> None:
    with st.container(border=True):
        st.subheader("1. Informe os CNPJs")
        st.caption("Envie uma planilha ou digite os CNPJs manualmente.")

        aba_planilha, aba_manual = st.tabs(["📁 Enviar planilha", "⌨️ Digitar CNPJs"])

        with aba_planilha:
            _tela_upload_planilha()

        with aba_manual:
            _tela_upload_manual()


def _tela_upload_planilha() -> None:
    st.caption("Formatos aceitos: .xlsx ou .csv, a planilha deve conter uma coluna com os CNPJs a consultar.")

    arquivo = st.file_uploader("Planilha de CNPJs", type=["xlsx", "csv"], label_visibility="collapsed")

    if arquivo is None:
        return

    try:
        df = ler_planilha(arquivo, arquivo.name)
    except Exception as exc:
        st.error(f"Não foi possível ler a planilha: {exc}")
        return

    if df.empty:
        st.warning("A planilha enviada está vazia.")
        return

    st.markdown("**Pré-visualização**")
    st.dataframe(df.head(8), width='stretch')

    colunas = list(df.columns)
    coluna_sugerida = detectar_coluna_cnpj(colunas)
    indice_padrao = colunas.index(coluna_sugerida) if coluna_sugerida else 0

    coluna_cnpj = st.selectbox("Qual coluna contém os CNPJs?", colunas, index=indice_padrao)

    total_linhas = len(df)
    st.caption(f"{total_linhas} linha(s) serão processadas.")

    if st.button("Iniciar Consulta", type="primary", key="btn_iniciar_planilha"):
        st.session_state.df_original = df
        st.session_state.coluna_cnpj = coluna_cnpj
        st.session_state.coluna_empresa = detectar_coluna_empresa(colunas)
        st.session_state.nome_arquivo = arquivo.name
        st.session_state.fase = "processando"
        st.rerun()


def _tela_upload_manual() -> None:
    st.caption("Um CNPJ por linha (ou separados por vírgula), com ou sem formatação.")

    texto = st.text_area(
        "CNPJs",
        placeholder="12.345.678/0001-00\n98765432000155\n...",
        height=180,
        label_visibility="collapsed",
    )

    cnpjs = parse_cnpjs_manuais(texto) if texto else []
    if cnpjs:
        st.caption(f"{len(cnpjs)} CNPJ(s) detectado(s).")

    if st.button("Iniciar Consulta", type="primary", key="btn_iniciar_manual", disabled=not cnpjs):
        st.session_state.df_original = pd.DataFrame({"CNPJ": cnpjs})
        st.session_state.coluna_cnpj = "CNPJ"
        st.session_state.coluna_empresa = None
        st.session_state.nome_arquivo = "cnpjs_digitados.xlsx"
        st.session_state.fase = "processando"
        st.rerun()


def tela_processamento() -> None:
    with st.container(border=True):
        st.subheader("2. Consultando a BrasilAPI")

        df = st.session_state.df_original
        coluna_cnpj = st.session_state.coluna_cnpj
        cnpjs = df[coluna_cnpj].fillna("").astype(str).tolist()

        barra_progresso = st.progress(0.0)
        texto_status = st.empty()

        def callback(concluidos: int, total: int, cnpj_atual: str) -> None:
            barra_progresso.progress(concluidos / total)
            texto_status.markdown(f"Consultando **{concluidos}/{total}** — `{cnpj_atual}`")

        resultados = processar_lote(cnpjs, progress_callback=callback)

        st.session_state.resultados = resultados
        st.session_state.fase = "resultado"
    st.rerun()


def tela_resultado() -> None:
    resultados = st.session_state.resultados
    df_original = st.session_state.df_original

    total = len(resultados)
    contagem = {
        SIMPLES_NACIONAL: sum(1 for r in resultados if r["regime_tributario"] == SIMPLES_NACIONAL),
        MEI: sum(1 for r in resultados if r["regime_tributario"] == MEI),
        REGIME_NORMAL: sum(1 for r in resultados if r["regime_tributario"] == REGIME_NORMAL),
    }
    erros = sum(1 for r in resultados if r["status"] in STATUS_COM_FALHA)

    st.subheader("3. Resumo da consulta")
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total processado", total)
    col2.metric("Simples Nacional", contagem[SIMPLES_NACIONAL])
    col3.metric("MEI", contagem[MEI])
    col4.metric("Regime Normal (Lucro)", contagem[REGIME_NORMAL])
    col5.metric("Erros / não encontrados", erros)

    df_resultado = montar_dataframe_resultado(
        df_original,
        resultados,
        coluna_cnpj=st.session_state.coluna_cnpj,
        coluna_empresa=st.session_state.get("coluna_empresa"),
    )

    st.markdown("**Resultado detalhado**")
    legenda_cores()
    st.dataframe(estilizar_resultado(df_resultado), width='stretch', height=380)

    excel_bytes = gerar_excel_resultado(df_resultado).getvalue()
    nome_saida = f"resultado_regime_tributario_{st.session_state.get('nome_arquivo', 'consulta')}"
    if not nome_saida.lower().endswith(".xlsx"):
        nome_saida = nome_saida.rsplit(".", 1)[0] + ".xlsx"

    col_download, col_nova = st.columns([1, 1])
    with col_download:
        st.download_button(
            "⬇ Baixar Planilha de Resultados",
            data=excel_bytes,
            file_name=nome_saida,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width='stretch',
        )
    with col_nova:
        if st.button("Nova Consulta", width='stretch'):
            resetar_para_upload()
            st.rerun()


def main() -> None:
    carregar_css()
    cabecalho()

    fase = st.session_state.get("fase", "upload")
    indicador_de_etapas(fase)

    if fase == "upload":
        tela_upload()
    elif fase == "processando":
        tela_processamento()
    elif fase == "resultado":
        tela_resultado()


if __name__ == "__main__":
    main()
