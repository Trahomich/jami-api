import os

import httpx
import pytest

BASE_URL = os.getenv("JAMI_API_URL", "http://192.168.99.10:8080")
ACCOUNT_ID = os.getenv("JAMI_ACCOUNT_ID", "6b658ed9429e6b8d")
CONTACT_URI = os.getenv("JAMI_CONTACT_URI", "141b732d5c8e82f5e5ba36a9d1f023c866f0af34")
CONV_ID = os.getenv("JAMI_CONV_ID", "28ae52ed5d4334a7f3cd8e0b588229d7523e9bd0")


@pytest.fixture
def client():
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as c:
        yield c


class TestHealth:
    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert data["dbus"] == "connected"


class TestAccounts:
    def test_list_accounts(self, client):
        r = client.get("/api/accounts")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert ACCOUNT_ID in data

    def test_get_account(self, client):
        r = client.get(f"/api/accounts/{ACCOUNT_ID}")
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == ACCOUNT_ID
        assert "details" in data
        assert "volatile" in data
        assert data["details"]["Account.type"] == "RING"
        assert data["volatile"]["Account.registrationStatus"] == "REGISTERED"

    def test_get_account_nonexistent(self, client):
        r = client.get("/api/accounts/nonexistent123")
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == "nonexistent123"
        assert data["details"] == {}
        assert data["volatile"] == {}


class TestContacts:
    def test_list_contacts(self, client):
        r = client.get(f"/api/accounts/{ACCOUNT_ID}/contacts")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_get_contact(self, client):
        r = client.get(f"/api/accounts/{ACCOUNT_ID}/contacts/{CONTACT_URI}")
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == CONTACT_URI
        assert data["confirmed"] == "true"

    def test_get_contact_nonexistent(self, client):
        r = client.get(f"/api/accounts/{ACCOUNT_ID}/contacts/nonexistent000")
        assert r.status_code == 200
        data = r.json()
        assert data == {}


class TestMessages:
    def test_send_direct_message(self, client):
        r = client.post(
            f"/api/accounts/{ACCOUNT_ID}/messages",
            json={"to": CONTACT_URI, "body": "test from integration"},
        )
        assert r.status_code == 200
        data = r.json()
        assert "message_id" in data
        assert isinstance(data["message_id"], str)

    def test_list_conversations(self, client):
        r = client.get(f"/api/accounts/{ACCOUNT_ID}/conversations")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert CONV_ID in data

    def test_send_conversation_message(self, client):
        r = client.post(
            f"/api/accounts/{ACCOUNT_ID}/conversations/{CONV_ID}/messages",
            json={"to": CONTACT_URI, "body": "swarm test from integration"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "sent"

    def test_get_conversation_messages(self, client):
        r = client.get(
            f"/api/accounts/{ACCOUNT_ID}/conversations/{CONV_ID}/messages",
            params={"count": 5},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "loaded"


class TestCalls:
    def test_list_calls(self, client):
        r = client.get(f"/api/accounts/{ACCOUNT_ID}/calls")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)

    def test_place_and_hangup_call(self, client):
        r = client.post(
            f"/api/accounts/{ACCOUNT_ID}/calls",
            json={"to": CONTACT_URI},
        )
        assert r.status_code == 200
        data = r.json()
        assert "call_id" in data
        call_id = data["call_id"]

        r = client.post(f"/api/accounts/{ACCOUNT_ID}/calls/{call_id}/hangup")
        assert r.status_code == 200

    def test_hangup_nonexistent_call(self, client):
        r = client.post(f"/api/accounts/{ACCOUNT_ID}/calls/fake-call-id/hangup")
        assert r.status_code in (200, 500)


class TestFiles:
    def test_send_file_not_found_path(self, client):
        r = client.post(
            f"/api/accounts/{ACCOUNT_ID}/files/send",
            json={"conversation_id": CONV_ID, "file_path": "/nonexistent/file.txt"},
        )
        assert r.status_code == 500

    def test_file_status_nonexistent(self, client):
        r = client.get(f"/api/accounts/{ACCOUNT_ID}/files/{CONV_ID}/nonexistent-id/status")
        assert r.status_code == 200
        data = r.json()
        assert "error_code" in data
        assert data["error_code"] != 0
