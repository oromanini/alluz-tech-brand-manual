from fastapi import FastAPI, HTTPException
from fastapi.responses import Response

from app.schemas import FaturaRequest, ErroResponse
from app.scraper import baixar_fatura, CopelAuthError, CopelFaturaNotFoundError, CopelScraperError

app = FastAPI(
    title="Alluz Copel Collector",
    description="Serviço de coleta automatizada de faturas Copel via portal AVA.",
    version="1.0.0",
)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post(
    "/faturas/download",
    responses={
        200: {"content": {"application/pdf": {}}, "description": "PDF da fatura"},
        401: {"model": ErroResponse, "description": "Credenciais inválidas"},
        404: {"model": ErroResponse, "description": "Fatura não encontrada"},
        502: {"model": ErroResponse, "description": "Falha ao acessar portal Copel"},
    },
)
async def download_fatura(req: FaturaRequest):
    """
    Faz login no portal AVA da Copel com as credenciais do cliente e retorna
    o PDF da fatura solicitada.
    """
    try:
        pdf_bytes = await baixar_fatura(
            cpf_cnpj=req.cpf_cnpj,
            senha=req.senha,
            competencia=req.competencia,
        )
    except CopelAuthError as e:
        raise HTTPException(status_code=401, detail={"erro": "Autenticação falhou", "detalhe": str(e)})
    except CopelFaturaNotFoundError as e:
        raise HTTPException(status_code=404, detail={"erro": "Fatura não encontrada", "detalhe": str(e)})
    except CopelScraperError as e:
        raise HTTPException(status_code=502, detail={"erro": "Erro no portal Copel", "detalhe": str(e)})

    filename = f"copel_fatura_{req.competencia or 'recente'}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
