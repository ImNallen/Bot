import json
from collections.abc import Callable
from typing import Literal, TypedDict

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


class TextEvent(TypedDict):
    type: Literal["heard", "said"]
    text: str


Event = StateEvent | MoodEvent | LevelsEvent | StatusEvent | TextEvent

COMMANDS = ("mute", "unmute", "sleep")


class Hub:
    """Broadcasts what the bot is doing to overlay windows over a WebSocket on localhost.

    A client that connects late gets the current state and mood straight away, so a restarted
    overlay shows the right face without waiting for the next change.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8765) -> None:
        self.host, self.port = host, port
        self.on_command: Callable[[str], None] = lambda name: None
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
                if name := parse_command(raw):
                    self.on_command(name)
        finally:
            self._clients.discard(client)


def parse_command(raw: str | bytes) -> str | None:
    """A command from an overlay window, or None for anything that is not one."""
    try:
        message = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    name = message.get("name") if isinstance(message, dict) and message.get("type") == "command" else None
    return name if name in COMMANDS else None
