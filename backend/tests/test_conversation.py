import asyncio

from companion.config import Settings
from companion.conversation import Conversation
from companion.reply import Mood, MoodEvent, SentenceEvent


class FakeLLM:
    def __init__(self) -> None:
        self.prompts: list[list[dict]] = []

    async def stream(self, messages):
        self.prompts.append(messages)
        for chunk in ["[mood:", "happy] Hi ", "there. Bye."]:
            yield chunk


def talk(convo: Conversation, text: str) -> list:
    async def collect():
        return [t.event async for t in convo.reply(text)]

    return asyncio.run(collect())


def test_reply_streams_mood_then_sentences_and_records_history():
    convo = Conversation(FakeLLM(), Settings())
    assert talk(convo, "hello") == [MoodEvent(Mood.HAPPY), SentenceEvent("Hi there."), SentenceEvent("Bye.")]
    assert convo.history == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "[mood:happy] Hi there. Bye."},
    ]


def test_prompt_only_grows_by_appending_except_at_rare_trims():
    llm = FakeLLM()
    turns = 4
    convo = Conversation(llm, Settings(history_turns=turns))
    for i in range(30):
        talk(convo, f"message {i}")

    breaks = sum(1 for prev, cur in zip(llm.prompts, llm.prompts[1:]) if cur[: len(prev)] != prev)
    assert breaks <= 30 // (turns // 2)
    assert max(len(p) for p in llm.prompts) <= 2 + len(convo.prefix) + 2 * turns


def test_cancelled_reply_leaves_history_untouched():
    convo = Conversation(FakeLLM(), Settings())

    async def stop_after_first_event():
        stream = convo.reply("hello")
        first = await anext(stream)
        await stream.aclose()
        return first.event

    assert asyncio.run(stop_after_first_event()) == MoodEvent(Mood.HAPPY)
    assert convo.history == []
