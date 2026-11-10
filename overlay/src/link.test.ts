import { describe, expect, it } from "vitest";
import { parseEvent } from "./link";

describe("parseEvent", () => {
  it("accepts the three event types the backend sends", () => {
    expect(parseEvent('{"type":"state","state":"speaking"}')).toEqual({ type: "state", state: "speaking" });
    expect(parseEvent('{"type":"mood","mood":"sad"}')).toEqual({ type: "mood", mood: "sad" });
    expect(parseEvent('{"type":"levels","speech":0.12,"mic":0}')).toEqual({ type: "levels", speech: 0.12, mic: 0 });
    expect(parseEvent('{"type":"status","micOn":false,"model":"qwen","memories":3}')).toEqual({ type: "status", micOn: false, model: "qwen", memories: 3 });
    expect(parseEvent('{"type":"said","text":"Good good good."}')).toEqual({ type: "said", text: "Good good good." });
  });

  it("drops anything malformed or unknown instead of guessing", () => {
    for (const raw of ["not json", "null", '{"type":"state","state":"dancing"}', '{"type":"mood"}', '{"type":"levels","speech":-1,"mic":0}', '{"type":"levels","speech":"loud","mic":0}', '{"type":"teleport"}', '{"type":"heard","text":""}', '{"type":"status","micOn":"yes","model":"q","memories":1}']) {
      expect(parseEvent(raw)).toBeNull();
    }
  });
});
