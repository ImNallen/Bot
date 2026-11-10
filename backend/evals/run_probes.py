"""Score the persona's voice and latency against fixed probes.

Each probe runs in a fresh conversation. Usage: uv run python evals/run_probes.py [--runs N] [--model TAG]
"""

import argparse
import asyncio
import re
import statistics
from dataclasses import dataclass, replace
from pathlib import Path

from companion.config import Settings
from companion.conversation import Conversation
from companion.llm import LLM
from companion.reply import EMOJI, Mood, MoodEvent, SentenceEvent

PROBES = Path(__file__).with_name("probes.txt")
TAG = re.compile(rf"\s*\[mood:({'|'.join(m.value for m in Mood)})\]")
FORMATTING = re.compile(r"\*\*|`|#|\n\s*(?:[-*•]|\d+[.)])\s|\n\s*\n")
BANNED = ["great question", "happy to help", "let me know if", "anything else", "as an ai", "i'd be glad", "certainly!", "absolutely!"]
CONTRACTION = re.compile(r"\b\w+'(?:t|re|ll|ve|d|m)\b|\b(?:it|that|what|he|she|there)'s\b", re.IGNORECASE)
STOP = set("a an the is are am i you to of and or it this that do does my me what how why can be in on for with so just".split())


@dataclass
class Result:
    prompt: str
    raw: str
    mood: Mood
    sentences: list[str]
    first_token: float
    first_sentence: float
    checks: dict[str, bool]


def words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z']+", text.lower()) if w not in STOP}


def score(prompt: str, raw: str, sentences: list[str]) -> dict[str, bool]:
    body = TAG.sub("", raw, count=1)
    spoken = " ".join(sentences)
    questions = re.findall(r"([^.!?]*)\?", spoken)
    p, first = words(prompt), words(sentences[0]) if sentences else set()
    return {
        "mood tag": bool(TAG.match(raw)),
        "short": len(spoken.split()) <= 35,
        "no formatting": not FORMATTING.search(body) and not EMOJI.search(body),
        "no assistant talk": not any(b in raw.lower() for b in BANNED),
        "question word": all(q.rstrip().lower().endswith("question") for q in questions),
        "no restating": not p or len(p & first) / len(p | first or {""}) < 0.5,
        "no contractions": not CONTRACTION.search(spoken),
    }


async def probe(llm: LLM, settings: Settings, prompt: str) -> Result:
    convo = Conversation(llm, settings)
    mood, sentences, first_sentence = Mood.NEUTRAL, [], None
    async for timed in convo.reply(prompt):
        match timed.event:
            case MoodEvent(m):
                mood = m
            case SentenceEvent(s):
                sentences.append(s)
                first_sentence = first_sentence or timed.seconds
    return Result(prompt, convo.last_raw, mood, sentences, convo.first_token_seconds or 0, first_sentence or 0, score(prompt, convo.last_raw, sentences))


def pct(values: list[float], q: float) -> float:
    return statistics.quantiles(values, n=100)[int(q) - 1] if len(values) > 1 else values[0]


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--model")
    ap.add_argument("--inline", action="store_true", help="put examples in the system prompt instead of as chat turns")
    args = ap.parse_args()
    settings = Settings.from_env()
    if args.model:
        settings = replace(settings, model=args.model)
    settings = replace(settings, examples_as_turns=not args.inline)
    llm = LLM(settings)
    await llm.warm()
    await probe(llm, settings, "Hello.")

    prompts = [p for p in PROBES.read_text().splitlines() if p.strip()] * args.runs
    results = [await probe(llm, settings, p) for p in prompts]

    for r in results:
        failed = [k for k, ok in r.checks.items() if not ok]
        status = "ok  " if not failed else "FAIL"
        print(f"{status} {r.first_token:4.2f}s {r.first_sentence:4.2f}s [{r.mood}] {r.prompt}")
        print(f"     › {' '.join(r.sentences)}")
        if failed:
            print(f"     failed: {', '.join(failed)}")

    mode = "examples as chat turns" if settings.examples_as_turns else "examples inline"
    print(f"\n{settings.model} · {mode} · {len(results)} replies")
    for check in results[0].checks:
        passed = sum(r.checks[check] for r in results)
        print(f"  {check:<18} {passed}/{len(results)}")
    spoken_words = [w.lower() for r in results for w in re.findall(r"[A-Za-z']+", " ".join(r.sentences))]
    articles = sum(w in ("the", "a", "an") for w in spoken_words)
    print(f"  article rate       {articles / len(spoken_words):.1%} of words (plain English is about 6-8%)")
    asking = sum("?" in " ".join(r.sentences) for r in results)
    print(f"  asks a question    {asking}/{len(results)} (aim for under 40%)")
    ft = [r.first_token for r in results]
    fs = [r.first_sentence for r in results]
    print("  latency below is a fresh conversation, so the system prompt is processed cold every time")
    print(f"  first token        median {statistics.median(ft):.2f} s · p90 {pct(ft, 90):.2f} s")
    print(f"  first sentence     median {statistics.median(fs):.2f} s · p90 {pct(fs, 90):.2f} s")


if __name__ == "__main__":
    asyncio.run(main())
