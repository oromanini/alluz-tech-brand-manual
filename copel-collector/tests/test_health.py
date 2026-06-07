def test_health_retorna_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_health_sem_autenticacao(client):
    """Endpoint de saúde deve ser público."""
    resp = client.get("/health")
    assert resp.status_code == 200
