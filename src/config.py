"""Configurações do app"""
import os

from dotenv import load_dotenv

load_dotenv()

BRASILAPI_URL = os.getenv("BRASILAPI_URL", "https://brasilapi.com.br/api/cnpj/v1/{cnpj}")
CNPJ_WS_URL = os.getenv("CNPJ_WS_URL", "https://publica.cnpj.ws/cnpj/{cnpj}")

TIMEOUT_REQUISICAO = float(os.getenv("TIMEOUT_REQUISICAO", "10.0"))
TENTATIVAS = int(os.getenv("TENTATIVAS", "5"))

MAX_WORKERS = int(os.getenv("MAX_WORKERS", "5"))
INTERVALO_MINIMO = float(os.getenv("INTERVALO_MINIMO", "0.25"))
INTERVALO_FALLBACK = float(os.getenv("INTERVALO_FALLBACK", "21.0"))
