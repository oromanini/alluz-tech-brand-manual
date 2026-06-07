"""
Testes do endpoint POST /faturas/download.

O scraper Playwright é sempre mockado — estes testes validam a camada de API
(autenticação, validação de input, mapeamento de erros para HTTP codes) sem
depender de conexão real com o portal Copel.
"""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.scraper import CopelAuthError, CopelFaturaNotFoundError, CopelScraperError

_FAKE_PDF = b"%PDF-1.4 conteudo-falso-para-testes"
_PAYLOAD_BASE = {"cpf_cnpj": "123.456.789-00", "senha": "copelsenha"}
_SCRAPER_PATH = "app.main.baixar_fatura"


def _mock_scraper(return_value=_FAKE_PDF, side_effect=None):
    """Atalho para criar o mock do scraper."""
    if side_effect:
        return patch(_SCRAPER_PATH, new=AsyncMock(side_effect=side_effect))
    return patch(_SCRAPER_PATH, new=AsyncMock(return_value=return_value))


# ── Autenticação do endpoint ──────────────────────────────────────────────────

class TestAutenticacaoDoEndpoint:
    def test_sem_token_retorna_401(self, client: TestClient):
        resp = client.post("/faturas/download", json=_PAYLOAD_BASE)
        assert resp.status_code == 401

    def test_token_invalido_retorna_401(self, client: TestClient):
        resp = client.post(
            "/faturas/download",
            json=_PAYLOAD_BASE,
            headers={"Authorization": "Bearer tokeninvalido"},
        )
        assert resp.status_code == 401

    def test_token_mal_formado_retorna_401(self, client: TestClient):
        resp = client.post(
            "/faturas/download",
            json=_PAYLOAD_BASE,
            headers={"Authorization": "Basic abc123"},
        )
        assert resp.status_code == 401


# ── Validação de input ────────────────────────────────────────────────────────

class TestValidacaoDeInput:
    def test_sem_cpf_retorna_422(self, client: TestClient, headers_auth: dict):
        resp = client.post("/faturas/download", json={"senha": "copelsenha"}, headers=headers_auth)
        assert resp.status_code == 422

    def test_sem_senha_retorna_422(self, client: TestClient, headers_auth: dict):
        resp = client.post(
            "/faturas/download",
            json={"cpf_cnpj": "123.456.789-00"},
            headers=headers_auth,
        )
        assert resp.status_code == 422

    def test_body_vazio_retorna_422(self, client: TestClient, headers_auth: dict):
        resp = client.post("/faturas/download", json={}, headers=headers_auth)
        assert resp.status_code == 422

    def test_competencia_formato_invertido_retorna_422(self, client: TestClient, headers_auth: dict):
        resp = client.post(
            "/faturas/download",
            json={**_PAYLOAD_BASE, "competencia": "05-2025"},
            headers=headers_auth,
        )
        assert resp.status_code == 422

    def test_competencia_mes_13_retorna_422(self, client: TestClient, headers_auth: dict):
        resp = client.post(
            "/faturas/download",
            json={**_PAYLOAD_BASE, "competencia": "2025-13"},
            headers=headers_auth,
        )
        assert resp.status_code == 422

    def test_competencia_mes_00_retorna_422(self, client: TestClient, headers_auth: dict):
        resp = client.post(
            "/faturas/download",
            json={**_PAYLOAD_BASE, "competencia": "2025-00"},
            headers=headers_auth,
        )
        assert resp.status_code == 422

    def test_competencia_texto_livre_retorna_422(self, client: TestClient, headers_auth: dict):
        resp = client.post(
            "/faturas/download",
            json={**_PAYLOAD_BASE, "competencia": "maio de 2025"},
            headers=headers_auth,
        )
        assert resp.status_code == 422


# ── Cenários de sucesso ───────────────────────────────────────────────────────

