import httpx
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from .config import BRASILAPI_URL, CNPJ_WS_URL, TENTATIVAS, TIMEOUT_REQUISICAO

BASE_URL = BRASILAPI_URL
FALLBACK_URL = CNPJ_WS_URL
TIMEOUT_PADRAO = TIMEOUT_REQUISICAO
TENTATIVAS_PADRAO = TENTATIVAS


class ErroTemporario(Exception):
    """Falha que justifica nova tentativa: timeout, erro de conexão, HTTP 429 ou 5xx."""


class CNPJNaoEncontrado(Exception):
    """A Receita não possui registro para o CNPJ informado (HTTP 404)."""


def criar_client() -> httpx.Client:
    """Cria um client HTTP reutilizável e seguro para uso concorrente entre threads com 10 conexões simultâneas."""
    limites = httpx.Limits(max_connections=10, max_keepalive_connections=10)
    return httpx.Client(limits=limites, headers={"User-Agent": "consulta-regime-tributario/1.0"})


def _fazer_requisicao(client: httpx.Client, cnpj: str, timeout: float) -> dict:
    """Faz a requisição HTTP para a BrasilAPI, levantando exceções apropriadas em caso de falhas."""
    try:
        resposta = client.get(BASE_URL.format(cnpj=cnpj), timeout=timeout)
    except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError) as exc:
        raise ErroTemporario(str(exc)) from exc

    if resposta.status_code == 404:
        raise CNPJNaoEncontrado(cnpj)
    if resposta.status_code == 429 or resposta.status_code >= 500:
        raise ErroTemporario(f"HTTP {resposta.status_code}")

    resposta.raise_for_status()
    return resposta.json()


def consultar_cnpj(
    client: httpx.Client,
    cnpj: str,
    timeout: float = TIMEOUT_PADRAO,
    tentativas: int = TENTATIVAS_PADRAO,
) -> dict:
    """Consulta um CNPJ na BrasilAPI, retentando com backoff em falhas temporárias.

    Levanta CNPJNaoEncontrado se a Receita não tiver o CNPJ, ou ErroTemporario se todas as tentativas de rede falharem.
    """
    for tentativa in Retrying(
        stop=stop_after_attempt(tentativas),
        wait=wait_exponential(multiplier=1, min=1, max=20),
        retry=retry_if_exception_type(ErroTemporario),
        reraise=True,
    ):
        with tentativa:
            return _fazer_requisicao(client, cnpj, timeout)


def _extrair_dados_fallback(payload: dict) -> dict:
    """Normaliza a resposta da CNPJ.ws para o mesmo formato usado pela BrasilAPI."""
    estabelecimento = payload.get("estabelecimento") or {}
    simples = payload.get("simples") or {}
    return {
        "razao_social": payload.get("razao_social", ""),
        "descricao_situacao_cadastral": estabelecimento.get("situacao_cadastral", ""),
        "opcao_pelo_mei": str(simples.get("mei", "")).strip().lower() == "sim",
        "opcao_pelo_simples": str(simples.get("simples", "")).strip().lower() == "sim",
    }


def consultar_cnpj_fallback(client: httpx.Client, cnpj: str, timeout: float = TIMEOUT_PADRAO) -> dict:
    """Consulta de reforço na CNPJ.ws, usada só quando a BrasilAPI não encontra o CNPJ.

    A BrasilAPI atualiza sua base periodicamente, então empresas abertas há poucos dias podem não constar
    ainda mesmo já estando ativas na Receita. A CNPJ.ws tem limite de 3 requisições/minuto no plano gratuito,
    por isso só é usada como reforço pontual, nunca no lote principal.
    """
    try:
        resposta = client.get(FALLBACK_URL.format(cnpj=cnpj), timeout=timeout)
    except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError) as exc:
        raise ErroTemporario(str(exc)) from exc

    if resposta.status_code == 404:
        raise CNPJNaoEncontrado(cnpj)
    if resposta.status_code == 429 or resposta.status_code >= 500:
        raise ErroTemporario(f"HTTP {resposta.status_code}")

    resposta.raise_for_status()
    return _extrair_dados_fallback(resposta.json())
