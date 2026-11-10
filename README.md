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

Most settings can be changed while it runs from the menu bar: microphone, voice, speaking speed, sensitivity, the pause before replying, interrupting, model, thinking and memory. Those choices are saved to `~/Library/Application Support/Companion/preferences.json`. Every setting is also an environment variable, and an environment variable wins over a saved choice:

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

## Memory

The companion remembers facts about you and dated events you mention, in `~/Library/Application Support/Companion/memory.db`. Nothing leaves your Mac.

New memories are saved after 45 quiet seconds in voice mode, and when you quit the text chat. At the start of a session it gets a note with what is coming up, what just happened and a few facts. Later in a session, a memory rides along only when it relates to what you said. A past event stays on the list until the bot actually asks how it went.

```sh
uv run companion-memory            # list
uv run companion-memory forget 3   # forget one
uv run companion-memory clear      # forget everything
```

`COMPANION_REMEMBER=false` turns memory off, and with it the Stats page, which counts voice turns in `stats.db` next to the memories. `uv run python evals/memory_eval.py` checks the whole loop with the real model, using a throwaway memory file.

## The overlay

```sh
cd overlay
npm install
npm run tauri dev
```

A transparent, always-on-top window puts the bot in the bottom-right corner of your main display. Clicks pass through everywhere except the bot. It has no menu yet, so quit with `pkill -f companion-overlay`.

Run `uv run companion-voice` in `backend/` alongside it and the two connect over `ws://127.0.0.1:8765`, in either start order. The voice loop then drives the face: listening, thinking and speaking states, the reply's mood, a mouth that moves with the bot's voice, and dozing off after five idle minutes (`COMPANION_SLEEP_AFTER_S`). Without the backend, clicking the bot steps through its states and moods.

`uv run python evals/voice_sim.py --hub` plays a scripted conversation into a running overlay, with no microphone needed.

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
