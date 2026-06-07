"""
Configuração global de testes.

DATABASE_URL é sobrescrito para SQLite em memória antes de qualquer import
de módulos da app, garantindo que nenhum dado de teste toque o banco real.
"""
import os
import pytest

# Deve ser setado ANTES dos imports da app para que o engine seja criado com a URL de teste
os.environ["DATABASE_URL"] = "sqlite:///./test_copel.db"
os.environ["SECRET_KEY"] = "test-secret-key-nao-usar-em-producao"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402

TEST_DB_URL = "sqlite:///./test_copel.db"
_test_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
_TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=_test_engine)


@pytest.fixture(scope="session", autouse=True)
def _create_tables():
    """Cria as tabelas no banco de teste uma única vez por sessão de testes."""
    Base.metadata.create_all(bind=_test_engine)
    yield
    Base.metadata.drop_all(bind=_test_engine)
    _test_engine.dispose()
    if os.path.exists("./test_copel.db"):
        os.remove("./test_copel.db")


@pytest.fixture(autouse=True)
def _limpar_tabelas():
    """Limpa todas as linhas após cada teste para isolamento completo."""
    yield
    db = _TestingSession()
    for table in reversed(Base.metadata.sorted_tables):
        db.execute(table.delete())
    db.commit()
    db.close()


@pytest.fixture
def client() -> TestClient:
    """TestClient com banco de teste injetado via dependency override."""

    def _override_get_db():
        db = _TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ── Fixtures de autenticação reutilizáveis ────────────────────────────────────

_TEST_EMAIL = "teste@alluz.com.br"
_TEST_PASSWORD = "senha12345"


@pytest.fixture
def usuario_registrado(client: TestClient) -> dict:
    resp = client.post(
        "/auth/registro",
        json={"email": _TEST_EMAIL, "password": _TEST_PASSWORD},
    )
    assert resp.status_code == 201, resp.json()
    return resp.json()


@pytest.fixture
def token(client: TestClient, usuario_registrado: dict) -> str:
    resp = client.post(
        "/auth/login",
        json={"email": _TEST_EMAIL, "password": _TEST_PASSWORD},
    )
    assert resp.status_code == 200, resp.json()
    return resp.json()["access_token"]


@pytest.fixture
def headers_auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
