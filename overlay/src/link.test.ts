import { describe, expect, it } from "vitest";
import { parseEvent } from "./link";

describe("parseEvent", () => {
  it("accepts the three event types the backend sends", () => {
    expect(parseEvent('{"type":"state","state":"speaking"}')).toEqual({ type: "state", state: "speaking" });
    expect(parseEvent('{"type":"mood","mood":"sad"}')).toEqual({ type: "mood", mood: "sad" });
    expect(parseEvent('{"type":"levels","speech":0.12,"mic":0}')).toEqual({ type: "levels", speech: 0.12, mic: 0 });
  });

  it("drops anything malformed or unknown instead of guessing", () => {
    for (const raw of ["not json", "null", '{"type":"state","state":"dancing"}', '{"type":"mood"}', '{"type":"levels","speech":-1,"mic":0}', '{"type":"levels","speech":"loud","mic":0}', '{"type":"teleport"}']) {
      expect(parseEvent(raw)).toBeNull();
    }
  });
});
