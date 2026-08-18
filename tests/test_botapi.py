import asyncio
import os

import pytest

# conftest mocks pydantic_settings; give app.config a real, env-driven stub
# BEFORE anything imports app.main / app.routers.botapi in this session.
import app.config as _config_mod


class _StubSettings:
    host = "0.0.0.0"
    port = 8080
    log_level = "info"
    dbus_address = ""
    alert_account_id = ""
    alert_conversation_id = ""
    alert_recipients: list = []

    def __init__(self) -> None:
        self.db_path = os.getenv("JAMI_API_DB_PATH", "data/botapi.db")
        self.files_dir = os.getenv("JAMI_API_FILES_DIR", "data/botapi-files")


_config_mod.Settings = _StubSettings

import app.main as _main_mod  # noqa: E402
import app.routers.botapi as _botapi_mod  # noqa: E402
from app.botapi.service import BotApiError, BotAPIService  # noqa: E402
from app.botapi.store import BotStore  # noqa: E402
from app.services.event_bus import EventBus  # noqa: E402

ACCOUNT = "botacc123"
CONV = "convabc456"
PEER = "141b732d5c8e82f5e5ba36a9d1f023c866f0af34"


@pytest.fixture
def store(tmp_path):
    return BotStore(str(tmp_path / "botapi.db"))


@pytest.fixture
def service(store, mock_dbus_client, tmp_path):
    bus = EventBus()
    return BotAPIService(
        store, bus, client_factory=lambda: mock_dbus_client, files_dir=str(tmp_path / "files")
    )


def _swarm_event(body: str = "Привет!", author: str = PEER, msg_id: str = "msg-001") -> dict:
    return {
        "type": "message",
        "source": "swarm",
        "account_id": ACCOUNT,
        "conversation_id": CONV,
        "message": {
            "id": msg_id,
            "type": "text/plain",
            "parent": "",
            "author": author,
            "body": body,
            "timestamp": "1777105547",
        },
    }


def _direct_event(body: str = "direct hi") -> dict:
    return {
        "type": "message",
        "source": "direct",
        "account_id": ACCOUNT,
        "from": PEER,
        "payloads": {"text/plain": body},
    }


# ------------------------------------------------------------------- store


@pytest.mark.asyncio
async def test_token_lifecycle(store):
    record = store.create_token(ACCOUNT, name="testbot")
    assert record["token"].count(":") == 1
    assert store.get_token(record["token"])["account_id"] == ACCOUNT
    assert ACCOUNT in store.accounts_with_tokens()

    store.create_token(ACCOUNT)
    assert len(store.list_tokens()) == 2

    assert store.delete_token(record["token"]) is True
    assert store.get_token(record["token"]) is None


@pytest.mark.asyncio
async def test_chat_id_derivation(store):
    group1 = store.get_or_create_chat(ACCOUNT, "group", CONV, conv_id=CONV)
    group2 = store.get_or_create_chat(ACCOUNT, "group", CONV, conv_id=CONV)
    private = store.get_or_create_chat(ACCOUNT, "private", PEER, peer_uri=PEER)

    assert group1["chat_id"] == group2["chat_id"]  # stable
    assert group1["chat_id"] < 0  # groups are negative, telegram-style
    assert private["chat_id"] > 0  # private chats are positive
    assert group1["chat_id"] != private["chat_id"]

    assert store.get_chat(ACCOUNT, private["chat_id"])["peer_uri"] == PEER


# ----------------------------------------------------------------- getMe


@pytest.mark.asyncio
async def test_get_me(service, mock_dbus_client):
    mock_dbus_client.proxy.getAccountDetails.return_value = {"Account.alias": "AlertBot"}
    me = service.get_me(ACCOUNT)
    assert me["is_bot"] is True
    assert me["first_name"] == "AlertBot"
    assert isinstance(me["id"], int)


@pytest.mark.asyncio
async def test_get_me_fallback_alias(service, mock_dbus_client):
    mock_dbus_client.proxy.getAccountDetails.return_value = {}
    me = service.get_me(ACCOUNT)
    assert me["first_name"] == ACCOUNT[:8]


