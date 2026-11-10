import asyncio
import json

from websockets.asyncio.client import connect

from companion.hub import Hub


async def received(ws, count: int) -> list[dict]:
    return [json.loads(await asyncio.wait_for(ws.recv(), 1)) for _ in range(count)]


def test_commands_from_clients_reach_the_handler_and_junk_is_ignored():
    async def scenario():
        hub = Hub(port=0)
        got: list[str] = []
        hub.on_command = got.append
        await hub.start()
        try:
            async with connect(f"ws://127.0.0.1:{hub.port}") as client:
                for raw in ['{"type":"command","name":"mute"}', '{"type":"command","name":"self-destruct"}', "nonsense", '{"type":"command","name":"sleep"}']:
                    await client.send(raw)
                await asyncio.sleep(0.1)
        finally:
            await hub.stop()
        return got

    assert asyncio.run(scenario()) == ["mute", "sleep"]


def test_clients_receive_events_and_late_joiners_get_current_state_and_mood():
    async def scenario():
        hub = Hub(port=0)
        await hub.start()
        url = f"ws://127.0.0.1:{hub.port}"
        try:
            async with connect(url) as early:
                await asyncio.sleep(0.05)
                hub.publish({"type": "state", "state": "speaking"})
                hub.publish({"type": "mood", "mood": "happy"})
                hub.publish({"type": "levels", "speech": 0.4, "mic": 0.0})
                assert await received(early, 3) == [
                    {"type": "state", "state": "speaking"},
                    {"type": "mood", "mood": "happy"},
                    {"type": "levels", "speech": 0.4, "mic": 0.0},
                ]
            async with connect(url) as late:
                assert sorted(e["type"] for e in await received(late, 2)) == ["mood", "state"]
        finally:
            await hub.stop()

    asyncio.run(scenario())
