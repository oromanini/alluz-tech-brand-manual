"""
Testes do scraper Copel.

Para rodar os testes de integração real, defina as variáveis de ambiente:
  COPEL_CPF=xxx.xxx.xxx-xx
  COPEL_SENHA=suasenha

Os testes unitários (sem credenciais) verificam validações e schemas.
"""
import os
import pytest
from unittest.mock import AsyncMock, patch

from app.scraper import _parse_competencia, CopelScraperError
from app.schemas import FaturaRequest


# --- Testes unitários (sem rede) ---

def test_parse_competencia_valida():
    resultado = _parse_competencia("2025-05")
    assert resultado == (2025, 5)


def test_parse_competencia_none():
    assert _parse_competencia(None) is None


def test_parse_competencia_invalida():
    with pytest.raises(CopelScraperError):
        _parse_competencia("05-2025")


def test_fatura_request_schema():
    req = FaturaRequest(cpf_cnpj="123.456.789-00", senha="abc123")
    assert req.competencia is None


def test_fatura_request_com_competencia():
    req = FaturaRequest(cpf_cnpj="123.456.789-00", senha="abc123", competencia="2025-03")
    assert req.competencia == "2025-03"


# --- Teste de integração real (requer credenciais) ---

@pytest.mark.skipif(
    not os.getenv("COPEL_CPF") or not os.getenv("COPEL_SENHA"),
    reason="Credenciais Copel não configuradas (COPEL_CPF / COPEL_SENHA)",
)
@pytest.mark.asyncio
async def test_baixar_fatura_real():
    from app.scraper import baixar_fatura

    cpf = os.environ["COPEL_CPF"]
    senha = os.environ["COPEL_SENHA"]
    competencia = os.getenv("COPEL_COMPETENCIA")  # opcional

    pdf = await baixar_fatura(cpf, senha, competencia)

    assert pdf is not None
    assert len(pdf) > 1000
    assert pdf[:4] == b"%PDF", "O arquivo retornado não é um PDF válido"
