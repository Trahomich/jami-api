import pytest


@pytest.mark.asyncio
async def test_event_bus_subscribe_publish():
    from app.services.event_bus import EventBus

    bus = EventBus()
    queue = bus.subscribe("acc1")
    await bus.publish("acc1", {"type": "test"})
    data = queue.get_nowait()
    assert data == {"type": "test"}


@pytest.mark.asyncio
async def test_event_bus_unsubscribe():
    from app.services.event_bus import EventBus

    bus = EventBus()
    queue = bus.subscribe("acc1")
    bus.unsubscribe("acc1", queue)
    assert queue not in bus._subscribers["acc1"]