# ------------------------------------------------------------ sendMessage


@pytest.mark.asyncio
async def test_send_message_to_swarm(service, store, mock_dbus_client):
    mock_dbus_client.proxy.sendMessage.return_value = "jami-777"
    chat = store.get_or_create_chat(ACCOUNT, "group", CONV, conv_id=CONV)

    message = service.send_message(ACCOUNT, chat["chat_id"], "hello swarm")

    mock_dbus_client.proxy.sendMessage.assert_called_once_with(
        ACCOUNT, CONV, "hello swarm", "", 0
    )
    assert message["message_id"] > 0
    assert message["chat"]["id"] == chat["chat_id"]
    assert message["text"] == "hello swarm"
    assert store.get_message(ACCOUNT, message["message_id"])["jami_msg_id"] == "jami-777"


@pytest.mark.asyncio
async def test_send_message_direct(service, store, mock_dbus_client):
    mock_dbus_client.proxy.sendTextMessage.return_value = "481613349902297"
    chat = store.get_or_create_chat(ACCOUNT, "private", PEER, peer_uri=PEER)

    message = service.send_message(ACCOUNT, chat["chat_id"], "hello direct")

    mock_dbus_client.proxy.sendTextMessage.assert_called_once_with(
        ACCOUNT, PEER, {"text/plain": "hello direct"}, 0
    )
    assert message["message_id"] > 0


@pytest.mark.asyncio
async def test_send_message_with_reply(service, store, mock_dbus_client):
    mock_dbus_client.proxy.sendMessage.return_value = "jami-888"
    chat = store.get_or_create_chat(ACCOUNT, "group", CONV, conv_id=CONV)
    original = store.insert_message(ACCOUNT, chat["chat_id"], "jami-001", PEER, "orig", "")

    service.send_message(ACCOUNT, chat["chat_id"], "re:orig", reply_to_message_id=original)

    call = mock_dbus_client.proxy.sendMessage.call_args[0]
    assert call[3] == "jami-001"  # parent message id passed


@pytest.mark.asyncio
async def test_send_message_unknown_chat(service):
    with pytest.raises(BotApiError) as exc:
        service.send_message(ACCOUNT, 424242, "text")
    assert exc.value.code == 400


@pytest.mark.asyncio
async def test_send_message_bad_reply(service, store):
    chat = store.get_or_create_chat(ACCOUNT, "group", CONV, conv_id=CONV)
    with pytest.raises(BotApiError) as exc:
        service.send_message(ACCOUNT, chat["chat_id"], "text", reply_to_message_id=999)
    assert exc.value.code == 400


# --------------------------------------------------------- update pipeline


@pytest.mark.asyncio
async def test_swarm_event_becomes_update(service, store):
    await service.handle_event(ACCOUNT, _swarm_event())

    updates = store.get_updates(ACCOUNT)
    assert len(updates) == 1
    update = updates[0]
    assert update["update_id"] > 0

    message = update["message"]
    assert message["text"] == "Привет!"
    assert message["date"] == 1777105547
    assert message["chat"]["type"] == "group"
    assert message["chat"]["id"] < 0
    assert message["from"]["id"] > 0
    assert message["from"]["is_bot"] is False
    assert message["message_id"] > 0


@pytest.mark.asyncio
async def test_direct_event_becomes_private_update(service, store):
    await service.handle_event(ACCOUNT, _direct_event())

    updates = store.get_updates(ACCOUNT)
    assert len(updates) == 1
    message = updates[0]["message"]
    assert message["text"] == "direct hi"
    assert message["chat"]["type"] == "private"
    assert message["chat"]["id"] > 0


@pytest.mark.asyncio
async def test_self_echo_filtered(service, store):
    store.create_token(ACCOUNT, bot_uri=PEER)
    await service.handle_event(ACCOUNT, _swarm_event(author=PEER))
    assert store.get_updates(ACCOUNT) == []


