import asyncio
from datetime import datetime

from companion.config import Settings
from companion.conversation import Conversation
from companion.llm import LLM
from companion.remember import Memorizer, with_memory
from companion.reply import MoodEvent, SentenceEvent

DIM, RESET = "\033[2m", "\033[0m"
HELP = "Type to talk. /memories lists what it remembers, /reset clears the conversation, /quit exits and saves memories."


async def run() -> None:
    settings = Settings.load()
    llm = LLM(settings)
    print(f"{DIM}Loading {settings.model}…{RESET}", flush=True)
    await llm.warm()
    convo, memorizer = with_memory(llm, settings)
    await convo.prime()
    print(f"{DIM}{HELP}{RESET}\n")
    while True:
        try:
            text = (await asyncio.to_thread(input, "you › ")).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            await save_memories(convo, memorizer)
            return
        if not text:
            continue
        if text == "/quit":
            await save_memories(convo, memorizer)
            return
        if text == "/memories":
            memories = memorizer.store.all() if memorizer else []
            print("\n".join(f"{DIM}{m.id:>3} {m.kind:<5} {m.text}{' · ' + str(m.on) if m.on else ''}{RESET}" for m in memories) or f"{DIM}(nothing yet){RESET}", "\n")
            continue
        if text == "/reset":
            convo.reset()
            print(f"{DIM}(conversation cleared){RESET}\n")
            continue

        first_sentence = None
        async for timed in convo.reply(text):
            match timed.event:
                case MoodEvent(mood):
                    print(f"{settings.name.lower()} {DIM}[{mood}]{RESET} ›", end="", flush=True)
                case SentenceEvent(sentence):
                    first_sentence = first_sentence or timed.seconds
                    print(f" {sentence}", end="", flush=True)
        ttft = convo.first_token_seconds
        print(f"\n{DIM}first token {ttft or 0:.2f} s · first sentence {first_sentence or 0:.2f} s{RESET}\n")


async def save_memories(convo: Conversation, memorizer: Memorizer | None) -> None:
    if not memorizer or not convo.exchanges:
        return
    print(f"{DIM}Remembering…{RESET}", flush=True)
    for memory in await memorizer.remember(convo.exchanges, datetime.now()):
        print(f"{DIM}· {memory.text}{' · ' + str(memory.on) if memory.on else ''}{RESET}")
    convo.exchanges.clear()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
