import asyncio

import pytest

from src.a2a.protocol import Message, MessageType
from src.a2a.broker import A2ABroker


@pytest.mark.asyncio
async def test_publish_subscribe():
    broker = A2ABroker()
    received = []

    async def subscriber():
        async for msg in broker.subscribe("test.topic"):
            received.append(msg)
            break

    task = asyncio.create_task(subscriber())
    await asyncio.sleep(0)
    await broker.publish(
        Message(type=MessageType.EVENT, sender_id="a", topic="test.topic", payload={"x": 1})
    )
    await asyncio.wait_for(task, timeout=1)
    assert len(received) == 1
    assert received[0].payload["x"] == 1


@pytest.mark.asyncio
async def test_direct_send():
    broker = A2ABroker()
    inbox = await broker.register_direct_inbox("agent-b")

    sent = await broker.send(
        Message(type=MessageType.REQUEST, sender_id="agent-a", target_id="agent-b", payload={"op": "ping"})
    )
    assert sent is True
    msg = await asyncio.wait_for(inbox.get(), timeout=1)
    assert msg.payload["op"] == "ping"


