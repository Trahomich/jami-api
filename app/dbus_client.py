import threading
from typing import Any

import gi

gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
from gi.repository import Gio, GLib

import structlog
from dasbus.connection import SessionMessageBus
from dasbus.loop import EventLoop

from app.services.event_bus import EventBus

logger = structlog.get_logger()


class JamiDBusClient:
    _instance: "JamiDBusClient | None" = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._bus = SessionMessageBus()
        self._event_loop = EventLoop()
        self._proxy: Any = None
        self._call_proxy: Any = None
        self._connected = False
        self._event_thread: threading.Thread | None = None
        self._gio_bus: Any = None
        self._event_bus: EventBus | None = None

    @classmethod
    def get_instance(cls) -> "JamiDBusClient":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def connect(self, event_bus: EventBus | None = None) -> None:
        self._event_bus = event_bus
        try:
            self._proxy = self._bus.get_proxy(
                "cx.ring.Ring",
                "/cx/ring/Ring/ConfigurationManager",
            )
            self._call_proxy = self._bus.get_proxy(
                "cx.ring.Ring",
                "/cx/ring/Ring/CallManager",
            )
            self._gio_bus = Gio.bus_get_sync(Gio.BusType.SESSION)
            self._connected = True
            self._event_thread = threading.Thread(target=self._run_loop, daemon=True)
            self._event_thread.start()
            logger.info("dbus_connected")
        except Exception as e:
            logger.error("dbus_connection_failed", error=str(e))
            self._connected = False

    def _run_loop(self) -> None:
        if self._gio_bus and self._event_bus:
            self._subscribe_signals()
        self._event_loop.run()

    def _subscribe_signals(self) -> None:
        self._gio_bus.signal_subscribe(
            "cx.ring.Ring",
            "cx.ring.Ring.ConfigurationManager",
            None,
            "/cx/ring/Ring/ConfigurationManager",
            None,
            Gio.DBusSignalFlags.NONE,
            self._on_dbus_signal,
        )
        self._gio_bus.signal_subscribe(
            "cx.ring.Ring",
            "cx.ring.Ring.CallManager",
            None,
            "/cx/ring/Ring/CallManager",
            None,
            Gio.DBusSignalFlags.NONE,
            self._on_dbus_signal,
        )

    def _on_dbus_signal(
        self, connection: Any, sender: str, path: str, iface: str, signal: str, params: Any
    ) -> None:
        if not self._event_bus:
            return
        try:
            val = params.unpack()
        except Exception:
            return

        if signal == "swarmMessageReceived":
            self._handle_swarm_message(val)
        elif signal == "incomingAccountMessage":
            self._handle_incoming_message(val)
        elif signal == "incomingCall":
            self._handle_incoming_call(val)
        elif signal == "callStateChanged":
            self._handle_call_state(val)
        elif signal == "conversationRequestReceived":
            self._handle_conversation_request(val)
        elif signal == "composingStatusChanged":
            self._handle_composing_status(val)
        else:
            logger.debug("dbus_signal_unhandled", signal=signal)

    def _handle_swarm_message(self, val: tuple) -> None:
        account_id, conv_id, message_data = val[0], val[1], val[2]
        msg_id = message_data[0]
        msg_type = message_data[1]
        parent = message_data[2]
        details = dict(message_data[3]) if len(message_data) > 3 else {}

        event = {
            "type": "message",
            "source": "swarm",
            "account_id": account_id,
            "conversation_id": conv_id,
            "message": {
                "id": msg_id,
                "type": msg_type,
                "parent": parent,
                "author": details.get("author", ""),
                "body": details.get("body", ""),
                "timestamp": details.get("timestamp", ""),
            },
        }
        self._event_bus.publish_sync(account_id, event)
        logger.info(
            "swarm_message_received", account_id=account_id, body=details.get("body", "")[:50]
        )

    def _handle_incoming_message(self, val: tuple) -> None:
        account_id, from_uri, payloads = val[0], val[1], val[2]
        event = {
            "type": "message",
            "source": "direct",
            "account_id": account_id,
            "from": from_uri,
            "payloads": {k: v for k, v in payloads.items()}
            if isinstance(payloads, dict)
            else str(payloads),
        }
        self._event_bus.publish_sync(account_id, event)
        logger.info("incoming_message", account_id=account_id, from_uri=from_uri)

    def _handle_incoming_call(self, val: tuple) -> None:
        account_id, call_id, from_uri = val[0], val[1], val[2]
        event = {
            "type": "incoming_call",
            "account_id": account_id,
            "call_id": call_id,
            "from": from_uri,
        }
        self._event_bus.publish_sync(account_id, event)
        logger.info("incoming_call", account_id=account_id, call_id=call_id)

    def _handle_call_state(self, val: tuple) -> None:
        account_id, call_id, state = val[0], val[1], val[2]
        event = {
            "type": "call_state",
            "account_id": account_id,
            "call_id": call_id,
            "state": state,
        }
        self._event_bus.publish_sync(account_id, event)
        logger.info("call_state_changed", account_id=account_id, call_id=call_id, state=state)

    def _handle_conversation_request(self, val: tuple) -> None:
        account_id, conv_id, meta = val[0], val[1], val[2]
        event = {
            "type": "conversation_request",
            "account_id": account_id,
            "conversation_id": conv_id,
        }
        self._event_bus.publish_sync(account_id, event)
        logger.info("conversation_request", account_id=account_id, conv_id=conv_id)

    def _handle_composing_status(self, val: tuple) -> None:
        account_id, conv_id, from_uri, status = val[0], val[1], val[2], val[3]
        event = {
            "type": "composing_status",
            "account_id": account_id,
            "conversation_id": conv_id,
            "from": from_uri,
            "status": status,
        }
        self._event_bus.publish_sync(account_id, event)

    def disconnect(self) -> None:
        self._event_loop.quit()
        self._bus.disconnect()
        self._connected = False
        logger.info("dbus_disconnected")

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def proxy(self) -> Any:
        if not self._connected:
            raise RuntimeError("D-Bus not connected")
        return self._proxy

    def add_account(self, details: dict[str, str]) -> str:
        return self.proxy.addAccount(details)

    def remove_account(self, account_id: str) -> None:
        self.proxy.removeAccount(account_id)

    def get_account_list(self) -> list[str]:
        return self.proxy.getAccountList()

    def get_account_details(self, account_id: str) -> dict[str, str]:
        return dict(self.proxy.getAccountDetails(account_id))

    def get_volatile_account_details(self, account_id: str) -> dict[str, str]:
        return dict(self.proxy.getVolatileAccountDetails(account_id))

    def set_account_details(self, account_id: str, details: dict[str, str]) -> None:
        self.proxy.setAccountDetails(account_id, details)

    def register_name(self, account_id: str, name: str, password: str = "") -> int:
        return self.proxy.registerName(account_id, name, password)

    def lookup_name(self, account_id: str, name: str) -> int:
        return self.proxy.lookupName(account_id, "", name)

    def get_contacts(self, account_id: str) -> list[dict[str, Any]]:
        contacts = self.proxy.getContacts(account_id)
        return [dict(c) for c in contacts]

    def add_contact(self, account_id: str, uri: str) -> None:
        self.proxy.addContact(account_id, uri)

    def remove_contact(self, account_id: str, uri: str, ban: bool = False) -> None:
        self.proxy.removeContact(account_id, uri, ban)

    def get_contact_details(self, account_id: str, uri: str) -> dict[str, str]:
        return dict(self.proxy.getContactDetails(account_id, uri))

    def send_text_message(self, account_id: str, to: str, payloads: dict[str, str]) -> str:
        return str(self.proxy.sendTextMessage(account_id, to, payloads, 0))

    def send_conversation_message(
        self, account_id: str, conv_id: str, body: str, parent: str = ""
    ) -> None:
        self.proxy.sendMessage(account_id, conv_id, body, parent, 0)

    def get_conversations(self, account_id: str) -> list[str]:
        return self.proxy.getConversations(account_id)

    def get_conversation_requests(self, account_id: str) -> list[dict[str, Any]]:
        requests = self.proxy.getConversationRequests(account_id)
        return [dict(r) for r in requests]

    def accept_conversation_request(self, account_id: str, conv_id: str) -> None:
        self.proxy.acceptConversationRequest(account_id, conv_id)

    def decline_conversation_request(self, account_id: str, conv_id: str) -> None:
        self.proxy.declineConversationRequest(account_id, conv_id)

    def load_conversation(
        self, account_id: str, conv_id: str, from_msg: str = "", count: int = 50
    ) -> int:
        return self.proxy.loadConversation(account_id, conv_id, from_msg, count)

    def get_conversation_messages(
        self, account_id: str, conv_id: str, count: int, from_msg: str = "", search: str = ""
    ) -> list[dict[str, Any]]:
        self.load_conversation(account_id, conv_id, from_msg, count)
        return []

    def place_call(self, account_id: str, to: str) -> str:
        return self._call_proxy.placeCall(account_id, to)

    def accept_call(self, account_id: str, call_id: str) -> None:
        self._call_proxy.accept(account_id, call_id)

    def hang_up(self, account_id: str, call_id: str) -> None:
        self._call_proxy.hangUp(account_id, call_id)

    def get_call_list(self, account_id: str) -> list[str]:
        return self._call_proxy.getCallList(account_id)

    def get_call_details(self, account_id: str, call_id: str) -> dict[str, str]:
        return dict(self._call_proxy.getCallDetails(account_id, call_id))

    def send_file(self, account_id: str, conversation_id: str, file_path: str) -> str:
        return self.proxy.sendFile(account_id, conversation_id, file_path, "", "")

    def download_file(
        self, account_id: str, conversation_id: str, interaction_id: str, file_path: str
    ) -> None:
        self.proxy.downloadFile(
            account_id, conversation_id, interaction_id, interaction_id, file_path
        )

    def file_transfer_info(
        self, account_id: str, conversation_id: str, interaction_id: str
    ) -> dict[str, Any]:
        error_code, path, total_size, bytes_progress = self.proxy.fileTransferInfo(
            account_id, conversation_id, interaction_id
        )
        return {
            "error_code": error_code,
            "path": path,
            "total_size": total_size,
            "bytes_progress": bytes_progress,
        }
