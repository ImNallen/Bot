import { describe, expect, it } from "vitest";
import { formatBytes, formatDuration, modelLabel, relativeDay } from "./ui";

describe("menu formatting", () => {
  it("names Ollama models the way the menu shows them", () => {
    expect(modelLabel("qwen3.6:35b-a3b-q8_0")).toEqual({ name: "qwen3.6 35B-A3B", quant: "Q8" });
    expect(modelLabel("qwen3.6:27b")).toEqual({ name: "qwen3.6 27B", quant: "" });
    expect(modelLabel("llama3.2:3b-instruct-q4_K_M")).toEqual({ name: "llama3.2 3B-INSTRUCT", quant: "Q4_K_M" });
    expect(modelLabel("mistral:latest")).toEqual({ name: "mistral", quant: "" });
    expect(modelLabel("phi4")).toEqual({ name: "phi4", quant: "" });
  });

  it("says when an event is in plain words", () => {
    const today = new Date(2026, 10, 10, 15, 0);
    expect(relativeDay(new Date(2026, 10, 10), today)).toBe("Today");
    expect(relativeDay(new Date(2026, 10, 9), today)).toBe("Yesterday");
    expect(relativeDay(new Date(2026, 10, 12), today)).toBe("Thu · in 2 days");
    expect(relativeDay(new Date(2026, 10, 5), today)).toBe("5 days ago");
    expect(relativeDay(new Date(2026, 11, 24), today)).toBe("24 Dec");
  });

  it("rounds sizes and durations", () => {
    expect(formatBytes(38_704_982_915)).toBe("39 GB");
    expect(formatBytes(0)).toBe("0 B");
    expect(formatDuration(33_120)).toBe("9 h 12 min");
    expect(formatDuration(2040)).toBe("34 min");
  });
});
