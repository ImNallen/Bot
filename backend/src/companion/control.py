import asyncio
from collections.abc import Callable
from datetime import date

from companion.audio import input_devices
from companion.config import write_saved
from companion.conversation import Conversation
from companion.hub import Event, Request
from companion.memory import Memory, needs_follow_up
from companion.prefs import to_settings
from companion.stats import summarize
from companion.tts import KOKORO_VOICES, describe_voice
from companion.voice import VoiceLoop


class Control:
    """Answers the overlay's menu: changes settings while running, and looks things up for its pages.

    Changes are saved so they survive a restart, and every change publishes a fresh status so all
    open windows show the same thing.
    """

    def __init__(
        self,
        loop: VoiceLoop,
        convo: Conversation,
        use_mic: Callable[[str | None], None],
        microphones: Callable[[], list[dict]] = input_devices,
        save: Callable = write_saved,
        today: Callable[[], date] = date.today,
    ) -> None:
        self.loop, self.convo, self.llm = loop, convo, convo.llm
        self.settings = loop.settings
        self.use_mic, self.microphones, self.save, self.today = use_mic, microphones, save, today
        self._background: set[asyncio.Task] = set()

    async def handle(self, request: Request) -> Event | None:
        match request:
            case {"type": "command", "name": name}:
                self.loop.command(name)
            case {"type": "set", "key": key, "value": value}:
                return await self._set(key, value)
            case {"type": "get", "what": what}:
                return await self._get(what)
            case {"type": "preview", "voice": voice} if voice in KOKORO_VOICES:
                self._spawn(self.loop.preview(voice))
            case {"type": "forget", "id": memory_id}:
                if store := self._store():
                    store.clear() if memory_id is None else store.forget(memory_id)
                    self.loop.publish_status()
                return self._memories()
        return None

    async def _set(self, key: str, value: object) -> Event | None:
        changes = to_settings(key, value)
        if changes is None:
            return None
        old_model = self.settings.model
        if "model" in changes and changes["model"] != old_model:
            installed = {m["name"] for m in (await self.llm.models())["installed"]}
            if changes["model"] not in installed:
                return {"type": "notice", "text": f"{changes['model']} is not installed in Ollama"}
        if "mic" in changes and changes["mic"] != self.settings.mic:
            try:
                self.use_mic(changes["mic"])
            except Exception as error:
                return {"type": "notice", "text": f"Could not switch microphones: {error}"}
        for field, new in changes.items():
            setattr(self.settings, field, new)
        if "model" in changes and changes["model"] != old_model:
            self._spawn(self._switch_model(old_model))
        if "keep_loaded" in changes:
            self._spawn(self.llm.warm())
        self.save(self.settings)
        self.loop.settings_changed()
        return None

    async def _switch_model(self, old: str) -> None:
        """Frees the old model's memory, loads the new one, and tells open menus when it is ready."""
        await self.llm.unload(old)
        await self.llm.warm()
        await self.convo.prime()
        self.loop.publish({"type": "models", **await self.llm.models()})

    async def _get(self, what: str) -> Event:
        match what:
            case "devices":
                return {"type": "devices", "inputs": await asyncio.to_thread(self.microphones)}
            case "voices":
                return {"type": "voices", "engine": "Kokoro 82M", "voices": [describe_voice(v) for v in KOKORO_VOICES]}
            case "models":
                return {"type": "models", **await self.llm.models()}
            case "memories":
                return self._memories()
            case _:
                stats = self.loop.stats
                return {"type": "stats", "on": stats is not None, **summarize(stats.all() if stats else [], self.today())}

    def _memories(self) -> Event:
        store, today = self._store(), self.today()
        return {"type": "memories", "on": store is not None, "items": [memory_item(m, today) for m in (store.all() if store else [])]}

    def _store(self):
        return self.loop.memorizer.store if self.loop.memorizer else None

    def _spawn(self, work) -> None:
        task = asyncio.create_task(work)
        self._background.add(task)
        task.add_done_callback(self._finished)

    def _finished(self, task: asyncio.Task) -> None:
        self._background.discard(task)
        if not task.cancelled() and task.exception():
            print(f"menu request failed: {task.exception()!r}", flush=True)


def memory_item(m: Memory, today: date) -> dict:
    return {
        "id": m.id,
        "kind": m.kind,
        "text": m.text,
        "on": m.on.isoformat() if m.on else None,
        "learned": m.created.date().isoformat(),
        "followUp": needs_follow_up(m, today),
    }
