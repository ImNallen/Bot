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

## Talk to it

```sh
cd backend
uv run companion-voice
```

Run it from Terminal (or iTerm). macOS asks for microphone access the first time. The first launch also downloads Parakeet and Kokoro (about 1 GB).

Just talk. It answers after you pause, and you can interrupt it at any time. Each turn prints how long it took from the end of your speech to its voice.

Settings are environment variables:

| Variable | Default | What it does |
| --- | --- | --- |
| `COMPANION_MIC` | system default | Part of the input device name, for example `Wave:3` |
| `COMPANION_SPEAKER` | system default | Part of the output device name |
| `COMPANION_VOICE` | `af_heart` | Kokoro voice, for example `am_puck` or `bm_george` |
| `COMPANION_SPEECH_SPEED` | `1.0` | Speaking speed |
| `COMPANION_PAUSE_MS` | `300` | Silence before it starts working on a reply |
| `COMPANION_REPLY_GAP_MS` | `650` | Silence before it may start speaking. Pauses shorter than this never get answered mid-thought |
| `COMPANION_BARGE_IN_MS` | `192` | How long you must speak over it before it stops |
| `COMPANION_ECHO_CANCELLATION` | `true` | WebRTC echo cancellation so it does not hear itself |

To check latency and interruption without a microphone, run the scripted conversation:

```sh
uv run python evals/voice_sim.py
```

## The overlay

```sh
cd overlay
npm install
npm run tauri dev
```

A transparent, always-on-top window puts the bot in the bottom-right corner of your main display. Clicks pass through everywhere except the bot. Until the backend drives it, clicking the bot steps through its states and moods. It has no menu yet, so quit with `pkill -f companion-overlay`.

`npm run dev` and http://localhost:1420/dev.html shows every expression and state in both themes, plus a live bot with buttons. `npm test` runs the animation tests.

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
