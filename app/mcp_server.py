import json

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from app.dbus_client import JamiDBusClient

mcp = FastMCP(
    name="Jami API",
    instructions=(
        "MCP server for Jami messaging. Use these tools to send messages, "
        "manage contacts, handle calls, and transfer files via the Jami daemon."
    ),
    streamable_http_path="/mcp",
    host="0.0.0.0",
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    ),
)


def _get_client() -> JamiDBusClient:
    client = JamiDBusClient.get_instance()
    if not client.is_connected:
        raise RuntimeError("D-Bus not connected")
    return client


@mcp.tool()
def list_accounts() -> list[str]:
    """List all Jami account IDs registered on this daemon."""
    return _get_client().get_account_list()


@mcp.tool()
def get_account_info(account_id: str) -> dict:
    """Get detailed info for a Jami account including registration status.

    Args:
        account_id: The Jami account ID (e.g. "6b658ed9429e6b8d")
    """
    return _get_client().get_account_details(account_id)


@mcp.tool()
def get_account_status(account_id: str) -> dict:
    """Get volatile/runtime status for a Jami account (registration state, DHT port, etc).

    Args:
        account_id: The Jami account ID
    """
    return _get_client().get_volatile_account_details(account_id)


@mcp.tool()
def list_contacts(account_id: str) -> list[dict]:
    """List all contacts for a Jami account.

    Args:
        account_id: The Jami account ID
    """
    return _get_client().get_contacts(account_id)


@mcp.tool()
def add_contact(account_id: str, uri: str) -> str:
    """Add a contact to a Jami account.

    Args:
        account_id: The Jami account ID
        uri: The contact's Jami ID hash (e.g. "141b732d5c8e82f5e5ba36a9d1f023c866f0af34")
    """
    _get_client().add_contact(account_id, uri)
    return f"Contact {uri} added"


@mcp.tool()
def remove_contact(account_id: str, uri: str) -> str:
    """Remove a contact from a Jami account.

    Args:
        account_id: The Jami account ID
        uri: The contact's Jami ID hash
    """
    _get_client().remove_contact(account_id, uri)
    return f"Contact {uri} removed"


@mcp.tool()
def list_conversations(account_id: str) -> list[str]:
    """List all swarm conversation IDs for a Jami account.

    Args:
        account_id: The Jami account ID
    """
    return _get_client().get_conversations(account_id)


@mcp.tool()
def send_message(
    account_id: str, conversation_id: str, body: str, parent_message_id: str = ""
) -> str:
    """Send a text message in a swarm conversation.

    Args:
        account_id: The Jami account ID
        conversation_id: The swarm conversation ID
        body: The message text to send
        parent_message_id: Optional parent message ID for threading
    """
    _get_client().send_conversation_message(account_id, conversation_id, body, parent_message_id)
    return "Message sent"


@mcp.tool()
def send_direct_message(account_id: str, to: str, body: str) -> str:
    """Send a direct text message to a contact (not via swarm conversation).

    Args:
        account_id: The Jami account ID
        to: The recipient's Jami ID hash
        body: The message text to send
    """
    msg_id = _get_client().send_text_message(account_id, to, {"text/plain": body})
    return f"Message sent, id={msg_id}"


@mcp.tool()
def place_call(account_id: str, to: str) -> str:
    """Place an audio/video call to a contact.

    Args:
        account_id: The Jami account ID
        to: The recipient's Jami ID hash
    """
    call_id = _get_client().place_call(account_id, to)
    return f"Call placed, call_id={call_id}"


@mcp.tool()
def hangup_call(account_id: str, call_id: str) -> str:
    """Hang up an active call.

    Args:
        account_id: The Jami account ID
        call_id: The call ID to hang up
    """
    _get_client().hang_up(account_id, call_id)
    return f"Call {call_id} hung up"


@mcp.tool()
def accept_call(account_id: str, call_id: str) -> str:
    """Accept an incoming call.

    Args:
        account_id: The Jami account ID
        call_id: The call ID to accept
    """
    _get_client().accept_call(account_id, call_id)
    return f"Call {call_id} accepted"


@mcp.tool()
def list_calls(account_id: str) -> list[str]:
    """List active call IDs for a Jami account.

    Args:
        account_id: The Jami account ID
    """
    return _get_client().get_call_list(account_id)


@mcp.tool()
def send_file(account_id: str, conversation_id: str, file_path: str) -> str:
    """Send a file in a swarm conversation.

    Args:
        account_id: The Jami account ID
        conversation_id: The swarm conversation ID
        file_path: Absolute path to the file to send
    """
    result = _get_client().send_file(account_id, conversation_id, file_path)
    return f"File sent, interaction_id={result}"


@mcp.tool()
def get_file_status(account_id: str, conversation_id: str, interaction_id: str) -> dict:
    """Get the transfer status of a file.

    Args:
        account_id: The Jami account ID
        conversation_id: The swarm conversation ID
        interaction_id: The file interaction ID
    """
    return _get_client().file_transfer_info(account_id, conversation_id, interaction_id)


@mcp.resource("jami://accounts")
def accounts_resource() -> str:
    """All registered Jami accounts with their details."""
    client = _get_client()
    accounts = client.get_account_list()
    result = []
    for acc_id in accounts:
        details = client.get_account_details(acc_id)
        volatile = client.get_volatile_account_details(acc_id)
        result.append(
            {
                "id": acc_id,
                "alias": details.get("Account.alias", ""),
                "type": details.get("Account.type", ""),
                "registration_status": volatile.get("Account.registrationStatus", ""),
                "device_id": volatile.get("Account.deviceID", ""),
            }
        )
    return json.dumps(result, indent=2)


@mcp.resource("jami://accounts/{account_id}/contacts")
def contacts_resource(account_id: str) -> str:
    """Contacts for a specific Jami account."""
    contacts = _get_client().get_contacts(account_id)
    return json.dumps(contacts, indent=2)


@mcp.resource("jami://accounts/{account_id}/conversations")
def conversations_resource(account_id: str) -> str:
    """Conversations for a specific Jami account."""
    convs = _get_client().get_conversations(account_id)
    return json.dumps(convs, indent=2)


mcp_app = mcp.streamable_http_app()
