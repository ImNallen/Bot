# Bot

A local desktop companion for macOS. You talk to it, it talks back, and everything runs on your Mac.

## Layout

- `backend/` is the Python side: persona, LLM client, reply parsing, and later audio, speech and memory.
- `design/character.json` holds the bot's geometry, expression presets, motion timings and theme colors. The overlay reads it.
- The Figma file has the visual design: https://www.figma.com/design/bAsFbtMiAeQdODLoDNXd0m

## Run the terminal chat

You need [Ollama](https://ollama.com) running and the model pulled:

```sh
ollama pull qwen3.6:35b-a3b-q8_0
cd backend
uv sync
uv run companion-chat
```

Each reply prints its mood tag and how long the first token and first sentence took.

Environment overrides: `COMPANION_MODEL`, `COMPANION_BASE_URL`, `COMPANION_NAME` (the bot's name), `COMPANION_USER` (your name).

## Tune the voice

```sh
uv run python evals/run_probes.py            # one pass over evals/probes.txt
uv run python evals/run_probes.py --runs 3   # repeat for variance
```

Each reply is checked for a mood tag, length, formatting, assistant phrases, the "question" habit and restating the prompt. The summary gives pass counts and median and p90 latency.

## Tests

```sh
uv run pytest
```
