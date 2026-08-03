"""Organiza a consulta em lote: validação, chamadas concorrentes e progresso."""
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

from .api_client import (
    CNPJNaoEncontrado,
    ErroTemporario,
    consultar_cnpj,
    consultar_cnpj_fallback,
    criar_client,
)
from .classifier import classificar_regime
from .cnpj_utils import formatar_cnpj, formatar_cpf, limpar_cnpj, validar_cnpj, validar_cpf
from .config import INTERVALO_FALLBACK, INTERVALO_MINIMO, MAX_WORKERS

MAX_WORKERS_PADRAO = MAX_WORKERS
INTERVALO_MINIMO_PADRAO = INTERVALO_MINIMO  # No máximo 4 requisições somadas entre todas as threads
INTERVALO_FALLBACK_PADRAO = INTERVALO_FALLBACK  # CNPJ.ws (reforço) permite só 3 requisições/minuto


class LimitadorDeTaxa:
    """Impõe um intervalo mínimo entre o início de requisições, mesmo com várias threads em paralelo. 
    A BrasilAPI é gratuita e aplica rate limit (HTTP 429) quando o volume de chamadas simultâneas é alto,
    sem isso, lotes grandes (ex: 300+ CNPJs) acabam com boa parte marcada como "Erro na consulta".
    """
    def __init__(self, intervalo_minimo: float):
        self._intervalo_minimo = intervalo_minimo
        self._lock = threading.Lock()
        self._proxima_liberacao = 0.0

    def aguardar(self) -> None:
        with self._lock:
            agora = time.monotonic()
            espera = max(self._proxima_liberacao - agora, 0.0)
            self._proxima_liberacao = max(self._proxima_liberacao, agora) + self._intervalo_minimo
        if espera > 0:
            time.sleep(espera)


STATUS_OK = "OK"
STATUS_INVALIDO = "CNPJ inválido"
STATUS_E_CPF = "É um CPF, não um CNPJ"
STATUS_NAO_ENCONTRADO = "CNPJ não encontrado"
STATUS_ERRO = "Erro na consulta"

ProgressCallback = Callable[[int, int, str], None]


def _resultado_base(cnpj_bruto: str, status: str, **extra) -> dict:
    resultado = {
        "cnpj_original": cnpj_bruto,
        "cnpj_formatado": formatar_cnpj(cnpj_bruto),
        "razao_social": "",
        "situacao_cadastral": "",
        "regime_tributario": "",
        "status": status,
    }
    resultado.update(extra)
    return resultado


def _processar_um_cnpj(client, cnpj_bruto: str, limitador: LimitadorDeTaxa) -> dict:
    """Valida e consulta um único CNPJ, retornando o resultado em formato padronizado."""
    if not validar_cnpj(cnpj_bruto):
        if validar_cpf(cnpj_bruto):
            return _resultado_base(cnpj_bruto, STATUS_E_CPF, cnpj_formatado=formatar_cpf(cnpj_bruto))
        return _resultado_base(cnpj_bruto, STATUS_INVALIDO)

    cnpj_limpo = limpar_cnpj(cnpj_bruto)

    try:
        limitador.aguardar()
        dados = consultar_cnpj(client, cnpj_limpo)
    except CNPJNaoEncontrado:
        return _resultado_base(cnpj_bruto, STATUS_NAO_ENCONTRADO)
    except (ErroTemporario, Exception):
        # Captura ampla e intencional: uma falha isolada (rede, parsing, campo inesperado da API) nunca deve interromper o lote inteiro.
        return _resultado_base(cnpj_bruto, STATUS_ERRO)

    return _resultado_base(
        cnpj_bruto,
        STATUS_OK,
        cnpj_formatado=formatar_cnpj(cnpj_limpo),
        razao_social=dados.get("razao_social", ""),
        situacao_cadastral=dados.get("descricao_situacao_cadastral", ""),
        regime_tributario=classificar_regime(dados),
    )