@pytest.mark.asyncio
async def test_duplicate_jami_message_not_dup_update(service, store):
    await service.handle_event(ACCOUNT, _swarm_event(msg_id="dup-1"))
    await service.handle_event(ACCOUNT, _swarm_event(msg_id="dup-1"))
    assert len(store.get_updates(ACCOUNT)) == 1


@pytest.mark.asyncio
async def test_file_transfer_event(service, store):
    event = _swarm_event(body="report.pdf")
    event["message"]["type"] = "application/data-transfer+pdf"
    await service.handle_event(ACCOUNT, event)

    updates = store.get_updates(ACCOUNT)
    message = updates[0]["message"]
    assert "text" not in message
    assert message["document"]["file_name"] == "report.pdf"
    file_id = message["document"]["file_id"]
    assert store.get_file(file_id) is not None


@pytest.mark.asyncio
async def test_updates_offset_semantics(service, store):
    await service.handle_event(ACCOUNT, _swarm_event(msg_id="m1"))
    await service.handle_event(ACCOUNT, _swarm_event(msg_id="m2"))
    await service.handle_event(ACCOUNT, _swarm_event(msg_id="m3"))

    updates = store.get_updates(ACCOUNT)
    ids = [u["update_id"] for u in updates]
    assert len(ids) == 3

    # offset confirms everything below it and returns the rest
    store.delete_updates_below(ACCOUNT, ids[1])
    remaining = store.get_updates(ACCOUNT, offset=ids[1])
    assert [u["update_id"] for u in remaining] == ids[1:]


@pytest.mark.asyncio
async def test_non_message_events_ignored(service, store):
    await service.handle_event(
        ACCOUNT, {"type": "call_state", "account_id": ACCOUNT, "state": "OVER"}
    )
    await service.handle_event(
        ACCOUNT,
        {"type": "composing_status", "account_id": ACCOUNT, "from": PEER, "status": "1"},
    )
    assert store.get_updates(ACCOUNT) == []


# ---------------------------------------------------------------- webhooks


@pytest.mark.asyncio
async def test_webhook_dispatch_success(service, store, monkeypatch):
    class FakeResponse:
        status_code = 200

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, json=None, headers=None):
            FakeClient.last_request = {"url": url, "json": json, "headers": headers}
            return FakeResponse()

    monkeypatch.setattr("app.botapi.service.httpx.AsyncClient", FakeClient)

    store.set_webhook(ACCOUNT, "https://example.com/hook", secret_token="s3cret")
    await service.handle_event(ACCOUNT, _swarm_event())
    await asyncio.sleep(0.1)  # let dispatch task run

    request = FakeClient.last_request
    assert request["url"] == "https://example.com/hook"
    assert request["headers"]["X-Telegram-Bot-Api-Secret-Token"] == "s3cret"
    assert request["json"]["message"]["text"] == "Привет!"

    # delivered update is removed from the polling queue
    assert store.get_updates(ACCOUNT) == []
    info = store.get_webhook(ACCOUNT)
    assert info["last_error"] == ""


@pytest.mark.asyncio
async def test_webhook_delivery_failure_keeps_update(service, store, monkeypatch):
    class FailingClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, json=None, headers=None):
            raise ConnectionError("boom")

    monkeypatch.setattr("app.botapi.service.httpx.AsyncClient", FailingClient)

    store.set_webhook(ACCOUNT, "https://example.com/hook")
    await service.handle_event(ACCOUNT, _swarm_event())
    await asyncio.sleep(0.1)

    assert len(store.get_updates(ACCOUNT)) == 1
    assert "boom" in store.get_webhook(ACCOUNT)["last_error"]


# ------------------------------------------------------------------- files