class TestDownloadSucesso:
    def test_retorna_200_com_pdf(self, client: TestClient, headers_auth: dict):
        with _mock_scraper():
            resp = client.post("/faturas/download", json=_PAYLOAD_BASE, headers=headers_auth)
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content == _FAKE_PDF

    def test_com_competencia_valida(self, client: TestClient, headers_auth: dict):
        with _mock_scraper():
            resp = client.post(
                "/faturas/download",
                json={**_PAYLOAD_BASE, "competencia": "2025-05"},
                headers=headers_auth,
            )
        assert resp.status_code == 200

    def test_competencia_mes_01(self, client: TestClient, headers_auth: dict):
        with _mock_scraper():
            resp = client.post(
                "/faturas/download",
                json={**_PAYLOAD_BASE, "competencia": "2025-01"},
                headers=headers_auth,
            )
        assert resp.status_code == 200

    def test_competencia_mes_12(self, client: TestClient, headers_auth: dict):
        with _mock_scraper():
            resp = client.post(
                "/faturas/download",
                json={**_PAYLOAD_BASE, "competencia": "2025-12"},
                headers=headers_auth,
            )
        assert resp.status_code == 200

    def test_nome_arquivo_inclui_competencia_no_header(self, client: TestClient, headers_auth: dict):
        with _mock_scraper():
            resp = client.post(
                "/faturas/download",
                json={**_PAYLOAD_BASE, "competencia": "2025-03"},
                headers=headers_auth,
            )
        assert "2025-03" in resp.headers["content-disposition"]

    def test_nome_arquivo_sem_competencia_usa_recente(self, client: TestClient, headers_auth: dict):
        with _mock_scraper():
            resp = client.post("/faturas/download", json=_PAYLOAD_BASE, headers=headers_auth)
        assert "recente" in resp.headers["content-disposition"]

    def test_scraper_recebe_cpf_senha_e_competencia_corretos(
        self, client: TestClient, headers_auth: dict
    ):
        mock = AsyncMock(return_value=_FAKE_PDF)
        with patch(_SCRAPER_PATH, new=mock):
            client.post(
                "/faturas/download",
                json={**_PAYLOAD_BASE, "competencia": "2025-06"},
                headers=headers_auth,
            )
        mock.assert_called_once_with(
            cpf_cnpj="123.456.789-00",
            senha="copelsenha",
            competencia="2025-06",
        )

    def test_scraper_recebe_none_para_competencia_omitida(
        self, client: TestClient, headers_auth: dict
    ):
        mock = AsyncMock(return_value=_FAKE_PDF)
        with patch(_SCRAPER_PATH, new=mock):
            client.post("/faturas/download", json=_PAYLOAD_BASE, headers=headers_auth)
        mock.assert_called_once_with(
            cpf_cnpj="123.456.789-00",
            senha="copelsenha",
            competencia=None,
        )


# ── Cenários de erro do portal Copel ─────────────────────────────────────────

class TestErrosDoPortalCopel:
    def test_credenciais_copel_invalidas_retorna_401(self, client: TestClient, headers_auth: dict):
        with _mock_scraper(side_effect=CopelAuthError("Credenciais inválidas")):
            resp = client.post("/faturas/download", json=_PAYLOAD_BASE, headers=headers_auth)
        assert resp.status_code == 401
        assert "erro" in resp.json()["detail"]

    def test_fatura_nao_encontrada_retorna_404(self, client: TestClient, headers_auth: dict):
        with _mock_scraper(side_effect=CopelFaturaNotFoundError("Mês não disponível")):
            resp = client.post(
                "/faturas/download",
                json={**_PAYLOAD_BASE, "competencia": "2020-01"},
                headers=headers_auth,
            )
        assert resp.status_code == 404
        assert "erro" in resp.json()["detail"]

    def test_timeout_portal_retorna_502(self, client: TestClient, headers_auth: dict):
        with _mock_scraper(side_effect=CopelScraperError("Timeout")):
            resp = client.post("/faturas/download", json=_PAYLOAD_BASE, headers=headers_auth)
        assert resp.status_code == 502
        assert "erro" in resp.json()["detail"]

    def test_layout_mudou_retorna_502(self, client: TestClient, headers_auth: dict):
        with _mock_scraper(side_effect=CopelScraperError("Campo de CPF não encontrado")):
            resp = client.post("/faturas/download", json=_PAYLOAD_BASE, headers=headers_auth)
        assert resp.status_code == 502

    def test_detalhe_de_erro_copel_aparece_na_resposta(self, client: TestClient, headers_auth: dict):
        mensagem = "Conta bloqueada por excesso de tentativas"
        with _mock_scraper(side_effect=CopelAuthError(mensagem)):
            resp = client.post("/faturas/download", json=_PAYLOAD_BASE, headers=headers_auth)
        assert resp.status_code == 401
        assert mensagem in resp.json()["detail"]["detalhe"]
