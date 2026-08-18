"""Bot API service: converts Jami D-Bus events to Telegram-style updates.

Consumes messages from the EventBus for every account that has a bot token,
maps them to Telegram-shaped objects (Update/Message/Chat/User), persists them
and dispatches webhooks when configured.
"""

import asyncio
import time
import uuid
from pathlib import Path
from typing import Any, Callable

import httpx
import structlog

from app.botapi.store import BotStore
from app.services.event_bus import EventBus

logger = structlog.get_logger()


class BotApiError(Exception):
    """Error with Telegram Bot API semantics (HTTP code + description)."""

    def __init__(self, code: int, description: str) -> None:
        super().__init__(description)
        self.code = code
        self.description = description


class BotAPIService:
    def __init__(
        self,
        store: BotStore,
        event_bus: EventBus,
        client_factory: Callable[[], Any] | None = None,
        files_dir: str = "data/botapi-files",
    ) -> None:
        self._store = store
        self._event_bus = event_bus
        self._client_factory = client_factory
        self._files_dir = Path(files_dir)
        self._tasks: dict[str, asyncio.Task] = {}
        self._queues: dict[str, asyncio.Queue] = {}

    # ----------------------------------------------------------- lifecycle

    async def start(self) -> None:
        for account_id in self._store.accounts_with_tokens():
            self.ensure_subscription(account_id)
        logger.info("botapi_started", accounts=list(self._tasks))

    async def stop(self) -> None:
        for account_id, task in self._tasks.items():
            task.cancel()
            queue = self._queues.get(account_id)
            if queue is not None:
                self._event_bus.unsubscribe(account_id, queue)
        self._tasks.clear()
        self._queues.clear()

    def ensure_subscription(self, account_id: str) -> None:
        if account_id in self._tasks:
            return
        queue = self._event_bus.subscribe(account_id)
        self._queues[account_id] = queue
        self._tasks[account_id] = asyncio.create_task(
            self._consume(account_id, queue), name=f"botapi-consume-{account_id}"
        )
        logger.info("botapi_subscribed", account_id=account_id)

    def _client(self) -> Any:
        if self._client_factory is not None:
            return self._client_factory()
        from app.dbus_client import JamiDBusClient

        return JamiDBusClient.get_instance()

    # ------------------------------------------------------------ consumer

    async def _consume(self, account_id: str, queue: asyncio.Queue) -> None:
        while True:
            event: dict[str, Any] = await queue.get()
            try:
                await self.handle_event(account_id, event)
            except Exception as e:
                logger.error("botapi_event_failed", account_id=account_id, error=str(e))

    async def handle_event(self, bot_account: str, event: dict[str, Any]) -> None:
        if event.get("type") != "message":
            return

        if event.get("source") == "swarm":
            update = self._swarm_to_update(bot_account, event)
        else:
            update = self._direct_to_update(bot_account, event)
        if update is None:
            return

        update_id = self._store.insert_update(bot_account, update)
        logger.info(
            "botapi_update_stored",
            bot_account=bot_account,
            update_id=update_id,
            chat_id=update.get("message", {}).get("chat", {}).get("id"),
        )

        webhook = self._store.get_webhook(bot_account)
        if webhook:
            asyncio.create_task(self._dispatch_webhook(bot_account, update_id, update))

    def _swarm_to_update(self, bot_account: str, event: dict[str, Any]) -> dict[str, Any] | None:
        conv_id = event.get("conversation_id", "")
        msg = event.get("message", {})
        jami_msg_id = str(msg.get("id", ""))
        author = str(msg.get("author", ""))
        body = str(msg.get("body", ""))
        msg_type = str(msg.get("type", "text/plain"))

        # Skip our own echoes (also deduplicated by jami_msg_id in the store).
        token_uris = [
            t["bot_uri"] for t in self._store.list_tokens() if t["account_id"] == bot_account
        ]
        if author and author in token_uris:
            return None

        chat = self._store.get_or_create_chat(
            bot_account, "group", conv_id, title=conv_id[:8], conv_id=conv_id
        )
        user = self._store.get_or_create_user(bot_account, author)

        is_file = msg_type.startswith("application/data-transfer")
        file_id = ""
        if is_file:
            file_id = f"{conv_id}:{jami_msg_id}"
            file_name = body or "file"
            self._store.insert_file(file_id, bot_account, "", file_name, 0)

        message_id = self._store.insert_message(
            bot_account, chat["chat_id"], jami_msg_id, author, body, file_id
        )
        if message_id is None:
            return None

        ts = self._parse_timestamp(msg.get("timestamp", ""))
        message: dict[str, Any] = {
            "message_id": message_id,
            "from": self._user_obj(user),
            "chat": self._chat_obj(chat),
            "date": ts,
        }
        if is_file:
            message["document"] = {
                "file_id": file_id,
                "file_unique_id": file_id,
                "file_name": body or "file",
            }
        else:
            message["text"] = body

        return {"update_id": 0, "message": message}

    def _direct_to_update(self, bot_account: str, event: dict[str, Any]) -> dict[str, Any] | None:
        from_uri = str(event.get("from", ""))
        if not from_uri:
            return None
        payloads = event.get("payloads", {})
        body = ""
        if isinstance(payloads, dict):
            body = str(payloads.get("text/plain", next(iter(payloads.values()), "")))

        chat = self._store.get_or_create_chat(
            bot_account, "private", from_uri, peer_uri=from_uri
        )
        user = self._store.get_or_create_user(bot_account, from_uri)

        # Direct events carry no daemon message id: no cross-restart dedup.
        message_id = self._store.insert_message(
            bot_account, chat["chat_id"], "", from_uri, body, ""
        )
        message = {
            "message_id": message_id,
            "from": self._user_obj(user),
            "chat": self._chat_obj(chat),
            "date": int(time.time()),
            "text": body,
        }
        return {"update_id": 0, "message": message}

    @staticmethod
    def _parse_timestamp(raw: Any) -> int:
        try:
            value = int(str(raw))
            if value > 10_000_000_000:  # milliseconds
                value //= 1000
            return value if value > 0 else int(time.time())
        except (TypeError, ValueError):
            return int(time.time())

    @staticmethod
    def _user_obj(user: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": user["user_id"],
            "is_bot": False,
            "first_name": user.get("first_name") or str(user["uri"])[:8],
        }

    @staticmethod
    def _chat_obj(chat: dict[str, Any]) -> dict[str, Any]:
        if chat["type"] == "private":
            return {
                "id": chat["chat_id"],
                "type": "private",
                "first_name": chat.get("title") or chat.get("peer_uri", "")[:8],
            }
        return {
            "id": chat["chat_id"],
            "type": "group",
            "title": chat.get("title") or chat.get("conv_id", "")[:8],
        }

    # ------------------------------------------------------------ webhooks

    async def _dispatch_webhook(
        self, bot_account: str, update_id: int, payload: dict[str, Any]
    ) -> None:
        webhook = self._store.get_webhook(bot_account)
        if not webhook:
            return
        headers = {}
        if webhook.get("secret_token"):
            headers["X-Telegram-Bot-Api-Secret-Token"] = webhook["secret_token"]
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(webhook["url"], json=payload, headers=headers)
            if 200 <= resp.status_code < 300:
                self._store.delete_update(update_id)
                logger.info(
                    "botapi_webhook_delivered",
                    bot_account=bot_account,
                    code=resp.status_code,
                )
            else:
                self._store.set_webhook_error(bot_account, f"HTTP {resp.status_code}")
                logger.warning(
                    "botapi_webhook_failed", bot_account=bot_account, code=resp.status_code
                )
        except Exception as e:
            self._store.set_webhook_error(bot_account, str(e))
            logger.error("botapi_webhook_error", bot_account=bot_account, error=str(e))

    # ------------------------------------------------------------- actions

    def get_bot_uri(self, bot_account: str) -> str:
        try:
            volatile = self._client().get_volatile_account_details(bot_account)
            return volatile.get("Account.uri", "")
        except Exception:
            return ""

    def get_me(self, bot_account: str) -> dict[str, Any]:
        try:
            details = self._client().get_account_details(bot_account)
            alias = details.get("Account.alias") or bot_account[:8]
        except Exception:
            alias = bot_account[:8]
        from app.botapi.store import _derive_int

        return {
            "id": _derive_int(f"bot:{bot_account}"),
            "is_bot": True,
            "first_name": alias,
            "username": f"jami_{bot_account[:12]}",
        }

    def send_message(
        self, bot_account: str, chat_id: int, text: str, reply_to_message_id: int | None = None
    ) -> dict[str, Any]:
        chat = self._store.get_chat(bot_account, chat_id)
        if chat is None:
            raise BotApiError(400, "Bad Request: chat not found")

        parent = ""
        if reply_to_message_id:
            ref = self._store.get_message(bot_account, reply_to_message_id)
            if ref is None:
                raise BotApiError(400, "Bad Request: message to reply not found")
            parent = ref.get("jami_msg_id", "")

        client = self._client()
        jami_msg_id = ""
        if chat["conv_id"]:
            jami_msg_id = client.send_conversation_message(
                bot_account, chat["conv_id"], text, parent
            )
        else:
            jami_msg_id = client.send_text_message(
                bot_account, chat["peer_uri"], {"text/plain": text}
            )

        message_id = self._store.insert_message(
            bot_account, chat_id, str(jami_msg_id), "", text, ""
        )
        if message_id is None:
            # Echo already registered the message; fetch its id for the response.
            existing = self._store.get_message_by_jami_id(bot_account, str(jami_msg_id))
            message_id = existing["id"] if existing else 0

        return {
            "message_id": message_id,
            "chat": self._chat_obj(chat),
            "date": int(time.time()),
            "text": text,
        }

    def send_document(
        self,
        bot_account: str,
        chat_id: int,
        local_path: str,
        file_name: str,
        caption: str = "",
    ) -> dict[str, Any]:
        chat = self._store.get_chat(bot_account, chat_id)
        if chat is None:
            raise BotApiError(400, "Bad Request: chat not found")
        if not chat["conv_id"]:
            raise BotApiError(
                400, "Bad Request: file sending is only supported in swarm conversations"
            )

        file_id = uuid.uuid4().hex
        path = Path(local_path)
        size = path.stat().st_size if path.exists() else 0

        client = self._client()
        jami_msg_id = client.send_file(bot_account, chat["conv_id"], str(path))

        self._store.insert_file(file_id, bot_account, str(path), file_name, size)
        message_id = self._store.insert_message(
            bot_account, chat_id, str(jami_msg_id), "", caption or file_name, file_id
        )
        message: dict[str, Any] = {
            "message_id": message_id or 0,
            "chat": self._chat_obj(chat),
            "date": int(time.time()),
            "document": {
                "file_id": file_id,
                "file_unique_id": file_id,
                "file_name": file_name,
                "file_size": size,
            },
        }
        if caption:
            message["caption"] = caption
        return message

    def get_file(self, bot_account: str, file_id: str) -> dict[str, Any]:
        record = self._store.get_file(file_id)
        if record is None or record["bot_account"] != bot_account:
            raise BotApiError(400, "Bad Request: file not found")

        if not record["local_path"] and ":" in file_id:
            # Incoming transfer: trigger download into our files dir.
            conv_id, interaction = file_id.split(":", 1)
            self._files_dir.mkdir(parents=True, exist_ok=True)
            target = self._files_dir / f"{file_id.replace(':', '_')}_{record['file_name']}"
            try:
                client = self._client()
                client.download_file(bot_account, conv_id, interaction, str(target))
                size = target.stat().st_size if target.exists() else 0
                self._store.insert_file(
                    file_id, bot_account, str(target), record["file_name"], size
                )
                record = self._store.get_file(file_id) or record
            except Exception as e:
                raise BotApiError(400, f"Bad Request: file download failed: {e}") from e

        return {
            "file_id": file_id,
            "file_unique_id": file_id,
            "file_size": record.get("file_size", 0),
            "file_path": f"files/{file_id}/{record['file_name']}",
        }