@pytest.mark.asyncio
async def test_send_document(service, store, mock_dbus_client, tmp_path):
    mock_dbus_client.proxy.sendFile.return_value = "inter-42"
    chat = store.get_or_create_chat(ACCOUNT, "group", CONV, conv_id=CONV)
    path = tmp_path / "doc.txt"
    path.write_text("file content")

    message = service.send_document(ACCOUNT, chat["chat_id"], str(path), "doc.txt")

    mock_dbus_client.proxy.sendFile.assert_called_once()
    call = mock_dbus_client.proxy.sendFile.call_args[0]
    assert call[0] == ACCOUNT
    assert call[1] == CONV

    file_id = message["document"]["file_id"]
    assert message["document"]["file_name"] == "doc.txt"
    assert message["document"]["file_size"] == 12
    assert store.get_file(file_id)["local_path"] == str(path)


@pytest.mark.asyncio
async def test_send_document_private_unsupported(service, store):
    chat = store.get_or_create_chat(ACCOUNT, "private", PEER, peer_uri=PEER)
    with pytest.raises(BotApiError) as exc:
        service.send_document(ACCOUNT, chat["chat_id"], "/tmp/x", "x")
    assert "swarm" in exc.value.description


@pytest.mark.asyncio
async def test_get_file_triggers_download(service, store, mock_dbus_client, monkeypatch, tmp_path):
    def fake_download(account, conv, interaction, target):
        with open(target, "w") as fh:
            fh.write("downloaded")

    monkeypatch.setattr(mock_dbus_client, "download_file", fake_download)
    store.insert_file(f"{CONV}:inter-9", ACCOUNT, "", "data.bin")
    store.get_or_create_chat(ACCOUNT, "group", CONV, conv_id=CONV)

    result = service.get_file(ACCOUNT, f"{CONV}:inter-9")

    assert result["file_path"].startswith("files/")
    record = store.get_file(f"{CONV}:inter-9")
    assert record["local_path"] != ""
    assert record["file_size"] == len("downloaded")


# -------------------------------------------------- HTTP-level tests


@pytest.fixture
def http_env(store, service, monkeypatch, tmp_path):
    """Wire real store/service into the router; stub init via env-driven files dir."""
    monkeypatch.setattr(_botapi_mod, "init_botapi", lambda bus: None)
    monkeypatch.setattr(_botapi_mod, "store", store)
    monkeypatch.setattr(_botapi_mod, "service", service)
    monkeypatch.setenv("JAMI_API_FILES_DIR", str(tmp_path / "files"))
    record = store.create_token(ACCOUNT, name="httptest", bot_uri="self-uri")
    return _botapi_mod, record["token"]


def _client():
    from fastapi.testclient import TestClient

    return TestClient(_main_mod.app)


def test_http_get_me(http_env):
    _, token = http_env
    with _client() as client:
        r = client.post(f"/bot{token}/getMe")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["result"]["is_bot"] is True


def test_http_bad_token(http_env):
    _, _ = http_env
    with _client() as client:
        r = client.post("/bot000:bad/getMe")
    assert r.status_code == 401
    assert r.json()["ok"] is False


def test_http_unknown_method(http_env):
    _, token = http_env
    with _client() as client:
        r = client.post(f"/bot{token}/sendSticker", json={})
    assert r.status_code == 404
    assert "not supported" in r.json()["description"]


@pytest.mark.asyncio
async def test_http_send_message_regression_optional_reply(http_env, store):
    """reply_to_message_id must be optional (regression for param parsing bug)."""
    _, token = http_env
    chat = store.get_or_create_chat(ACCOUNT, "group", CONV, conv_id=CONV)

    with _client() as client:
        r = client.post(
            f"/bot{token}/sendMessage", json={"chat_id": chat["chat_id"], "text": "hi"}
        )
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["result"]["text"] == "hi"


def test_http_send_message_chat_not_found(http_env):
    _, token = http_env
    with _client() as client:
        r = client.post(f"/bot{token}/sendMessage", json={"chat_id": 424242, "text": "hi"})
    assert r.status_code == 400
    assert "chat not found" in r.json()["description"]


