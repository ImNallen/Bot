import asyncio

from companion.config import Settings
from companion.conversation import Conversation
from companion.llm import LLM
from companion.reply import MoodEvent, SentenceEvent

DIM, RESET = "\033[2m", "\033[0m"
HELP = "Type to talk. /reset clears the conversation, /quit exits."


async def run() -> None:
    settings = Settings.from_env()
    llm = LLM(settings)
    print(f"{DIM}Loading {settings.model}…{RESET}", flush=True)
    await llm.warm()
    convo = Conversation(llm, settings)
    print(f"{DIM}{HELP}{RESET}\n")
    while True:
        try:
            text = (await asyncio.to_thread(input, "you › ")).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not text:
            continue
        if text == "/quit":
            return
        if text == "/reset":
            convo.reset()
            print(f"{DIM}(conversation cleared){RESET}\n")
            continue

        first_sentence = None
        async for timed in convo.reply(text):
            match timed.event:
                case MoodEvent(mood):
                    print(f"{settings.companion_name.lower()} {DIM}[{mood}]{RESET} ›", end="", flush=True)
                case SentenceEvent(sentence):
                    first_sentence = first_sentence or timed.seconds
                    print(f" {sentence}", end="", flush=True)
        ttft = convo.first_token_seconds
        print(f"\n{DIM}first token {ttft or 0:.2f} s · first sentence {first_sentence or 0:.2f} s{RESET}\n")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
