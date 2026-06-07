from pydantic import BaseModel, Field
from typing import Optional


class FaturaRequest(BaseModel):
    cpf_cnpj: str = Field(..., description="CPF (xxx.xxx.xxx-xx) ou CNPJ do titular")
    senha: str = Field(..., description="Senha da Agência Virtual Copel")
    competencia: Optional[str] = Field(
        None,
        description="Competência no formato YYYY-MM (ex: 2025-05). Se omitido, baixa a fatura mais recente.",
    )


class ErroResponse(BaseModel):
    erro: str
    detalhe: Optional[str] = None
