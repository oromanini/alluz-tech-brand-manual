import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator, EmailStr


class RegistroRequest(BaseModel):
    email: EmailStr = Field(..., description="E-mail do usuário")
    password: str = Field(..., min_length=8, description="Senha com no mínimo 8 caracteres")

    model_config = {
        "json_schema_extra": {
            "examples": [{"email": "cliente@alluz.com.br", "password": "minhasenha123"}]
        }
    }


class LoginRequest(BaseModel):
    email: EmailStr = Field(..., description="E-mail cadastrado")
    password: str = Field(..., description="Senha")

    model_config = {
        "json_schema_extra": {
            "examples": [{"email": "cliente@alluz.com.br", "password": "minhasenha123"}]
        }
    }


class TokenResponse(BaseModel):
    access_token: str = Field(..., description="JWT para uso no header Authorization: Bearer <token>")
    token_type: str = Field(default="bearer", description="Tipo do token — sempre 'bearer'")


class UserResponse(BaseModel):
    id: int
    email: str
    created_at: datetime

    model_config = {"from_attributes": True}


class FaturaRequest(BaseModel):
    cpf_cnpj: str = Field(
        ...,
        description="CPF (xxx.xxx.xxx-xx) ou CNPJ do titular da conta Copel",
        examples=["123.456.789-00"],
    )
    senha: str = Field(..., description="Senha da Agência Virtual Copel (AVA)")
    competencia: Optional[str] = Field(
        None,
        description="Mês de referência no formato YYYY-MM. Omita para baixar a fatura mais recente.",
        examples=["2025-05"],
    )

    @field_validator("competencia")
    @classmethod
    def validar_competencia(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", v):
            raise ValueError("Formato inválido. Use YYYY-MM (ex: 2025-05).")
        return v

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"cpf_cnpj": "123.456.789-00", "senha": "suasenha", "competencia": "2025-05"}
            ]
        }
    }


class ErroResponse(BaseModel):
    erro: str = Field(..., description="Descrição do erro")
    detalhe: Optional[str] = Field(None, description="Informação adicional sobre o erro")
