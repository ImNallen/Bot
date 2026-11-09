import re
from dataclasses import dataclass
from enum import StrEnum


class Mood(StrEnum):
    NEUTRAL = "neutral"
    HAPPY = "happy"
    SAD = "sad"
    SURPRISED = "surprised"
    ANNOYED = "annoyed"


@dataclass(frozen=True)
class MoodEvent:
    mood: Mood


@dataclass(frozen=True)
class SentenceEvent:
    text: str


ReplyEvent = MoodEvent | SentenceEvent

_TAG = re.compile(r"\s*\[\s*mood\s*:\s*([a-z]+)\s*\]", re.IGNORECASE)
_TAG_MAX_LEN = 32
_BOUNDARY = re.compile(r"[.!?…]+[\"')\]]*(?=\s)|\n+")

EMOJI = re.compile(
    "[\U0001f000-\U0001faff\U00002600-\U000027bf\U0001f1e6-\U0001f1ff\u200d\ufe0f\u2b50\u2b55\u23f0-\u23ff]+"
)
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_STRAY_TAG = re.compile(r"\[\s*mood\s*:[^\]]*\]", re.IGNORECASE)
_LIST_MARKER = re.compile(r"^\s*(?:[-*+•]|\d+[.)]|#+)\s+")
_MARKUP = re.compile(r"[*_`~#>|]")
_SPACES = re.compile(r"\s+")


def to_speech(text: str) -> str:
    text = _STRAY_TAG.sub("", text)
    text = _LINK.sub(r"\1", text)
    text = _LIST_MARKER.sub("", text)
    text = _MARKUP.sub("", text)
    text = EMOJI.sub("", text)
    return _SPACES.sub(" ", text).strip()


def parse_mood(name: str) -> Mood:
    try:
        return Mood(name.lower())
    except ValueError:
        return Mood.NEUTRAL


class ReplyParser:
    """Turns a streamed LLM reply into one MoodEvent followed by speakable SentenceEvents.

    Feed chunks as they arrive; call finish() once the stream ends to flush the last sentence.
    """

    def __init__(self) -> None:
        self._buffer = ""
        self._mood_sent = False

    def feed(self, chunk: str) -> list[ReplyEvent]:
        self._buffer += chunk
        events: list[ReplyEvent] = []
        if not self._mood_sent:
            mood = self._take_mood(final=False)
            if mood is None:
                return events
            events.append(MoodEvent(mood))
        events.extend(self._take_sentences())
        return events

    def finish(self) -> list[ReplyEvent]:
        events: list[ReplyEvent] = []
        if not self._mood_sent:
            events.append(MoodEvent(self._take_mood(final=True) or Mood.NEUTRAL))
        events.extend(self._take_sentences())
        events.extend(self._sentence(self._buffer))
        self._buffer = ""
        return events

    def _take_mood(self, final: bool) -> Mood | None:
        match = _TAG.match(self._buffer)
        if match:
            self._buffer = self._buffer[match.end():]
            self._mood_sent = True
            return parse_mood(match.group(1))
        head = self._buffer.lstrip()
        could_still_be_tag = head == "" or (head.startswith("[") and "]" not in head and len(head) < _TAG_MAX_LEN)
        if could_still_be_tag and not final:
            return None
        self._mood_sent = True
        return Mood.NEUTRAL

    def _take_sentences(self) -> list[SentenceEvent]:
        events: list[SentenceEvent] = []
        while match := _BOUNDARY.search(self._buffer):
            raw, self._buffer = self._buffer[: match.end()], self._buffer[match.end():]
            events.extend(self._sentence(raw))
        return events

    @staticmethod
    def _sentence(raw: str) -> list[SentenceEvent]:
        text = to_speech(raw)
        return [SentenceEvent(text)] if any(c.isalnum() for c in text) else []
