"""
Testes dos endpoints de autenticação.

Cobre todos os cenários de sucesso e falha para:
- POST /auth/registro
- POST /auth/login
- GET  /auth/me
"""
import pytest
from fastapi.testclient import TestClient

_USUARIO = {"email": "usuario@alluz.com.br", "password": "senha12345"}


# ── Registro ──────────────────────────────────────────────────────────────────

class TestRegistro:
    def test_sucesso_retorna_201_e_dados_do_usuario(self, client: TestClient):
        resp = client.post("/auth/registro", json=_USUARIO)
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == _USUARIO["email"]
        assert "id" in data
        assert "created_at" in data

    def test_nao_expoe_hash_da_senha(self, client: TestClient):
        resp = client.post("/auth/registro", json=_USUARIO)
        assert "hashed_password" not in resp.json()
        assert "password" not in resp.json()

    def test_email_duplicado_retorna_409(self, client: TestClient):
        client.post("/auth/registro", json=_USUARIO)
        resp = client.post("/auth/registro", json=_USUARIO)
        assert resp.status_code == 409
        assert "erro" in resp.json()["detail"]

    def test_email_invalido_retorna_422(self, client: TestClient):
        resp = client.post("/auth/registro", json={"email": "nao-e-email", "password": "senha12345"})
        assert resp.status_code == 422

    def test_senha_com_menos_de_8_chars_retorna_422(self, client: TestClient):
        resp = client.post("/auth/registro", json={"email": "x@x.com", "password": "abc"})
        assert resp.status_code == 422

    def test_sem_email_retorna_422(self, client: TestClient):
        resp = client.post("/auth/registro", json={"password": "senha12345"})
        assert resp.status_code == 422

    def test_sem_senha_retorna_422(self, client: TestClient):
        resp = client.post("/auth/registro", json={"email": "x@x.com"})
        assert resp.status_code == 422

    def test_body_vazio_retorna_422(self, client: TestClient):
        resp = client.post("/auth/registro", json={})
        assert resp.status_code == 422


# ── Login ─────────────────────────────────────────────────────────────────────

class TestLogin:
    def test_sucesso_retorna_token_bearer(self, client: TestClient, usuario_registrado: dict):
        resp = client.post(
            "/auth/login",
            json={"email": usuario_registrado["email"], "password": "senha12345"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert len(data["access_token"]) > 20

    def test_senha_errada_retorna_401(self, client: TestClient, usuario_registrado: dict):
        resp = client.post(
            "/auth/login",
            json={"email": _USUARIO["email"], "password": "senhaerrada"},
        )
        assert resp.status_code == 401

    def test_email_nao_cadastrado_retorna_401(self, client: TestClient):
        resp = client.post(
            "/auth/login",
            json={"email": "nao@existe.com", "password": "qualquer"},
        )
        assert resp.status_code == 401

    def test_sem_email_retorna_422(self, client: TestClient):
        resp = client.post("/auth/login", json={"password": "senha12345"})
        assert resp.status_code == 422

    def test_sem_senha_retorna_422(self, client: TestClient):
        resp = client.post("/auth/login", json={"email": "x@x.com"})
        assert resp.status_code == 422

    def test_email_invalido_retorna_422(self, client: TestClient):
        resp = client.post("/auth/login", json={"email": "invalido", "password": "senha12345"})
        assert resp.status_code == 422


# ── Endpoint /me ──────────────────────────────────────────────────────────────

class TestMe:
    def test_retorna_dados_do_usuario_autenticado(
        self, client: TestClient, headers_auth: dict, usuario_registrado: dict
    ):
        resp = client.get("/auth/me", headers=headers_auth)
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == usuario_registrado["email"]
        assert data["id"] == usuario_registrado["id"]

    def test_sem_token_retorna_401(self, client: TestClient):
        resp = client.get("/auth/me")
        assert resp.status_code == 401

    def test_token_invalido_retorna_401(self, client: TestClient):
        resp = client.get("/auth/me", headers={"Authorization": "Bearer tokeninvalido"})
        assert resp.status_code == 401

    def test_token_mal_formado_retorna_401(self, client: TestClient):
        resp = client.get("/auth/me", headers={"Authorization": "SemBearer abc123"})
        assert resp.status_code == 401

    def test_header_authorization_vazio_retorna_401(self, client: TestClient):
        resp = client.get("/auth/me", headers={"Authorization": ""})
        assert resp.status_code == 401
