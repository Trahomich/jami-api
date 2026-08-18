"""Telegram Bot API-compatible endpoints.

Routes under ``/bot{token}/<method>`` mirror the Telegram Bot API surface
(getMe, sendMessage, getUpdates, setWebhook, ...). Parameters are accepted as
JSON body, form fields or query params — like the original API. Responses use
the Telegram envelope: ``{"ok": true, "result": ...}`` /
``{"ok": false, "error_code": ..., "description": ...}``.

Admin endpoints under ``/api/bots`` manage bot tokens bound to Jami accounts.
"""

import asyncio
import time
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.botapi.service import BotApiError, BotAPIService
from app.botapi.store import BotStore
from app.config import Settings

router = APIRouter()
logger = structlog.get_logger()

store: BotStore | None = None
service: BotAPIService | None = None


def init_botapi(event_bus: Any) -> None:
    global store, service
    settings = Settings()
    store = BotStore(settings.db_path)
    service = BotAPIService(
        store, event_bus, files_dir=settings.files_dir
    )


def _ensure() -> tuple[BotStore, BotAPIService]:
    if store is None or service is None:
        raise RuntimeError("botapi not initialized")
    return store, service


# ------------------------------------------------------------------ helpers


def _ok(result: Any) -> dict[str, Any]:
    return {"ok": True, "result": result}


def _error_response(code: int, description: str) -> JSONResponse:
    return JSONResponse(
        {"ok": False, "error_code": code, "description": description},
        status_code=code,
    )


async def _parse_params(request: Request) -> tuple[dict[str, Any], dict[str, Any]]:
    """Merge query params, JSON body and form fields; collect uploads."""
    params: dict[str, Any] = dict(request.query_params)
    files: dict[str, StarletteUploadFile] = {}

    if request.method == "POST":
        content_type = request.headers.get("content-type", "")
        if content_type.startswith("application/json"):
            try:
                body = await request.json()
                if isinstance(body, dict):
                    params.update({k: v for k, v in body.items() if v is not None})
            except ValueError:
                pass
        elif content_type.startswith("multipart/form-data") or content_type.startswith(
            "application/x-www-form-urlencoded"
        ):
            form = await request.form()
            for key, value in form.multi_items():
                if isinstance(value, StarletteUploadFile):
                    files[key] = value
                else:
                    params[key] = value
    return params, files


def _require_int(params: dict[str, Any], name: str, default: int | None = None) -> int:
    raw = params.get(name)
    if raw is None or raw == "":
        if default is not None:
            return default
        raise BotApiError(400, f"Bad Request: parameter '{name}' is required")
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise BotApiError(400, f"Bad Request: parameter '{name}' must be an integer") from None


def _optional_int(params: dict[str, Any], name: str, default: int | None = None) -> int | None:
    raw = params.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise BotApiError(400, f"Bad Request: parameter '{name}' must be an integer") from None


def _require_str(params: dict[str, Any], name: str) -> str:
    raw = params.get(name)
    if raw is None or str(raw) == "":
        raise BotApiError(400, f"Bad Request: parameter '{name}' is required")
    return str(raw)


# ------------------------------------------------------------ admin: tokens


@router.post("/api/bots")
async def create_bot(request: Request) -> Any:
    st, svc = _ensure()
    params, _ = await _parse_params(request)
    account_id = str(params.get("account_id", "") or "").strip()
    name = str(params.get("name", "") or "").strip()

    if not account_id:
        return _error_response(400, "account_id is required")

    bot_uri = ""
    try:
        bot_uri = svc.get_bot_uri(account_id)
    except Exception:
        pass

    record = st.create_token(account_id, name=name, bot_uri=bot_uri)
    svc.ensure_subscription(account_id)
    logger.info("botapi_token_created", account_id=account_id, name=name)
    return record


@router.get("/api/bots")
async def list_bots() -> Any:
    st, _ = _ensure()
    return st.list_tokens()


@router.delete("/api/bots/{token}")
async def delete_bot(token: str) -> Any:
    st, _ = _ensure()
    record = st.get_token(token)
    if record is None:
        return _error_response(404, "token not found")
    st.delete_token(token)
    return {"status": "deleted"}


# ------------------------------------------------------------- bot methods


def _auth(token: str) -> str:
    st, _ = _ensure()
    record = st.get_token(token)
    if record is None:
        raise BotApiError(401, "Unauthorized")
    return record["account_id"]


async def _handle(request: Request, token: str, handler_name: str) -> Any:
    st, svc = _ensure()
    try:
        account_id = _auth(token)
        params, files = await _parse_params(request)
    except BotApiError as e:
        return _error_response(e.code, e.description)

    method: Callable[[BotStore, BotAPIService, str, dict, dict], Awaitable[Any]] = _METHODS[
        handler_name
    ]
    try:
        result = await method(st, svc, account_id, params, files)
        return _ok(result)
    except BotApiError as e:
        return _error_response(e.code, e.description)
    except Exception as e:
        logger.error("botapi_method_failed", method=handler_name, error=str(e))
        return _error_response(500, f"Internal Server Error: {e}")


# ---- method implementations (st=store, svc=service) ----


async def _m_get_me(st: BotStore, svc: BotAPIService, account_id: str, p: dict, f: dict) -> Any:
    return svc.get_me(account_id)


async def _m_send_message(
    st: BotStore, svc: BotAPIService, account_id: str, p: dict, f: dict
) -> Any:
    chat_id = _require_int(p, "chat_id")
    text = _require_str(p, "text")
    reply = _optional_int(p, "reply_to_message_id")
    if "parse_mode" in p:
        logger.debug("botapi_parse_mode_ignored", parse_mode=p["parse_mode"])
    return svc.send_message(account_id, chat_id, text, reply)


