import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import URL


def get_config():
    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(project_root / ".env")

    required = ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD", "JWT_SECRET_KEY")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise RuntimeError("Lipsesc setari in .env: " + ", ".join(missing))

    jwt_secret = os.environ["JWT_SECRET_KEY"]
    if len(jwt_secret.strip().encode("utf-8")) < 32:
        raise RuntimeError("JWT_SECRET_KEY trebuie sa aiba cel putin 32 de octeti si sa fie generata aleator.")
    cookie_secure = os.getenv("JWT_COOKIE_SECURE", "true").lower()
    if cookie_secure not in {"true", "false"}:
        raise RuntimeError("JWT_COOKIE_SECURE trebuie sa fie true sau false.")
    try:
        token_minutes = int(os.getenv("JWT_ACCESS_TOKEN_MINUTES", "15"))
    except ValueError:
        raise RuntimeError("JWT_ACCESS_TOKEN_MINUTES trebuie sa fie un numar intreg intre 1 si 60.") from None
    if not 1 <= token_minutes <= 60:
        raise RuntimeError("JWT_ACCESS_TOKEN_MINUTES trebuie sa fie intre 1 si 60.")
    behind_proxy = os.getenv("BEHIND_PROXY", "false").lower()
    if behind_proxy not in {"true", "false"}:
        raise RuntimeError("BEHIND_PROXY trebuie sa fie true sau false.")

    database_url = URL.create(
        drivername="postgresql+psycopg",
        username=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.environ["POSTGRES_DB"],
    )

    return {
        "BEHIND_PROXY": behind_proxy == "true",
        "ATTACHMENT_STORAGE_PATH": os.getenv("ATTACHMENT_STORAGE_PATH") or str(project_root / "instance" / "attachments"),
        "MAIL_TRANSPORT": os.getenv("MAIL_TRANSPORT", "LOCAL_MAILPIT"),
        "MAILPIT_SMTP_HOST": os.getenv("MAILPIT_SMTP_HOST", "127.0.0.1"),
        "MAILPIT_SMTP_PORT": os.getenv("MAILPIT_SMTP_PORT", "1025"),
        "SMTP_HOST": os.getenv("SMTP_HOST", ""),
        "SMTP_PORT": os.getenv("SMTP_PORT", "587"),
        "SMTP_SECURITY": os.getenv("SMTP_SECURITY", "STARTTLS"),
        "SMTP_USERNAME": os.getenv("SMTP_USERNAME", ""),
        "SMTP_PASSWORD": os.getenv("SMTP_PASSWORD", ""),
        "SMTP_FROM_EMAIL": os.getenv("SMTP_FROM_EMAIL", ""),
        "EMAIL_DAILY_TIME": os.getenv("EMAIL_DAILY_TIME", "08:00"),
        "EMAIL_RETRY_SECONDS": os.getenv("EMAIL_RETRY_SECONDS", "300"),
        "RATELIMIT_STORAGE_URI": "memory://",
        "RATELIMIT_HEADERS_ENABLED": True,
        "JWT_SECRET_KEY": jwt_secret,
        "JWT_ALGORITHM": "HS256",
        "JWT_DECODE_ALGORITHMS": ["HS256"],
        "JWT_ACCESS_TOKEN_EXPIRES": timedelta(minutes=token_minutes),
        "JWT_TOKEN_LOCATION": ["cookies"],
        "JWT_ACCESS_COOKIE_PATH": "/api",
        "JWT_COOKIE_SECURE": cookie_secure == "true",
        "JWT_COOKIE_SAMESITE": "Lax",
        "JWT_COOKIE_CSRF_PROTECT": True,
        "JWT_CSRF_IN_COOKIES": True,
        "JWT_ACCESS_CSRF_HEADER_NAME": "X-CSRF-TOKEN",
        "SQLALCHEMY_DATABASE_URI": database_url,
        "SQLALCHEMY_ENGINE_OPTIONS": {
            "pool_pre_ping": True,
            "connect_args": {"connect_timeout": 5},
        },
    }