def test_http_send_message_form_and_query_params(http_env, store, mock_dbus_client):
    _, token = http_env
    chat = store.get_or_create_chat(ACCOUNT, "private", PEER, peer_uri=PEER)

    with _client() as client:
        r = client.post(
            f"/bot{token}/sendMessage?chat_id={chat['chat_id']}", data={"text": "via form"}
        )
    assert r.status_code == 200
    mock_dbus_client.proxy.sendTextMessage.assert_called_once_with(
        ACCOUNT, PEER, {"text/plain": "via form"}, 0
    )


@pytest.mark.asyncio
async def test_http_get_updates_full_cycle(http_env, store, service, mock_dbus_client):
    _, token = http_env
    await service.handle_event(ACCOUNT, _swarm_event(msg_id="http-1"))

    with _client() as client:
        r = client.post(f"/bot{token}/getUpdates", data={"timeout": 0})
    body = r.json()
    assert r.status_code == 200
    assert len(body["result"]) == 1
    update_id = body["result"][0]["update_id"]

    # offset confirms consumption
    with _client() as client:
        r = client.post(
            f"/bot{token}/getUpdates", json={"offset": update_id + 1, "timeout": 0}
        )
    assert r.json()["result"] == []


def test_http_set_webhook_flow(http_env):
    _, token = http_env
    with _client() as client:
        r = client.post(
            f"/bot{token}/setWebhook", json={"url": "https://bot.example/hook"}
        )
        assert r.json()["result"] is True

        r = client.get(f"/bot{token}/getWebhookInfo")
        assert r.json()["result"]["url"] == "https://bot.example/hook"

        r = client.post(f"/bot{token}/deleteWebhook")
        assert r.json()["result"] is True

        r = client.get(f"/bot{token}/getWebhookInfo")
        assert r.json()["result"]["url"] == ""


def test_http_set_webhook_bad_url(http_env):
    _, token = http_env
    with _client() as client:
        r = client.post(f"/bot{token}/setWebhook", json={"url": "ftp://nope"})
    assert r.status_code == 400


def test_http_admin_tokens(http_env):
    _, _ = http_env
    with _client() as client:
        r = client.post("/api/bots", json={"account_id": "acc2", "name": "second"})
        assert r.status_code == 200
        token2 = r.json()["token"]

        r = client.get("/api/bots")
        assert len(r.json()) == 2

        r = client.delete(f"/api/bots/{token2}")
        assert r.json()["status"] == "deleted"

        r = client.delete(f"/api/bots/{token2}")
        assert r.status_code == 404


def test_http_send_document_multipart(http_env, store, mock_dbus_client):
    _, token = http_env
    mock_dbus_client.proxy.sendFile.return_value = "inter-100"
    chat = store.get_or_create_chat(ACCOUNT, "group", CONV, conv_id=CONV)

    with _client() as client:
        r = client.post(
            f"/bot{token}/sendDocument",
            data={"chat_id": str(chat["chat_id"]), "caption": "see attached"},
            files={"document": ("notes.txt", b"hello file", "text/plain")},
        )
    assert r.status_code == 200
    result = r.json()["result"]
    assert result["document"]["file_name"] == "notes.txt"
    assert result["caption"] == "see attached"
    mock_dbus_client.proxy.sendFile.assert_called_once()


# -------------------------------------------------- end-to-end via bus


@pytest.mark.asyncio
async def test_end_to_end_event_bus_consumption(service, mock_dbus_client, tmp_path):
    bus = EventBus()
    store2 = BotStore(str(tmp_path / "e2e.db"))
    store2.create_token(ACCOUNT, bot_uri="self-uri")
    svc = BotAPIService(
        store2, bus, client_factory=lambda: mock_dbus_client, files_dir=str(tmp_path / "files")
    )
    await svc.start()

    bus.publish_sync(ACCOUNT, _swarm_event())
    for _ in range(20):
        await asyncio.sleep(0.05)
        if store2.get_updates(ACCOUNT):
            break

    updates = store2.get_updates(ACCOUNT)
    assert len(updates) == 1
    assert updates[0]["message"]["text"] == "Привет!"

    await svc.stop()
    store2.close()
