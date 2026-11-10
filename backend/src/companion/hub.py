import json
from collections.abc import Awaitable, Callable
from typing import Any, Literal, TypedDict

from websockets.asyncio.server import Server, ServerConnection, broadcast, serve


class StateEvent(TypedDict):
    type: Literal["state"]
    state: str


class MoodEvent(TypedDict):
    type: Literal["mood"]
    mood: str


class LevelsEvent(TypedDict):
    type: Literal["levels"]
    speech: float
    mic: float


class StatusEvent(TypedDict):
    type: Literal["status"]
    micOn: bool
    model: str
    memories: int
    prefs: dict[str, Any]


class TextEvent(TypedDict):
    type: Literal["heard", "said", "notice"]
    text: str


class ReplyEvent(TypedDict):
    """An answer to a `get` request: devices, voices, models, memories or stats, with its own fields."""

    type: str


Event = StateEvent | MoodEvent | LevelsEvent | StatusEvent | TextEvent | ReplyEvent


class Command(TypedDict):
    type: Literal["command"]
    name: Literal["mute", "unmute", "sleep"]


class Set(TypedDict):
    type: Literal["set"]
    key: str
    value: Any


class Get(TypedDict):
    type: Literal["get"]
    what: Literal["devices", "voices", "models", "memories", "stats"]


class Preview(TypedDict):
    type: Literal["preview"]
    voice: str


class Forget(TypedDict):
    """One memory by id, or every memory when id is None (sent as {"all": true})."""

    type: Literal["forget"]
    id: int | None


Request = Command | Set | Get | Preview | Forget

COMMANDS = ("mute", "unmute", "sleep")
GETS = ("devices", "voices", "models", "memories", "stats")


class Hub:
    """Broadcasts what the bot is doing to overlay windows over a WebSocket on localhost, and answers their requests.

    A client that connects late gets the current state, mood and status straight away, so a restarted
    overlay shows the right face without waiting for the next change. A request's reply goes only to
    the window that asked.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8765) -> None:
        self.host, self.port = host, port
        self.on_request: Callable[[Request], Awaitable[Event | None]] = _ignore
        self._clients: set[ServerConnection] = set()
        self._latest: dict[str, str] = {}
        self._server: Server | None = None

    async def start(self) -> None:
        self._server = await serve(self._serve, self.host, self.port, compression=None)
        self.port = self._server.sockets[0].getsockname()[1] if self.port == 0 else self.port

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    def publish(self, event: Event) -> None:
        if event["type"] in ("state", "mood", "status"):
            self._latest[event["type"]] = json.dumps(event)
        broadcast(self._clients, json.dumps(event))

    async def _serve(self, client: ServerConnection) -> None:
        self._clients.add(client)
        try:
            for message in self._latest.values():
                await client.send(message)
            async for raw in client:
                if (request := parse_request(raw)) and (reply := await self.on_request(request)):
                    await client.send(json.dumps(reply))
        finally:
            self._clients.discard(client)


async def _ignore(request: Request) -> None:
    return None


def parse_request(raw: str | bytes) -> Request | None:
    """A request from an overlay window, or None for anything malformed. Values of `set` are checked by whoever applies them."""
    try:
        m = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(m, dict):
        return None
    match m.get("type"):
        case "command" if m.get("name") in COMMANDS:
            return {"type": "command", "name": m["name"]}
        case "set" if isinstance(m.get("key"), str) and "value" in m:
            return {"type": "set", "key": m["key"], "value": m["value"]}
        case "get" if m.get("what") in GETS:
            return {"type": "get", "what": m["what"]}
        case "preview" if isinstance(m.get("voice"), str):
            return {"type": "preview", "voice": m["voice"]}
        case "forget" if m.get("all") is True:
            return {"type": "forget", "id": None}
        case "forget" if isinstance(m.get("id"), int) and not isinstance(m["id"], bool):
            return {"type": "forget", "id": m["id"]}
    return None