async def _m_get_updates(
    st: BotStore, svc: BotAPIService, account_id: str, p: dict, f: dict
) -> Any:
    offset = _optional_int(p, "offset", default=0) or 0
    timeout = min(_optional_int(p, "timeout", default=0) or 0, 50)
    limit = min(max(_optional_int(p, "limit", default=100) or 100, 1), 100)

    if offset > 0:
        st.delete_updates_below(account_id, offset)

    deadline = time.monotonic() + timeout
    while True:
        updates = st.get_updates(account_id, offset, limit)
        if updates or time.monotonic() >= deadline:
            return updates
        await asyncio.sleep(0.3)


async def _m_set_webhook(
    st: BotStore, svc: BotAPIService, account_id: str, p: dict, f: dict
) -> Any:
    url = _require_str(p, "url")
    if not url.startswith(("http://", "https://")):
        raise BotApiError(400, "Bad Request: invalid webhook URL")
    secret = str(p.get("secret_token", "") or "")
    st.set_webhook(account_id, url, secret)
    if p.get("drop_pending_updates") in ("true", "True", True, 1):
        st.delete_updates_below(account_id, 1 << 60)
    return True


async def _m_delete_webhook(
    st: BotStore, svc: BotAPIService, account_id: str, p: dict, f: dict
) -> Any:
    if p.get("drop_pending_updates") in ("true", "True", True, 1):
        st.delete_updates_below(account_id, 1 << 60)
    st.delete_webhook(account_id)
    return True


async def _m_get_webhook_info(
    st: BotStore, svc: BotAPIService, account_id: str, p: dict, f: dict
) -> Any:
    hook = st.get_webhook(account_id)
    if hook is None:
        return {"url": "", "has_custom_certificate": False, "pending_update_count": 0}
    return {
        "url": hook["url"],
        "has_custom_certificate": False,
        "pending_update_count": st.pending_update_count(account_id),
        "last_error_message": hook.get("last_error", ""),
    }


async def _m_get_chat(st: BotStore, svc: BotAPIService, account_id: str, p: dict, f: dict) -> Any:
    chat_id = _require_int(p, "chat_id")
    chat = st.get_chat(account_id, chat_id)
    if chat is None:
        raise BotApiError(400, "Bad Request: chat not found")
    return BotAPIService._chat_obj(chat)  # noqa: SLF001


async def _m_send_chat_action(
    st: BotStore, svc: BotAPIService, account_id: str, p: dict, f: dict
) -> Any:
    _require_int(p, "chat_id")
    _require_str(p, "action")
    return True


async def _m_send_document(
    st: BotStore, svc: BotAPIService, account_id: str, p: dict, f: dict
) -> Any:
    return await _send_file(st, account_id, p, f, svc, key="document")


async def _m_send_photo(
    st: BotStore, svc: BotAPIService, account_id: str, p: dict, f: dict
) -> Any:
    return await _send_file(st, account_id, p, f, svc, key="photo")


async def _send_file(
    st: BotStore, account_id: str, p: dict, f: dict, svc: BotAPIService, key: str
) -> Any:
    chat_id = _require_int(p, "chat_id")
    caption = str(p.get("caption", "") or "")
    settings = Settings()

    upload = f.get(key)
    if upload is not None:
        dest_dir = Path(settings.files_dir) / "uploads" / uuid.uuid4().hex
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / (upload.filename or "file")
        content = await upload.read()
        dest.write_bytes(content)
        return svc.send_document(account_id, chat_id, str(dest), dest.name, caption)

    # Otherwise a file_id of a previously sent file.
    file_id = _require_str(p, key)
    record = st.get_file(file_id)
    if record is None or record["local_path"] == "":
        raise BotApiError(400, f"Bad Request: invalid {key} file_id")
    return svc.send_document(
        account_id, chat_id, record["local_path"], record["file_name"], caption
    )


async def _m_get_file(st: BotStore, svc: BotAPIService, account_id: str, p: dict, f: dict) -> Any:
    file_id = _require_str(p, "file_id")
    return svc.get_file(account_id, file_id)


_METHODS = {
    "getMe": _m_get_me,
    "sendMessage": _m_send_message,
    "getUpdates": _m_get_updates,
    "setWebhook": _m_set_webhook,
    "deleteWebhook": _m_delete_webhook,
    "getWebhookInfo": _m_get_webhook_info,
    "getChat": _m_get_chat,
    "sendChatAction": _m_send_chat_action,
    "sendDocument": _m_send_document,
    "sendPhoto": _m_send_photo,
    "getFile": _m_get_file,
}


@router.api_route("/bot{token}/{method}", methods=["POST", "GET"])
async def bot_endpoint(request: Request, token: str, method: str) -> Any:
    if method not in _METHODS:
        return _error_response(404, f"Not Found: method {method} is not supported")
    return await _handle(request, token, method)


@router.get("/bot{token}/files/{file_id}/{file_name:path}")
async def bot_download_file(token: str, file_id: str, file_name: str) -> Any:
    st, _ = _ensure()
    try:
        account_id = _auth(token)
    except BotApiError as e:
        return _error_response(e.code, e.description)
    record = st.get_file(file_id)
    if record is None or record["bot_account"] != account_id or not record["local_path"]:
        return _error_response(404, "Not Found: file not found")
    path = Path(record["local_path"])
    if not path.exists():
        return _error_response(404, "Not Found: file not found on disk")
    return FileResponse(path, filename=record["file_name"] or file_name)
