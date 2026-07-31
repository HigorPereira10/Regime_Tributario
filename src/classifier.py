"""Regra de negócio: classificação do regime tributário a partir do retorno da BrasilAPI."""

MEI = "MEI"
SIMPLES_NACIONAL = "Simples Nacional"
REGIME_NORMAL = "Regime Normal (Lucro)"


def classificar_regime(dados_api: dict) -> str:
    """Classifica a empresa com base nos campos opcao_pelo_mei / opcao_pelo_simples da BrasilAPI."""
    if dados_api.get("opcao_pelo_mei"):
        return MEI
    if dados_api.get("opcao_pelo_simples"):
        return SIMPLES_NACIONAL
    return REGIME_NORMAL