def processar_lote(
    cnpjs: list[str],
    progress_callback: Optional[ProgressCallback] = None,
    max_workers: int = MAX_WORKERS_PADRAO,
    intervalo_minimo: float = INTERVALO_MINIMO_PADRAO,
) -> list[dict]:
    """Consulta uma lista de CNPJs em paralelo, preservando a ordem original.

    `progress_callback(concluidos, total, cnpj_atual)` é chamado a cada CNPJ finalizado, permitindo atualizar a UI em tempo real.
    `intervalo_minimo` controla o espaçamento entre requisições (proteção contra rate limit).
    """
    total = len(cnpjs)
    resultados: list[Optional[dict]] = [None] * total
    concluidos = 0
    lock = threading.Lock()
    limitador = LimitadorDeTaxa(intervalo_minimo)

    client = criar_client()
    try:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futuros = {
                executor.submit(_processar_um_cnpj, client, cnpj, limitador): indice
                for indice, cnpj in enumerate(cnpjs)
            }
            for futuro in as_completed(futuros):
                indice = futuros[futuro]
                resultados[indice] = futuro.result()
                with lock:
                    concluidos += 1
                    if progress_callback:
                        progress_callback(concluidos, total, cnpjs[indice])
    finally:
        client.close()

    _reprocessar_falhas_temporarias(cnpjs, resultados, progress_callback, total, intervalo_minimo)
    _reprocessar_nao_encontrados_com_fallback(cnpjs, resultados, progress_callback, total)

    return resultados


def _reprocessar_falhas_temporarias(
    cnpjs: list[str],
    resultados: list[dict],
    progress_callback: Optional[ProgressCallback],
    total: int,
    intervalo_minimo: float,
) -> None:
    """Revalida os CNPJs marcados como 'Erro na consulta' após uma pequena pausa.

    Na prática, a maior parte desses erros é rate limit passageiro da BrasilAPI durante lotes grandes:
    o mesmo CNPJ que falhou no meio de uma rajada de requisições responde normalmente segundos depois, fora da rajada.
    """
    indices_com_erro = [i for i, r in enumerate(resultados) if r["status"] == STATUS_ERRO]
    if not indices_com_erro:
        return

    if progress_callback:
        progress_callback(total, total, f"Revalidando {len(indices_com_erro)} pendência(s)…")

    time.sleep(3)

    limitador = LimitadorDeTaxa(intervalo_minimo)
    client = criar_client()
    try:
        for indice in indices_com_erro:
            resultados[indice] = _processar_um_cnpj(client, cnpjs[indice], limitador)
    finally:
        client.close()


def _reprocessar_nao_encontrados_com_fallback(
    cnpjs: list[str],
    resultados: list[dict],
    progress_callback: Optional[ProgressCallback],
    total: int,
) -> None:
    """Tenta uma fonte alternativa (CNPJ.ws) para CNPJs que a BrasilAPI não encontrou.

    A BrasilAPI atualiza sua base periodicamente: empresas abertas há poucos dias podem já estar ativas na Receita mas ainda não constar lá.
    A fonte de reforço tem limite de 3 consultas/minuto, então só é usada para essa sobra pontual, nunca no lote inteiro.
    """
    indices_nao_encontrados = [i for i, r in enumerate(resultados) if r["status"] == STATUS_NAO_ENCONTRADO]
    if not indices_nao_encontrados:
        return

    if progress_callback:
        progress_callback(total, total, f"Consultando fonte alternativa para {len(indices_nao_encontrados)} CNPJ(s)…")

    limitador = LimitadorDeTaxa(INTERVALO_FALLBACK_PADRAO)
    client = criar_client()
    try:
        for indice in indices_nao_encontrados:
            cnpj_bruto = cnpjs[indice]
            cnpj_limpo = limpar_cnpj(cnpj_bruto)
            limitador.aguardar()
            try:
                dados = consultar_cnpj_fallback(client, cnpj_limpo)
            except (CNPJNaoEncontrado, ErroTemporario, Exception):
                continue  # Mantém o status "CNPJ não encontrado"

            resultados[indice] = _resultado_base(
                cnpj_bruto,
                STATUS_OK,
                cnpj_formatado=formatar_cnpj(cnpj_limpo),
                razao_social=dados.get("razao_social", ""),
                situacao_cadastral=dados.get("descricao_situacao_cadastral", ""),
                regime_tributario=classificar_regime(dados),
            )
    finally:
        client.close()
