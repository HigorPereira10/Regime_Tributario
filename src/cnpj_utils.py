"""Limpeza, validação e formatação de CNPJ."""
import re

_PESOS_CNPJ_DV1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
_PESOS_CNPJ_DV2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
_PESOS_CPF_DV1 = [10, 9, 8, 7, 6, 5, 4, 3, 2]
_PESOS_CPF_DV2 = [11, 10, 9, 8, 7, 6, 5, 4, 3, 2]


def apenas_digitos(valor: str) -> str:
    """Remove qualquer caractere que não seja dígito, sem completar com zeros."""
    if valor is None:
        return ""
    return re.sub(r"\D", "", str(valor))


def _limpar_caracteres_cnpj(valor: str) -> str:
    """Remove formatação (pontos, barra, hífen, espaços) preservando letras.

    Diferente do CPF, não da para descartar letras do CNPJ, porque os novos CNPJs são alfanuméricos (2026 em diante).
    """
    if valor is None:
        return ""
    return re.sub(r"[^0-9A-Za-z]", "", str(valor)).upper()


def limpar_cnpj(valor: str) -> str:
    """Extrai o CNPJ (dígitos e letras) e completa com zeros à esquerda quando necessário.
    
    Quando a planilha guarda o CNPJ como número (não texto), o Excel descarta zeros à esquerda, "05243856000101" vira "5243856000101".
    Completamos com zeros à esquerda para não invalidar CNPJs legítimos que começam com 0.
    """
    cnpj = _limpar_caracteres_cnpj(valor)
    if 0 < len(cnpj) <= 14:
        cnpj = cnpj.zfill(14)
    return cnpj


def _valor_caractere(caractere: str) -> int:
    """Valor numérico de um caractere do CNPJ para o dígito verificador: dígitos valem seu próprio valor,
    letras (A-Z) valem seu código ASCII menos 48 (ex: 'A' = 65 - 48 = 17), regra oficial do CNPJ alfanumérico."""
    return ord(caractere) - 48


def _calcular_digito(base: str, pesos: list[int]) -> str:
    """Calcula o dígito verificador de um CNPJ a partir da base e da lista de pesos"""
    soma = sum(_valor_caractere(caractere) * peso for caractere, peso in zip(base, pesos))
    resto = soma % 11
    return "0" if resto < 2 else str(11 - resto)


def validar_cnpj(valor: str) -> bool:
    """Valida um CNPJ (numérico ou alfanumérico) pelo algoritmo oficial de dígitos verificadores.
    Os 12 primeiros caracteres podem ser letras ou números; os 2 dígitos verificadores finais são sempre numéricos."""
    
    cnpj = limpar_cnpj(valor)

    if len(cnpj) != 14:
        return False
    if not cnpj[12:].isdigit():
        return False
    if cnpj == cnpj[0] * 14:
        return False

    dv1 = _calcular_digito(cnpj[:12], _PESOS_CNPJ_DV1)
    dv2 = _calcular_digito(cnpj[:12] + dv1, _PESOS_CNPJ_DV2)

    return cnpj[-2:] == dv1 + dv2


def validar_cpf(valor: str) -> bool:
    """Verifica se o valor é um CPF válido, usado para exibir erro quando tem um CPF na base de consulta."""
    cpf = apenas_digitos(valor)

    if len(cpf) != 11:
        return False
    if cpf == cpf[0] * 11:
        return False

    dv1 = _calcular_digito(cpf[:9], _PESOS_CPF_DV1)
    dv2 = _calcular_digito(cpf[:9] + dv1, _PESOS_CPF_DV2)

    return cpf[-2:] == dv1 + dv2


def formatar_cpf(valor: str) -> str:
    """Formata um CPF como XXX.XXX.XXX-XX. Retorna o valor original se não tiver 11 dígitos."""
    cpf = apenas_digitos(valor)
    if len(cpf) != 11:
        return valor
    return f"{cpf[0:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:11]}"


def formatar_cnpj(valor: str) -> str:
    """Formata um CNPJ limpo como XX.XXX.XXX/XXXX-XX. Retorna o valor original se não tiver 14 dígitos."""
    cnpj = limpar_cnpj(valor)
    if len(cnpj) != 14:
        return valor
    return f"{cnpj[0:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:14]}"
