import os

SECRET_KEY: str = os.getenv("SECRET_KEY", "alluz-dev-insecure-key-mude-em-producao")
ALGORITHM: str = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./copel.db")
