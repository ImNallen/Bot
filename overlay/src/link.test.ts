import { describe, expect, it } from "vitest";
import { parseEvent } from "./link";

const PREFS = { mic: null, voice: "af_heart", speed: 1, sensitivity: 0.5, pause: 0.65, interrupt: true, keepLoaded: true, thinking: false, learn: true, memoryOn: true };
const json = (v: unknown) => JSON.stringify(v);

describe("parseEvent", () => {
  it("accepts the events the backend broadcasts", () => {
    expect(parseEvent('{"type":"state","state":"speaking"}')).toEqual({ type: "state", state: "speaking" });
    expect(parseEvent('{"type":"mood","mood":"sad"}')).toEqual({ type: "mood", mood: "sad" });
    expect(parseEvent('{"type":"levels","speech":0.12,"mic":0}')).toEqual({ type: "levels", speech: 0.12, mic: 0 });
    const status = { type: "status", micOn: false, model: "qwen", memories: 3, prefs: PREFS };
    expect(parseEvent(json(status))).toEqual(status);
    expect(parseEvent('{"type":"said","text":"Good good good."}')).toEqual({ type: "said", text: "Good good good." });
  });

  it("accepts replies for the menu pages", () => {
    const replies = [
      { type: "devices", inputs: [{ name: "Wave:3", detail: "", default: true }] },
      { type: "models", server: "http://localhost:11434", running: false, version: null, installed: [] },
      { type: "memories", on: true, items: [{ id: 4, kind: "event", text: "has a demo", on: "2026-11-12", learned: "2026-11-09", followUp: false }] },
      {
        type: "stats", on: true, since: null, talkingSeconds: 0, conversations: 0, interruptions: 0, replyStart: null, cloudBytes: 0,
        moods: [{ mood: "happy", share: 0.5 }], perDay: [0, 2], favoriteWord: null, saidQuestion: 0, chattyHour: 21, longestChatSeconds: 0,
      },
    ];
    for (const reply of replies) expect(parseEvent(json(reply))).toEqual(reply);
  });

  it("drops anything malformed or unknown instead of guessing", () => {
    const bad = [
      "not json", "null", '{"type":"state","state":"dancing"}', '{"type":"mood"}', '{"type":"levels","speech":-1,"mic":0}',
      '{"type":"levels","speech":"loud","mic":0}', '{"type":"teleport"}', '{"type":"heard","text":""}', '{"type":"toString"}',
      '{"type":"status","micOn":"yes","model":"q","memories":1}',
      json({ type: "status", micOn: true, model: "q", memories: 1, prefs: { ...PREFS, speed: "fast" } }),
      json({ type: "memories", on: true, items: [{ id: 1, kind: "rumor", text: "x", on: null, learned: "", followUp: false }] }),
      json({ type: "devices", inputs: "Wave:3" }),
    ];
    for (const raw of bad) expect(parseEvent(raw), raw).toBeNull();
  });
});
