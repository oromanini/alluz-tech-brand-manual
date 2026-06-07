from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.responses import Response, HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db, init_db
from app.models import User
from app.auth import hash_password, verify_password, create_access_token, get_current_user
from app.schemas import (
    FaturaRequest,
    ErroResponse,
    RegistroRequest,
    LoginRequest,
    TokenResponse,
    UserResponse,
)
from app.scraper import baixar_fatura, CopelAuthError, CopelFaturaNotFoundError, CopelScraperError


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


_tags_metadata = [
    {
        "name": "Saúde",
        "description": "Verificação de disponibilidade do serviço.",
    },
    {
        "name": "Autenticação",
        "description": (
            "Registro de usuários e geração de tokens JWT.\n\n"
            "**Fluxo:** registre-se → faça login → use o `access_token` "
            "no header `Authorization: Bearer <token>` de todas as chamadas às Faturas."
        ),
    },
    {
        "name": "Faturas",
        "description": (
            "Download automatizado de faturas PDF via portal AVA da Copel.\n\n"
            "O serviço abre um browser headless, autentica com as credenciais do cliente "
            "e retorna o PDF diretamente — sem armazenar senha ou PDF."
        ),
    },
]

app = FastAPI(
    title="Alluz Copel Collector",
    description="""
API de coleta automatizada de faturas Copel para o produto de gestão solar da **Alluz Energia**.

## Como usar

1. **Crie sua conta** em `POST /auth/registro`
2. **Faça login** em `POST /auth/login` e guarde o `access_token`
3. Clique em **Authorize** (🔒) e cole o token no campo *Bearer*
4. **Baixe a fatura** em `POST /faturas/download` passando CPF e senha Copel do cliente

## Segurança

- Tokens JWT expiram em **60 minutos** (configurável via `ACCESS_TOKEN_EXPIRE_MINUTES`)
- Senhas armazenadas com **bcrypt**
- Credenciais Copel **nunca são persistidas** — usadas apenas durante a sessão do browser
""".strip(),
    version="1.0.0",
    openapi_tags=_tags_metadata,
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)


@app.get("/docs", include_in_schema=False)
async def scalar_docs() -> HTMLResponse:
    return HTMLResponse(
        content="""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Alluz Copel Collector — Documentação</title>
  <style>body { margin: 0; }</style>
</head>
<body>
  <script id="api-reference" data-url="/openapi.json"></script>
  <script src="https://cdn.jsdelivr.net/npm/@scalar/api-reference"></script>
</body>
</html>"""
    )


# ── Saúde ─────────────────────────────────────────────────────────────────────

@app.get(
    "/health",
    tags=["Saúde"],
    summary="Status do serviço",
    response_description="Serviço disponível",
)
async def health():
    """Retorna `ok` se o serviço está no ar."""
    return {"status": "ok"}


# ── Autenticação ──────────────────────────────────────────────────────────────

@app.post(
    "/auth/registro",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Autenticação"],
    summary="Criar conta de usuário",
    responses={
        409: {"model": ErroResponse, "description": "E-mail já cadastrado"},
        422: {"model": ErroResponse, "description": "Dados inválidos (e-mail malformado, senha curta)"},
    },
)
def registro(req: RegistroRequest, db: Session = Depends(get_db)):
    """
    Cria uma nova conta de usuário.

    - **email**: endereço válido, único no sistema
    - **password**: mínimo de 8 caracteres
    """
    if db.query(User).filter(User.email == req.email).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"erro": "E-mail já cadastrado.", "detalhe": str(req.email)},
        )
    user = User(email=req.email, hashed_password=hash_password(req.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.post(
    "/auth/login",
    response_model=TokenResponse,
    tags=["Autenticação"],
    summary="Autenticar e obter token Bearer",
    responses={
        401: {"model": ErroResponse, "description": "Credenciais inválidas"},
        422: {"model": ErroResponse, "description": "Campos ausentes ou malformados"},
    },
)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    """
    Autentica o usuário e retorna um JWT válido por 60 minutos.

    Use o `access_token` retornado no header:
    ```
    Authorization: Bearer <access_token>
    ```
    """
    user = db.query(User).filter(User.email == req.email).first()
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"erro": "E-mail ou senha incorretos."},
        )
    token = create_access_token({"sub": user.email})
    return TokenResponse(access_token=token)


@app.get(
    "/auth/me",
    response_model=UserResponse,
    tags=["Autenticação"],
    summary="Dados do usuário autenticado",
    responses={
        401: {"model": ErroResponse, "description": "Token ausente, inválido ou expirado"},
    },
)
def me(current_user: User = Depends(get_current_user)):
    """Retorna os dados do usuário dono do token enviado."""
    return current_user


# ── Faturas ───────────────────────────────────────────────────────────────────

@app.post(
    "/faturas/download",
    tags=["Faturas"],
    summary="Baixar PDF da fatura Copel",
    description="""
Abre um browser headless, faz login no portal **AVA da Copel** com as credenciais
informadas e retorna o PDF da fatura como download direto.

### Parâmetros

| Campo | Obrigatório | Descrição |
|-------|-------------|-----------|
| `cpf_cnpj` | ✅ | CPF ou CNPJ do titular da conta Copel |
| `senha` | ✅ | Senha da Agência Virtual (AVA) |
| `competencia` | ❌ | Mês no formato `YYYY-MM`. Omita para baixar a mais recente |

### Possíveis erros

| Código | Causa |
|--------|-------|
| `401` (sem token) | Header `Authorization` ausente ou token expirado |
| `401` (Copel) | CPF/CNPJ ou senha Copel incorretos |
| `404` | Fatura não encontrada para a competência informada |
| `422` | `competencia` em formato inválido ou campos ausentes |
| `502` | Timeout ou mudança de layout no portal Copel |
""".strip(),
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "PDF da fatura Copel",
        },
        401: {"model": ErroResponse, "description": "Token ausente/inválido ou credenciais Copel incorretas"},
        404: {"model": ErroResponse, "description": "Fatura não encontrada para a competência"},
        422: {"model": ErroResponse, "description": "Formato de competência inválido ou campos obrigatórios ausentes"},
        502: {"model": ErroResponse, "description": "Falha ao acessar o portal Copel"},
    },
)
async def download_fatura(
    req: FaturaRequest,
    _: User = Depends(get_current_user),
):
    try:
        pdf_bytes = await baixar_fatura(
            cpf_cnpj=req.cpf_cnpj,
            senha=req.senha,
            competencia=req.competencia,
        )
    except CopelAuthError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"erro": "Credenciais Copel inválidas.", "detalhe": str(e)},
        )
    except CopelFaturaNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"erro": "Fatura não encontrada.", "detalhe": str(e)},
        )
    except CopelScraperError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"erro": "Erro no portal Copel.", "detalhe": str(e)},
        )

    filename = f"copel_fatura_{req.competencia or 'recente'}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
