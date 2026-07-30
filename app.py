"""
ANALISADOR DE LINKEDIN - v1.1.0
Backend FastAPI + OpenAI
"""

import hmac as _hmac
import os
import json
import logging
import tempfile
import zipfile
import io
import csv
import uuid
import base64
import hashlib
import secrets
import time
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Any

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Header
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import httpx

_APP_DIR = Path(__file__).resolve().parent


def _load_app_env_files() -> None:
    """Carrega .env da raiz do repositório e, em seguida, de Analisador/ (override)."""
    load_dotenv(_APP_DIR.parent / ".env", override=False)
    load_dotenv(_APP_DIR / ".env", override=True)


_load_app_env_files()

import openai

from supabase_client import supabase_configured
import supabase_store

logger = logging.getLogger("analisadorcv")


def _is_vercel_runtime() -> bool:
    """Na Vercel o filesystem do runtime é só leitura exceto o diretório temporário."""
    return bool(os.getenv("VERCEL"))


def _app_env() -> str:
    explicit = os.getenv("APP_ENV", "").strip().lower()
    if explicit:
        return explicit
    return "production" if _is_vercel_runtime() else "development"


def _is_non_production_env() -> bool:
    return _app_env() not in ("production", "prod")


def _data_root() -> Path:
    if _is_vercel_runtime():
        return Path(tempfile.gettempdir()) / "analisadorcv"
    return Path(".")


_DATA_ROOT = _data_root()
if _is_vercel_runtime():
    _DATA_ROOT.mkdir(parents=True, exist_ok=True)

HISTORICO_DIR = _DATA_ROOT / "Historico"
USERS_DIR = _DATA_ROOT / "json"
HISTORICO_DIR.mkdir(parents=True, exist_ok=True)
USERS_DIR.mkdir(parents=True, exist_ok=True)

USERS_FILE = USERS_DIR / "users.json"
if not USERS_FILE.exists():
    USERS_FILE.write_text("[]", encoding="utf-8")
ARTIGOS_FEEDBACK_FILE = USERS_DIR / "artigos_feedback.json"
if not ARTIGOS_FEEDBACK_FILE.exists():
    ARTIGOS_FEEDBACK_FILE.write_text("[]", encoding="utf-8")
SUGESTOES_FILE = USERS_DIR / "sugestoes_funcionalidades.json"
if not SUGESTOES_FILE.exists():
    SUGESTOES_FILE.write_text("[]", encoding="utf-8")

_JSON_LOG_REL = USERS_DIR / "analisadorcv.log"


