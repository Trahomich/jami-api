"""SQLite-backed persistence for the Telegram-compatible Bot API layer.

Stores bot tokens, chat/user mappings (Jami URIs and conversation IDs to
numeric Telegram-style IDs), sent/received messages, pending updates and
webhook configuration.
"""

import hashlib
import json
import secrets
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any


def _derive_int(source: str, signed: bool = False) -> int:
    """Deterministically derive a positive int64-ish ID from a string key."""
    digest = hashlib.sha256(source.encode()).digest()
    value = int.from_bytes(digest[:7], "big")
    return -value if signed else value


class BotStore:
    def __init__(self, db_path: str) -> None:
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock, self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS tokens (
                    token TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    name TEXT NOT NULL DEFAULT '',
                    bot_uri TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_tokens_account ON tokens(account_id);

                CREATE TABLE IF NOT EXISTS chats (
                    bot_account TEXT NOT NULL,
                    chat_key TEXT NOT NULL,
                    chat_id INTEGER NOT NULL,
                    type TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    peer_uri TEXT NOT NULL DEFAULT '',
                    conv_id TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL,
                    PRIMARY KEY (bot_account, chat_key)
                );
                CREATE UNIQUE INDEX IF NOT EXISTS ux_chats_id ON chats(bot_account, chat_id);

                CREATE TABLE IF NOT EXISTS users (
                    bot_account TEXT NOT NULL,
                    uri TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    first_name TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL,
                    PRIMARY KEY (bot_account, uri)
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bot_account TEXT NOT NULL,
                    chat_id INTEGER NOT NULL,
                    jami_msg_id TEXT NOT NULL DEFAULT '',
                    author_uri TEXT NOT NULL DEFAULT '',
                    body TEXT NOT NULL DEFAULT '',
                    file_id TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS ux_messages_jami
                    ON messages(bot_account, jami_msg_id) WHERE jami_msg_id != '';

                CREATE TABLE IF NOT EXISTS updates (
                    update_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bot_account TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_updates_bot ON updates(bot_account, update_id);

                CREATE TABLE IF NOT EXISTS webhooks (
                    bot_account TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    secret_token TEXT NOT NULL DEFAULT '',
                    pending_update_count INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS files (
                    file_id TEXT PRIMARY KEY,
                    bot_account TEXT NOT NULL,
                    local_path TEXT NOT NULL DEFAULT '',
                    file_name TEXT NOT NULL DEFAULT '',
                    file_size INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL
                );
                """
            )

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ---------------------------------------------------------------- tokens

    def create_token(self, account_id: str, name: str = "", bot_uri: str = "") -> dict[str, Any]:
        token = f"{secrets.randbits(31)}:{secrets.token_hex(16)}"
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO tokens (token, account_id, name, bot_uri, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (token, account_id, name, bot_uri, int(time.time())),
            )
        return {"token": token, "account_id": account_id, "name": name, "bot_uri": bot_uri}

    def get_token(self, token: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM tokens WHERE token = ?", (token,)
            ).fetchone()
        return dict(row) if row else None

    def list_tokens(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM tokens ORDER BY created_at").fetchall()
        return [dict(r) for r in rows]

    def delete_token(self, token: str) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute("DELETE FROM tokens WHERE token = ?", (token,))
        return cur.rowcount > 0

    def accounts_with_tokens(self) -> list[str]:
        with self._lock:
            rows = self._conn.execute("SELECT DISTINCT account_id FROM tokens").fetchall()
        return [r["account_id"] for r in rows]

    # ----------------------------------------------------------------- chats

    def get_or_create_chat(
        self,
        bot_account: str,
        kind: str,
        key: str,
        title: str = "",
        peer_uri: str = "",
        conv_id: str = "",
    ) -> dict[str, Any]:
        chat_key = f"{kind}:{key}"
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM chats WHERE bot_account = ? AND chat_key = ?",
                (bot_account, chat_key),
            ).fetchone()
            if row is None:
                signed = kind == "group"
                chat_id = _derive_int(f"{bot_account}:{chat_key}", signed=signed)
                with self._conn:
                    self._conn.execute(
                        "INSERT INTO chats (bot_account, chat_key, chat_id, type, title,"
                        " peer_uri, conv_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            bot_account,
                            chat_key,
                            chat_id,
                            kind,
                            title,
                            peer_uri,
                            conv_id,
                            int(time.time()),
                        ),
                    )
                row = self._conn.execute(
                    "SELECT * FROM chats WHERE bot_account = ? AND chat_key = ?",
                    (bot_account, chat_key),
                ).fetchone()
        return dict(row)

    def get_chat(self, bot_account: str, chat_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM chats WHERE bot_account = ? AND chat_id = ?",
                (bot_account, chat_id),
            ).fetchone()
        return dict(row) if row else None

    def list_chats(self, bot_account: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM chats WHERE bot_account = ? ORDER BY created_at", (bot_account,)
            ).fetchall()
        return [dict(r) for r in rows]

    # ----------------------------------------------------------------- users

    def get_or_create_user(self, bot_account: str, uri: str, first_name: str = "") -> dict[
        str, Any
    ]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM users WHERE bot_account = ? AND uri = ?", (bot_account, uri)
            ).fetchone()
            if row is None:
                user_id = _derive_int(f"{bot_account}:user:{uri}")
                with self._conn:
                    self._conn.execute(
                        "INSERT INTO users (bot_account, uri, user_id, first_name, created_at)"
                        " VALUES (?, ?, ?, ?, ?)",
                        (bot_account, uri, user_id, first_name or uri[:8], int(time.time())),
                    )
                row = self._conn.execute(
                    "SELECT * FROM users WHERE bot_account = ? AND uri = ?", (bot_account, uri)
                ).fetchone()
        return dict(row)

    # -------------------------------------------------------------- messages

    def insert_message(
        self,
        bot_account: str,
        chat_id: int,
        jami_msg_id: str = "",
        author_uri: str = "",
        body: str = "",
        file_id: str = "",
    ) -> int | None:
        """Insert a message row, returns None when deduplicated by jami_msg_id."""
        try:
            with self._lock, self._conn:
                cur = self._conn.execute(
                    "INSERT INTO messages (bot_account, chat_id, jami_msg_id, author_uri,"
                    " body, file_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        bot_account,
                        chat_id,
                        jami_msg_id,
                        author_uri,
                        body,
                        file_id,
                        int(time.time()),
                    ),
                )
            return int(cur.lastrowid)
        except sqlite3.IntegrityError:
            return None

    def get_message(self, bot_account: str, message_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM messages WHERE bot_account = ? AND id = ?",
                (bot_account, message_id),
            ).fetchone()
        return dict(row) if row else None

    def get_message_by_jami_id(self, bot_account: str, jami_msg_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM messages WHERE bot_account = ? AND jami_msg_id = ?",
                (bot_account, jami_msg_id),
            ).fetchone()
        return dict(row) if row else None

    # --------------------------------------------------------------- updates

    def insert_update(self, bot_account: str, payload: dict[str, Any]) -> int:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "INSERT INTO updates (bot_account, payload, created_at) VALUES (?, ?, ?)",
                (bot_account, json.dumps(payload, ensure_ascii=False), int(time.time())),
            )
        return int(cur.lastrowid)

    def get_updates(
        self, bot_account: str, offset: int = 0, limit: int = 100
    ) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM updates WHERE bot_account = ? AND update_id >= ?"
                " ORDER BY update_id LIMIT ?",
                (bot_account, offset, limit),
            ).fetchall()
        results: list[dict[str, Any]] = []
        for r in rows:
            payload = json.loads(r["payload"])
            payload["update_id"] = r["update_id"]
            results.append(payload)
        return results

    def delete_updates_below(self, bot_account: str, offset: int) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "DELETE FROM updates WHERE bot_account = ? AND update_id < ?",
                (bot_account, offset),
            )

    def delete_update(self, update_id: int) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM updates WHERE update_id = ?", (update_id,))

    def pending_update_count(self, bot_account: str) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS c FROM updates WHERE bot_account = ?", (bot_account,)
            ).fetchone()
        return int(row["c"])

    # -------------------------------------------------------------- webhooks

    def set_webhook(self, bot_account: str, url: str, secret_token: str = "") -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO webhooks (bot_account, url, secret_token) VALUES (?, ?, ?)"
                " ON CONFLICT(bot_account) DO UPDATE SET url = excluded.url,"
                " secret_token = excluded.secret_token, last_error = ''",
                (bot_account, url, secret_token),
            )

    def delete_webhook(self, bot_account: str) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "DELETE FROM webhooks WHERE bot_account = ?", (bot_account,)
            )
        return cur.rowcount > 0

    def get_webhook(self, bot_account: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM webhooks WHERE bot_account = ?", (bot_account,)
            ).fetchone()
        return dict(row) if row else None

    def set_webhook_error(self, bot_account: str, error: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE webhooks SET last_error = ? WHERE bot_account = ?",
                (error[:500], bot_account),
            )

    # ----------------------------------------------------------------- files

    def insert_file(
        self,
        file_id: str,
        bot_account: str,
        local_path: str = "",
        file_name: str = "",
        file_size: int = 0,
    ) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO files (file_id, bot_account, local_path, file_name, file_size,"
                " created_at) VALUES (?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(file_id) DO UPDATE SET local_path = excluded.local_path,"
                " file_name = excluded.file_name, file_size = excluded.file_size",
                (file_id, bot_account, local_path, file_name, file_size, int(time.time())),
            )

    def get_file(self, file_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM files WHERE file_id = ?", (file_id,)).fetchone()
        return dict(row) if row else None
