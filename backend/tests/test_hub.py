import asyncio
import json

from websockets.asyncio.client import connect

from companion.hub import Hub, parse_request


async def received(ws, count: int) -> list[dict]:
    return [json.loads(await asyncio.wait_for(ws.recv(), 1)) for _ in range(count)]


def test_requests_reach_the_handler_replies_go_to_the_asker_and_junk_is_ignored():
    async def scenario():
        hub = Hub(port=0)
        got: list[dict] = []

        async def handle(request):
            got.append(request)
            return {"type": "voices", "voices": []} if request["type"] == "get" else None

        hub.on_request = handle
        await hub.start()
        url = f"ws://127.0.0.1:{hub.port}"
        try:
            async with connect(url) as asker, connect(url) as bystander:
                for raw in ['{"type":"command","name":"mute"}', '{"type":"command","name":"self-destruct"}', "nonsense", '{"type":"get","what":"voices"}']:
                    await asker.send(raw)
                assert await received(asker, 1) == [{"type": "voices", "voices": []}]
                try:
                    await asyncio.wait_for(bystander.recv(), 0.2)
                    raise AssertionError("a reply went to a window that did not ask")
                except TimeoutError:
                    pass
        finally:
            await hub.stop()
        return got

    assert asyncio.run(scenario()) == [{"type": "command", "name": "mute"}, {"type": "get", "what": "voices"}]


def test_parse_request_accepts_each_kind_and_refuses_ambiguous_ones():
    assert parse_request('{"type":"set","key":"speed","value":1.2}') == {"type": "set", "key": "speed", "value": 1.2}
    assert parse_request('{"type":"preview","voice":"af_bella"}') == {"type": "preview", "voice": "af_bella"}
    assert parse_request('{"type":"forget","id":7}') == {"type": "forget", "id": 7}
    assert parse_request('{"type":"forget","all":true}') == {"type": "forget", "id": None}
    for raw in ['{"type":"forget"}', '{"type":"forget","id":true}', '{"type":"get","what":"secrets"}', '{"type":"set","key":"speed"}', "[1]"]:
        assert parse_request(raw) is None, raw


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