def _ensure_json_file_log_handler() -> Path:
    """Escreve logs de persistência/Supabase em json/analisadorcv.log (ou sob /tmp na Vercel)."""
    USERS_DIR.mkdir(parents=True, exist_ok=True)
    path = _JSON_LOG_REL.resolve()
    for h in logger.handlers:
        if isinstance(h, logging.FileHandler):
            try:
                if Path(h.baseFilename).resolve() == path:
                    return _JSON_LOG_REL
            except Exception:
                continue
    fh = logging.FileHandler(_JSON_LOG_REL, encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(fh)
    return _JSON_LOG_REL


APP_VERSION = "1.1.0"

app = FastAPI(title="Analisador de LinkedIn", version=APP_VERSION)


@app.on_event("startup")
async def _log_persistencia_startup() -> None:
    """Ajuda a diagnosticar se a app está a usar Supabase ou ficheiros JSON locais."""
    from urllib.parse import urlparse

    log_file = _ensure_json_file_log_handler()
    logger.info("Ambiente: %s", _app_env())
    if _env_admin_enabled():
        logger.warning(
            "Admin de teste via .env ativo (somente fora de produção). "
            "Em produção, use conta com role=admin no Supabase."
        )
    logger.info("Ficheiro de log: %s", log_file.resolve())

    url_raw = (os.getenv("SUPABASE_URL") or "").strip()
    key_ok = bool((os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "").strip())
    url_ok = bool(url_raw)
    host = ""
    if url_ok:
        try:
            host = urlparse(url_raw).netloc or url_raw[:48]
        except Exception:
            host = "(URL inválida)"
    if supabase_configured():
        logger.info(
            "Persistência: Supabase (host=%s). Utilizadores, histórico e feedback vêm da base.",
            host or "?",
        )
    else:
        logger.warning(
            "Persistência: JSON local — utilizadores=%s histórico=%s. "
            "Supabase inativo: SUPABASE_URL=%s SUPABASE_SERVICE_ROLE_KEY=%s. "
            "Confirme o .env no diretório de trabalho ao iniciar o uvicorn.",
            USERS_FILE.resolve(),
            HISTORICO_DIR.resolve(),
            "definida" if url_ok else "ausente",
            "definida" if key_ok else "ausente",
        )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path("static")
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

ADMIN_USERNAME = "admin"


def _env_admin_credentials() -> Optional[tuple[str, str]]:
    """Login/senha de admin via .env — apenas fora de produção."""
    if not _is_non_production_env():
        return None
    login = _norm_email(os.getenv("ADMIN_EMAIL", ""))
    password = os.getenv("ADMIN_PASSWORD", "").strip()
    if not login or not password:
        return None
    return login, password


def _env_admin_enabled() -> bool:
    return _env_admin_credentials() is not None


def _is_env_admin_login(login: str, password: str) -> bool:
    creds = _env_admin_credentials()
    if not creds:
        return False
    expected_login, expected_password = creds
    if _norm_email(login) != expected_login:
        return False
    return _hmac.compare_digest(password, expected_password)


def _is_reserved_env_admin_login(login: str) -> bool:
    creds = _env_admin_credentials()
    if not creds:
        return False
    return _norm_email(login) == creds[0]

# JWT stateless — não precisa de estado em memória (funciona em serverless)
_JWT_RAW_SECRET = os.getenv("JWT_SECRET", "").strip()
if not _JWT_RAW_SECRET:
    # Se não definido, gera por processo — tokens válidos apenas até restart.
    # Em produção DEVE definir JWT_SECRET nas variáveis de ambiente.
    _JWT_RAW_SECRET = secrets.token_hex(32)
    logging.getLogger("analisadorcv").warning(
        "JWT_SECRET não definido. Tokens expiram ao reiniciar o servidor. "
        "Defina JWT_SECRET nas variáveis de ambiente para persistência."
    )
JWT_TTL_SECONDS = 60 * 60 * 12  # 12 h


def _jwt_encode(payload: dict[str, Any]) -> str:
    header = _b64u(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    body = _b64u(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64u(_hmac.new(_JWT_RAW_SECRET.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest())
    return f"{header}.{body}.{sig}"


def _jwt_decode(token: str) -> Optional[dict[str, Any]]:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header, body, sig = parts
        expected = _b64u(_hmac.new(_JWT_RAW_SECRET.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest())
        if not _hmac.compare_digest(sig, expected):
            return None
        padding = 4 - len(body) % 4
        padded = body + ("=" * (padding % 4))
        data = json.loads(base64.urlsafe_b64decode(padded).decode())
        if data.get("exp", 0) < _now_ts():
            return None
        return data
    except Exception:
        return None


def _now_ts() -> int:
    return int(datetime.now().timestamp())


def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _hash_password(password: str, salt: str) -> str:
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    return _b64u(dk)


def _load_users() -> list[dict[str, Any]]:
    try:
        raw = USERS_FILE.read_text(encoding="utf-8").strip() or "[]"
        data = json.loads(raw)
        if isinstance(data, list):
            return [u for u in data if isinstance(u, dict)]
    except Exception:
        pass
    return []


def _atomic_write_json(path: Path, payload: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _save_users(users: list[dict[str, Any]]) -> None:
    _atomic_write_json(USERS_FILE, users)


def _load_json_list(path: Path) -> list[dict[str, Any]]:
    try:
        raw = path.read_text(encoding="utf-8").strip() or "[]"
        data = json.loads(raw)
        if isinstance(data, list):
            return [it for it in data if isinstance(it, dict)]
    except Exception:
        pass
    return []


def _save_json_list(path: Path, items: list[dict[str, Any]]) -> None:
    _atomic_write_json(path, items)


def _norm_email(email: str) -> str:
    return str(email or "").strip().lower()


def _is_valid_email(email: str) -> bool:
    e = _norm_email(email)
    if not e or "@" not in e:
        return False
    local, _, domain = e.partition("@")
    return bool(local and domain and "." in domain)


def _find_user(users: list[dict[str, Any]], username: str) -> Optional[dict[str, Any]]:
    username_lc = username.strip().lower()
    for u in users:
        if str(u.get("username", "")).strip().lower() == username_lc:
            return u
    return None


def _find_user_by_email(users: list[dict[str, Any]], email: str) -> Optional[dict[str, Any]]:
    email_lc = _norm_email(email)
    for u in users:
        if _norm_email(str(u.get("email", ""))) == email_lc:
            return u
    return None


def _require_auth(authorization: Optional[str] = Header(default=None)) -> dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Não autenticado.")
    token = authorization.split(" ", 1)[1].strip()
    payload = _jwt_decode(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Sessão inválida ou expirada. Faça login novamente.")
    return payload


def _require_admin(session: dict[str, Any] = Depends(_require_auth)) -> dict[str, Any]:
    if session.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores.")
    return session


def _parse_iso_datetime(val: Any) -> Optional[datetime]:
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        return dt
    except Exception:
        return None


def _is_within_days(created_at: Any, days: int) -> bool:
    dt = _parse_iso_datetime(created_at)
    if not dt:
        return False
    return dt >= datetime.now() - timedelta(days=days)


def _admin_dashboard_local(days: int = 30) -> dict[str, Any]:
    users = _load_users()
    novos = sum(1 for u in users if _is_within_days(u.get("created_at"), days))
    counts: Counter[str] = Counter()
    total_analises = 0
    for arq in HISTORICO_DIR.glob("*.json"):
        try:
            data = json.loads(arq.read_text(encoding="utf-8"))
            meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
            u = str(meta.get("usuario", "")).strip().lower()
            if not u:
                continue
            counts[u] += 1
            total_analises += 1
        except Exception:
            continue
    por_usuario = [{"usuario": k, "analises": v} for k, v in sorted(counts.items(), key=lambda x: (-x[1], x[0]))]
    return {
        "periodo_dias_novos_usuarios": days,
        "novos_usuarios": novos,
        "total_usuarios": len(users),
        "total_analises": total_analises,
        "analises_por_usuario": por_usuario,
    }


async def _admin_dashboard_supabase(days: int = 30) -> dict[str, Any]:
    user_rows = await supabase_store.db_users_list()
    novos = sum(1 for u in user_rows if _is_within_days(u.get("created_at"), days))
    hist_usuarios = await supabase_store.db_historico_usuarios_for_stats()
    total_analises = len(hist_usuarios)
    c = Counter(hist_usuarios)
    por_usuario = [{"usuario": k, "analises": v} for k, v in sorted(c.items(), key=lambda x: (-x[1], x[0]))]
    return {
        "periodo_dias_novos_usuarios": days,
        "novos_usuarios": novos,
        "total_usuarios": len(user_rows),
        "total_analises": total_analises,
        "analises_por_usuario": por_usuario,
    }


@app.post("/auth/login")
async def login(payload: dict):
    login_id = _norm_email(str(payload.get("email", "")))
    password = str(payload.get("password", "")).strip()
    if not login_id or not password:
        raise HTTPException(status_code=400, detail="Informe e-mail e senha.")

    is_env_admin = _is_env_admin_login(login_id, password)
    if not is_env_admin and not _is_valid_email(login_id):
        raise HTTPException(status_code=400, detail="Informe um e-mail válido.")

    session_username = ADMIN_USERNAME
    role = "admin" if is_env_admin else "user"

    if not is_env_admin:
        if supabase_configured():
            u = await supabase_store.db_users_find_by_email(login_id)
        else:
            users = _load_users()
            u = _find_user_by_email(users, login_id)
        if not u:
            raise HTTPException(status_code=401, detail="E-mail ou senha inválidos.")
        salt = str(u.get("salt", ""))
        expected = str(u.get("password_hash", ""))
        session_username = str(u.get("username", "")).strip().lower()
        role = str(u.get("role", "user"))
        if not salt or not expected:
            raise HTTPException(status_code=401, detail="Conta inválida. Contate o administrador.")
        if _hash_password(password, salt) != expected:
            raise HTTPException(status_code=401, detail="E-mail ou senha inválidos.")

    session_email = login_id if _is_valid_email(login_id) else f"{login_id}@local.test"
    now = _now_ts()
    token = _jwt_encode({
        "username": session_username,
        "email": session_email,
        "role": role,
        "iat": now,
        "exp": now + JWT_TTL_SECONDS,
    })
    return {"token": token, "username": session_username, "email": session_email, "role": role, "is_admin": role == "admin"}


@app.post("/auth/register")
async def register(payload: dict):
    username = str(payload.get("username", "")).strip()
    email = _norm_email(str(payload.get("email", "")))
    password = str(payload.get("password", "")).strip()
    if not username or not email or not password:
        raise HTTPException(status_code=400, detail="Informe usuário, e-mail e senha.")
    if len(username) < 3:
        raise HTTPException(status_code=400, detail="O usuário deve ter no mínimo 3 caracteres.")
    if not _is_valid_email(email):
        raise HTTPException(status_code=400, detail="Informe um e-mail válido.")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="A senha deve ter no mínimo 6 caracteres.")
    if username.lower() == ADMIN_USERNAME.lower():
        raise HTTPException(status_code=400, detail="Nome de usuário reservado.")
    if _is_reserved_env_admin_login(email):
        raise HTTPException(status_code=400, detail="E-mail reservado.")

    if supabase_configured():
        if await supabase_store.db_users_find_by_username(username):
            raise HTTPException(status_code=409, detail="Usuário já existe.")
        if await supabase_store.db_users_find_by_email(email):
            raise HTTPException(status_code=409, detail="E-mail já cadastrado.")
        salt = _b64u(secrets.token_bytes(16))
        try:
            await supabase_store.db_users_insert(username, email, salt, _hash_password(password, salt))
        except RuntimeError as e:
            msg = str(e).lower()
            if "duplicate" in msg or "unique" in msg or "23505" in msg:
                raise HTTPException(status_code=409, detail="Usuário ou e-mail já cadastrado.")
            raise HTTPException(status_code=500, detail=f"Erro ao cadastrar: {e}")
        return {"ok": True}

    users = _load_users()
    if _find_user(users, username):
        raise HTTPException(status_code=409, detail="Usuário já existe.")
    if _find_user_by_email(users, email):
        raise HTTPException(status_code=409, detail="E-mail já cadastrado.")
    salt = _b64u(secrets.token_bytes(16))
    now = datetime.now().isoformat()
    users.append({
        "username": username.strip().lower(),
        "email": email,
        "salt": salt,
        "password_hash": _hash_password(password, salt),
        "created_at": now,
        "updated_at": now,
    })
    _save_users(users)
    return {"ok": True}


@app.get("/auth/me")
async def me(session: dict[str, Any] = Depends(_require_auth)):
    role = session.get("role", "user")
    return {"username": session.get("username"), "email": session.get("email"), "role": role, "is_admin": role == "admin"}


@app.post("/auth/logout")
async def logout(_session: dict[str, Any] = Depends(_require_auth)):
    # JWT é stateless — o token expira pelo campo exp; logout é feito pelo cliente.
    return {"ok": True}


@app.get("/users")
async def list_users(_: dict[str, Any] = Depends(_require_admin)):
    if supabase_configured():
        data = await supabase_store.db_users_list()
    else:
        users = _load_users()
        data = [{
            "username": str(u.get("username", "")),
            "email": _norm_email(str(u.get("email", ""))),
            "role": str(u.get("role", "user")),
            "created_at": u.get("created_at"),
            "updated_at": u.get("updated_at"),
        } for u in users]
    data.sort(key=lambda x: x["username"].lower())
    return JSONResponse(content=data)


@app.post("/users")
async def create_user(payload: dict, _: dict[str, Any] = Depends(_require_admin)):
    username = str(payload.get("username", "")).strip()
    email = _norm_email(str(payload.get("email", "")))
    password = str(payload.get("password", "")).strip()
    role = str(payload.get("role", "user"))
    if role not in ("admin", "user"):
        role = "user"
    if not username:
        raise HTTPException(status_code=400, detail="Informe o nome do usuário.")
    if not _is_valid_email(email):
        raise HTTPException(status_code=400, detail="Informe um e-mail válido.")
    if username.lower() == ADMIN_USERNAME.lower():
        raise HTTPException(status_code=400, detail="Nome reservado.")
    if _is_reserved_env_admin_login(email):
        raise HTTPException(status_code=400, detail="E-mail reservado.")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="A senha deve ter no mínimo 6 caracteres.")

    if supabase_configured():
        if await supabase_store.db_users_find_by_username(username):
            raise HTTPException(status_code=409, detail="Usuário já existe.")
        if await supabase_store.db_users_find_by_email(email):
            raise HTTPException(status_code=409, detail="E-mail já cadastrado.")
        salt = _b64u(secrets.token_bytes(16))
        try:
            await supabase_store.db_users_insert(username, email, salt, _hash_password(password, salt), role)
        except RuntimeError as e:
            msg = str(e).lower()
            if "duplicate" in msg or "unique" in msg or "23505" in msg:
                raise HTTPException(status_code=409, detail="Usuário ou e-mail já cadastrado.")
            raise HTTPException(status_code=500, detail=f"Erro ao criar usuário: {e}")
        return {"ok": True}

    users = _load_users()
    if _find_user(users, username):
        raise HTTPException(status_code=409, detail="Usuário já existe.")
    if _find_user_by_email(users, email):
        raise HTTPException(status_code=409, detail="E-mail já cadastrado.")

    salt = _b64u(secrets.token_bytes(16))
    now = datetime.now().isoformat()
    users.append({
        "username": username.strip().lower(),
        "email": email,
        "role": role,
        "salt": salt,
        "password_hash": _hash_password(password, salt),
        "created_at": now,
        "updated_at": now,
    })
    _save_users(users)
    return {"ok": True}


@app.put("/users/{username}")
async def update_user(username: str, payload: dict, _: dict[str, Any] = Depends(_require_admin)):
    new_username = str(payload.get("new_username", "")).strip()
    new_email = _norm_email(str(payload.get("new_email", "")))
    new_role_raw = str(payload.get("role", "")).strip()
    new_role = new_role_raw if new_role_raw in ("admin", "user") else None
    password = str(payload.get("password", "")).strip()

    if supabase_configured():
        u = await supabase_store.db_users_find_by_username(username)
        if not u:
            raise HTTPException(status_code=404, detail="Usuário não encontrado.")
        changed = False
        new_salt = None
        new_hash = None
        if new_username:
            if new_username.lower() == ADMIN_USERNAME.lower():
                raise HTTPException(status_code=400, detail="Nome reservado.")
            if await supabase_store.db_users_find_by_username(new_username) and new_username.strip().lower() != str(u.get("username", "")).strip().lower():
                raise HTTPException(status_code=409, detail="Já existe um usuário com esse nome.")
            changed = True
        if new_email:
            if not _is_valid_email(new_email):
                raise HTTPException(status_code=400, detail="Informe um e-mail válido.")
            if _is_reserved_env_admin_login(new_email):
                raise HTTPException(status_code=400, detail="E-mail reservado.")
            found_email = await supabase_store.db_users_find_by_email(new_email)
            if found_email and str(found_email.get("username", "")).strip().lower() != str(u.get("username", "")).strip().lower():
                raise HTTPException(status_code=409, detail="Já existe um usuário com esse e-mail.")
            changed = True
        if new_role:
            changed = True
        if password:
            if len(password) < 6:
                raise HTTPException(status_code=400, detail="A senha deve ter no mínimo 6 caracteres.")
            new_salt = _b64u(secrets.token_bytes(16))
            new_hash = _hash_password(password, new_salt)
            changed = True
        if not changed:
            raise HTTPException(status_code=400, detail="Nada para atualizar.")
        ok = await supabase_store.db_users_update(
            username,
            new_username.strip().lower() if new_username else None,
            new_email if new_email else None,
            new_hash,
            new_salt,
            new_role,
        )
        if not ok:
            raise HTTPException(status_code=404, detail="Usuário não encontrado.")
        return {"ok": True}

    users = _load_users()
    u = _find_user(users, username)
    if not u:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")

    changed = False
    if new_username:
        if new_username.lower() == ADMIN_USERNAME.lower():
            raise HTTPException(status_code=400, detail="Nome reservado.")
        if _find_user(users, new_username) and new_username.strip().lower() != str(u.get("username", "")).strip().lower():
            raise HTTPException(status_code=409, detail="Já existe um usuário com esse nome.")
        u["username"] = new_username.strip().lower()
        changed = True
    if new_email:
        if not _is_valid_email(new_email):
            raise HTTPException(status_code=400, detail="Informe um e-mail válido.")
        if _is_reserved_env_admin_login(new_email):
            raise HTTPException(status_code=400, detail="E-mail reservado.")
        found_email = _find_user_by_email(users, new_email)
        if found_email and str(found_email.get("username", "")).strip().lower() != str(u.get("username", "")).strip().lower():
            raise HTTPException(status_code=409, detail="Já existe um usuário com esse e-mail.")
        u["email"] = new_email
        changed = True
    if new_role:
        u["role"] = new_role
        changed = True
    if password:
        if len(password) < 6:
            raise HTTPException(status_code=400, detail="A senha deve ter no mínimo 6 caracteres.")
        salt = _b64u(secrets.token_bytes(16))
        u["salt"] = salt
        u["password_hash"] = _hash_password(password, salt)
        changed = True

    if not changed:
        raise HTTPException(status_code=400, detail="Nada para atualizar.")

    u["updated_at"] = datetime.now().isoformat()
    _save_users(users)
    return {"ok": True}


@app.delete("/users/{username}")
async def delete_user(username: str, _: dict[str, Any] = Depends(_require_admin)):
    if supabase_configured():
        ok = await supabase_store.db_users_delete(username)
        if not ok:
            raise HTTPException(status_code=404, detail="Usuário não encontrado.")
        return {"ok": True}

    users = _load_users()
    before = len(users)
    users = [u for u in users if str(u.get("username", "")).strip().lower() != username.strip().lower()]
    if len(users) == before:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    _save_users(users)
    return {"ok": True}

# ─────────────────────────────────────────────
# EXTRAÇÃO DO ZIP LINKEDIN
# ─────────────────────────────────────────────

def extrair_zip_linkedin(zip_bytes: bytes) -> dict:
    dados = {}
    arquivos_alvo = {
        "Profile.csv": "profile",
        "Positions.csv": "positions",
        "Skills.csv": "skills",
        "Education.csv": "education",
        "Certifications.csv": "certifications",
        "Recommendations_Received.csv": "recommendations",
        "Learning.csv": "learning",
        "Rich_Media.csv": "rich_media",
    }

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        for nome_arquivo in z.namelist():
            basename = Path(nome_arquivo).name
            if basename in arquivos_alvo:
                chave = arquivos_alvo[basename]
                with z.open(nome_arquivo) as f:
                    conteudo = f.read().decode("utf-8", errors="ignore")
                    reader = csv.DictReader(io.StringIO(conteudo))
                    dados[chave] = list(reader)

    return dados


def formatar_dados_para_prompt(dados: dict) -> str:
    secoes = []

    if "profile" in dados and dados["profile"]:
        p = dados["profile"][0]
        secoes.append(f"""## PERFIL
Nome: {p.get('First Name', '')} {p.get('Last Name', '')}
Headline: {p.get('Headline', '')}
Localização: {p.get('Geo Location', '')}
Resumo (About): {p.get('Summary', '')}
""")

    if "positions" in dados and dados["positions"]:
        linhas = ["## EXPERIÊNCIAS PROFISSIONAIS"]
        for pos in dados["positions"][:10]:
            linhas.append(
                f"- {pos.get('Title', '')} @ {pos.get('Company Name', '')} "
                f"({pos.get('Started On', '')} - {pos.get('Finished On', 'Atual')}): "
                f"{pos.get('Description', '')[:300]}"
            )
        secoes.append("\n".join(linhas))

    if "skills" in dados and dados["skills"]:
        skills_list = [s.get("Name", "") for s in dados["skills"][:30] if s.get("Name")]
        secoes.append(f"## HABILIDADES\n{', '.join(skills_list)}")

    if "education" in dados and dados["education"]:
        linhas = ["## FORMAÇÃO ACADÊMICA"]
        for edu in dados["education"][:5]:
            linhas.append(
                f"- {edu.get('Degree Name', '')} em {edu.get('Field Of Study', '')} "
                f"@ {edu.get('School Name', '')} ({edu.get('Start Date', '')} - {edu.get('End Date', '')})"
            )
        secoes.append("\n".join(linhas))

    if "certifications" in dados and dados["certifications"]:
        certs = [c.get("Name", "") for c in dados["certifications"][:10] if c.get("Name")]
        secoes.append(f"## CERTIFICAÇÕES\n{', '.join(certs)}")

    if "recommendations" in dados and dados["recommendations"]:
        linhas = ["## RECOMENDAÇÕES RECEBIDAS"]
        for rec in dados["recommendations"][:3]:
            linhas.append(f'- De {rec.get("First Name", "")} {rec.get("Last Name", "")}: {rec.get("Text", "")[:200]}')
        secoes.append("\n".join(linhas))

    return "\n\n".join(secoes) if secoes else "Nenhum dado extraído do ZIP."


# ─────────────────────────────────────────────
# PROMPT OPENAI
# ─────────────────────────────────────────────

SYSTEM_PROMPT = """Você é um Consultor Executivo de Carreira e Especialista em Personal Branding para LinkedIn.
Sua análise é direta, estratégica e de alto valor. Tom executivo, prático e sem enrolação.

REGRAS ABSOLUTAS:
- NÃO avaliar idade, foto, gênero, raça, religião ou dados sensíveis
- Avaliar APENAS: conteúdo profissional, clareza de posicionamento, autoridade, palavras-chave, atratividade para recrutadores, consistência de carreira, força comercial, senioridade percebida

Retorne EXCLUSIVAMENTE um JSON válido com esta estrutura exata:
{
  "score": <número 0-100>,
  "veredito": "<frase executiva curta sobre o perfil>",
  "resumo_executivo": "<parágrafo executivo de 3-4 linhas>",
  "diagnostico": "<análise detalhada dos pontos críticos em 4-5 linhas>",
  "acoes_prioritarias": ["<ação 1>", "<ação 2>", "<ação 3>"],
  "pontos_fortes": ["<forte 1>", "<forte 2>", "<forte 3>", "<forte 4>"],
  "riscos": ["<risco 1>", "<risco 2>", "<risco 3>"],
  "palavras_chave": ["<kw1>", "<kw2>", "<kw3>", "<kw4>", "<kw5>", "<kw6>", "<kw7>", "<kw8>"],
  "headline_sugerida": "<headline otimizada para LinkedIn>",
  "sobre_sugerido": "<texto completo para seção Sobre, 3 parágrafos executivos>",
  "checklist": [
    {"item": "<item 1>", "ok": true},
    {"item": "<item 2>", "ok": false},
    {"item": "<item 3>", "ok": true},
    {"item": "<item 4>", "ok": false},
    {"item": "<item 5>", "ok": true},
    {"item": "<item 6>", "ok": false},
    {"item": "<item 7>", "ok": true},
    {"item": "<item 8>", "ok": false}
  ],
  "artigos_recomendados": [
    {"titulo": "<título artigo 1>", "link": "<url do artigo>", "descricao": "<por que ler>"},
    {"titulo": "<título artigo 2>", "link": "<url do artigo>", "descricao": "<por que ler>"},
    {"titulo": "<título artigo 3>", "link": "<url do artigo>", "descricao": "<por que ler>"}
  ]
}"""


def construir_user_prompt(dados_perfil: str, especialidade: str, senioridade: str,
                           objetivo: str, cargo_alvo: str, contexto: str) -> str:
    return f"""Analise o perfil LinkedIn abaixo com precisão executiva.

CONTEXTO DO PROFISSIONAL:
- Especialidade: {especialidade}
- Senioridade: {senioridade}
- Objetivo profissional: {objetivo}
- Cargo alvo: {cargo_alvo or 'Não informado'}
- Contexto adicional: {contexto or 'Não informado'}

DADOS EXTRAÍDOS DO LINKEDIN:
{dados_perfil}

Gere a análise completa conforme estrutura JSON definida."""


# ─────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────

@app.get("/health")
async def health():
    """Liveness probe — confirma que o processo HTTP está ativo."""
    return {
        "status": "ok",
        "service": "analisador-linkedin",
        "version": APP_VERSION,
    }


@app.get("/ready")
async def ready():
    """Readiness probe — valida dependências críticas para operação normal."""
    checks: dict[str, str] = {}
    ok = True

    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    checks["openai_api_key"] = "ok" if openai_key else "missing"
    if not openai_key:
        ok = False

    jwt_secret = os.getenv("JWT_SECRET", "").strip()
    checks["jwt_secret"] = "ok" if jwt_secret else "ephemeral"

    if supabase_configured():
        supabase_url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
        service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    f"{supabase_url}/rest/v1/",
                    headers={"apikey": service_key},
                )
            if response.status_code >= 500:
                checks["supabase"] = f"http_{response.status_code}"
                ok = False
            else:
                checks["supabase"] = "ok"
        except httpx.RequestError:
            checks["supabase"] = "unreachable"
            ok = False
        checks["persistence"] = "supabase"
    else:
        checks["supabase"] = "not_configured"
        checks["persistence"] = "json_local"

    payload = {
        "status": "ready" if ok else "not_ready",
        "version": APP_VERSION,
        "checks": checks,
    }
    return JSONResponse(status_code=200 if ok else 503, content=payload)


@app.get("/", response_class=HTMLResponse)
async def landing():
    path = Path("landing.html")
    if path.exists():
        return HTMLResponse(content=path.read_text(encoding="utf-8"))
    raise HTTPException(status_code=404, detail="landing.html não encontrado")


@app.get("/app", response_class=HTMLResponse)
async def app_ui():
    html_path = Path("index.html")
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    raise HTTPException(status_code=404, detail="index.html não encontrado")


@app.post("/analisar")
async def analisar(
    session: dict[str, Any] = Depends(_require_auth),
    arquivo: UploadFile = File(...),
    arquivo_2: Optional[UploadFile] = File(None),
    especialidade: str = Form(...),
    senioridade: str = Form(...),
    objetivo: str = Form(...),
    cargo_alvo: str = Form(""),
    contexto: str = Form(""),
):
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="OPENAI_API_KEY não configurada. Verifique seu arquivo .env")

    arquivos = [arquivo] + ([arquivo_2] if arquivo_2 else [])
    dados: dict[str, list[dict[str, Any]]] = {}
    for arquivo_atual in arquivos:
        nome = (arquivo_atual.filename or "").lower()
        if not nome.endswith(".zip"):
            raise HTTPException(status_code=400, detail="Envie somente arquivos .zip exportados do LinkedIn.")

        zip_bytes = await arquivo_atual.read()
        if len(zip_bytes) == 0:
            raise HTTPException(status_code=400, detail=f"O arquivo {arquivo_atual.filename} está vazio.")

        try:
            dados_arquivo = extrair_zip_linkedin(zip_bytes)
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Erro ao ler o arquivo {arquivo_atual.filename}: {str(e)}",
            )
        for chave, registros in dados_arquivo.items():
            dados.setdefault(chave, []).extend(registros)

    dados_formatados = formatar_dados_para_prompt(dados)
    user_prompt = construir_user_prompt(dados_formatados, especialidade, senioridade, objetivo, cargo_alvo, contexto)

    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

    client = openai.OpenAI(api_key=api_key)
    response = None

    def _chat_create() -> Any:
        """Modelos recentes exigem max_completion_tokens na API; SDKs antigos só aceitam max_tokens."""
        base = dict(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            timeout=90.0,
        )
        try:
            return client.chat.completions.create(**base, max_completion_tokens=2000)
        except TypeError as e:
            if "max_completion_tokens" not in str(e):
                raise
            return client.chat.completions.create(**base, max_tokens=2000)

    for tentativa in range(3):
        try:
            response = _chat_create()
            break
        except openai.AuthenticationError:
            raise HTTPException(status_code=401, detail="OPENAI_API_KEY inválida. Verifique sua chave.")
        except openai.RateLimitError:
            raise HTTPException(status_code=429, detail="Limite de requisições OpenAI atingido. Tente em instantes.")
        except (openai.APIConnectionError, openai.APITimeoutError):
            if tentativa < 2:
                time.sleep(1.5 * (tentativa + 1))
                continue
            raise HTTPException(
                status_code=503,
                detail="Falha de conexão com a OpenAI após 3 tentativas. Verifique internet, firewall/proxy e tente novamente."
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Erro na OpenAI: {str(e)}")

    raw = response.choices[0].message.content.strip()

    # Limpar blocos markdown se existirem
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    try:
        resultado = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Resposta da IA inválida. Tente novamente.")

    resultado["meta"] = {
        "especialidade": especialidade,
        "senioridade": senioridade,
        "objetivo": objetivo,
        "cargo_alvo": cargo_alvo,
        "data": datetime.now().isoformat(),
        "modelo": model,
        "usuario": session.get("username"),
    }

    return JSONResponse(content=resultado)


@app.post("/salvar")
async def salvar(payload: dict, session: dict[str, Any] = Depends(_require_auth)):
    try:
        # Garante isolamento por usuário: o dono do histórico sempre é o usuário autenticado.
        if not isinstance(payload.get("meta"), dict):
            payload["meta"] = {}
        payload["meta"]["usuario"] = session.get("username")

        if supabase_configured():
            new_id = await supabase_store.db_historico_insert(str(session.get("username", "")), payload)
            return {"ok": True, "arquivo": new_id}

        uid = str(uuid.uuid4())[:8]
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = HISTORICO_DIR / f"analise_{ts}_{uid}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return {"ok": True, "arquivo": filename.name}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao salvar: {str(e)}")


@app.get("/historico")
async def listar_historico(session: dict[str, Any] = Depends(_require_auth)):
    current_user = str(session.get("username", "")).strip().lower()
    if supabase_configured():
        itens = await supabase_store.db_historico_list(current_user)
        return JSONResponse(content=itens)

    arquivos = sorted(HISTORICO_DIR.glob("*.json"), reverse=True)
    itens = []
    for arq in arquivos:
        try:
            data = json.loads(arq.read_text(encoding="utf-8"))
            meta = data.get("meta", {})
            owner = str(meta.get("usuario", "")).strip().lower()
            if owner != current_user:
                continue
            itens.append({
                "arquivo": arq.name,
                "data": meta.get("data", ""),
                "score": data.get("score", 0),
                "especialidade": meta.get("especialidade", ""),
                "senioridade": meta.get("senioridade", ""),
                "objetivo": meta.get("objetivo", ""),
                "veredito": data.get("veredito", ""),
                "resumo_executivo": data.get("resumo_executivo", ""),
            })
        except Exception:
            continue
    return JSONResponse(content=itens)


@app.get("/historico/{arquivo}")
async def detalhe_historico(arquivo: str, session: dict[str, Any] = Depends(_require_auth)):
    current_user = str(session.get("username", "")).strip().lower()
    if supabase_configured():
        data = await supabase_store.db_historico_get(arquivo, current_user)
        if not data:
            raise HTTPException(status_code=404, detail="Análise não encontrada.")
        return JSONResponse(content=data)

    path = HISTORICO_DIR / arquivo
    if not path.exists():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
    data = json.loads(path.read_text(encoding="utf-8"))
    owner = str(data.get("meta", {}).get("usuario", "")).strip().lower()
    if owner != current_user:
        raise HTTPException(status_code=403, detail="Você não tem permissão para acessar este histórico.")
    return JSONResponse(content=data)


@app.post("/artigos/feedback")
async def salvar_feedback_artigo(payload: dict, session: dict[str, Any] = Depends(_require_auth)):
    nome = str(payload.get("artigo_nome", "")).strip()
    link = str(payload.get("artigo_link", "")).strip()
    gostou = payload.get("gostou")
    analise_data = str(payload.get("analise_data", "")).strip()

    if not nome:
        raise HTTPException(status_code=400, detail="Informe o nome do artigo.")
    if gostou is None or not isinstance(gostou, bool):
        raise HTTPException(status_code=400, detail="Informe se gostou ou não do artigo.")

    if supabase_configured():
        updated, _ = await supabase_store.db_feedback_upsert(
            str(session.get("username", "")),
            analise_data,
            nome,
            link,
            gostou,
        )
        return {"ok": True, "updated": updated}

    itens = _load_json_list(ARTIGOS_FEEDBACK_FILE)
    registro = {
        "id": str(uuid.uuid4()),
        "usuario": session.get("username"),
        "analise_data": analise_data,
        "artigo_nome": nome,
        "artigo_link": link,
        "gostou": gostou,
        "criado_em": datetime.now().isoformat(),
    }

    updated = False
    for idx, item in enumerate(itens):
        same_user = str(item.get("usuario", "")).strip().lower() == str(session.get("username", "")).strip().lower()
        same_analysis = str(item.get("analise_data", "")).strip() == analise_data
        same_article = str(item.get("artigo_nome", "")).strip().lower() == nome.lower()
        if same_user and same_analysis and same_article:
            registro["id"] = str(item.get("id", registro["id"]))
            itens[idx] = registro
            updated = True
            break

    if not updated:
        itens.append(registro)

    _save_json_list(ARTIGOS_FEEDBACK_FILE, itens)
    return {"ok": True, "updated": updated}


@app.get("/artigos/feedback")
async def listar_feedback_artigos(analise_data: str = "", session: dict[str, Any] = Depends(_require_auth)):
    current_user = str(session.get("username", "")).strip().lower()
    analise_data = str(analise_data or "").strip()

    if supabase_configured():
        filtrados = await supabase_store.db_feedback_list(current_user, analise_data)
        return JSONResponse(content=filtrados)

    itens = _load_json_list(ARTIGOS_FEEDBACK_FILE)
    filtrados = []
    for item in itens:
        same_user = str(item.get("usuario", "")).strip().lower() == current_user
        if not same_user:
            continue
        if analise_data and str(item.get("analise_data", "")).strip() != analise_data:
            continue
        filtrados.append(item)
    return JSONResponse(content=filtrados)


@app.post("/sugestoes")
async def salvar_sugestao(payload: dict, session: dict[str, Any] = Depends(_require_auth)):
    texto = str(payload.get("sugestao", "")).strip()
    if len(texto) < 4:
        raise HTTPException(status_code=400, detail="Sugestão muito curta.")

    if supabase_configured():
        await supabase_store.db_sugestao_insert(str(session.get("username", "")), texto)
        return {"ok": True}

    itens = _load_json_list(SUGESTOES_FILE)
    itens.append({
        "id": str(uuid.uuid4()),
        "usuario": session.get("username"),
        "sugestao": texto,
        "criado_em": datetime.now().isoformat(),
    })
    _save_json_list(SUGESTOES_FILE, itens)
    return {"ok": True}


@app.get("/admin/dashboard")
async def admin_dashboard(_: dict[str, Any] = Depends(_require_admin)):
    if supabase_configured():
        data = await _admin_dashboard_supabase()
    else:
        data = _admin_dashboard_local()
    return JSONResponse(content=data)


@app.get("/admin/artigos/insights")
async def admin_artigos_insights(_: dict[str, Any] = Depends(_require_admin)):
    if supabase_configured():
        itens = await supabase_store.db_feedback_all()
    else:
        itens = _load_json_list(ARTIGOS_FEEDBACK_FILE)
    resumo: dict[str, dict[str, Any]] = {}

    total_feedbacks = 0
    total_gostou = 0
    total_nao_gostou = 0

    for item in itens:
        nome = str(item.get("artigo_nome", "")).strip()
        if not nome:
            continue
        link = str(item.get("artigo_link", "")).strip()
        gostou = bool(item.get("gostou", False))
        criado_em = str(item.get("criado_em", "")).strip()

        key = nome.lower()
        if key not in resumo:
            resumo[key] = {
                "artigo_nome": nome,
                "artigo_link": link,
                "total": 0,
                "gostou": 0,
                "nao_gostou": 0,
                "ultima_interacao": "",
            }

        ref = resumo[key]
        ref["total"] += 1
        if gostou:
            ref["gostou"] += 1
            total_gostou += 1
        else:
            ref["nao_gostou"] += 1
            total_nao_gostou += 1

        if link and not ref["artigo_link"]:
            ref["artigo_link"] = link
        if criado_em and (not ref["ultima_interacao"] or criado_em > ref["ultima_interacao"]):
            ref["ultima_interacao"] = criado_em

        total_feedbacks += 1

    artigos = []
    for item in resumo.values():
        total = int(item["total"])
        gostou = int(item["gostou"])
        nao_gostou = int(item["nao_gostou"])
        item["taxa_gostou"] = round((gostou / total) * 100, 2) if total else 0.0
        item["taxa_nao_gostou"] = round((nao_gostou / total) * 100, 2) if total else 0.0
        artigos.append(item)

    artigos.sort(key=lambda a: (-int(a["total"]), -float(a["taxa_gostou"]), str(a["artigo_nome"]).lower()))

    taxa_gostou_geral = round((total_gostou / total_feedbacks) * 100, 2) if total_feedbacks else 0.0
    taxa_nao_gostou_geral = round((total_nao_gostou / total_feedbacks) * 100, 2) if total_feedbacks else 0.0

    return JSONResponse(content={
        "resumo": {
            "total_feedbacks": total_feedbacks,
            "total_gostou": total_gostou,
            "total_nao_gostou": total_nao_gostou,
            "taxa_gostou_geral": taxa_gostou_geral,
            "taxa_nao_gostou_geral": taxa_nao_gostou_geral,
            "artigos_unicos": len(artigos),
        },
        "artigos": artigos,
    })


@app.get("/admin/sugestoes")
async def admin_listar_sugestoes(limit: int = 200, _: dict[str, Any] = Depends(_require_admin)):
    limit = max(1, min(limit, 500))
    if supabase_configured():
        itens = await supabase_store.db_sugestoes_all()
    else:
        itens = _load_json_list(SUGESTOES_FILE)

    itens.sort(key=lambda x: str(x.get("criado_em", "")), reverse=True)
    data = [{
        "id": str(item.get("id", "")),
        "usuario": str(item.get("usuario", "")),
        "sugestao": str(item.get("sugestao", "")),
        "criado_em": str(item.get("criado_em", "")),
    } for item in itens[:limit]]
    return JSONResponse(content={
        "total": len(itens),
        "itens": data,
    })
