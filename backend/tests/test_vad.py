import numpy as np

from companion.vad import CHUNK, CHUNK_MS, Rechunker, Segmenter, SpeechEnded, SpeechStarted


def chunk(value: float) -> np.ndarray:
    return np.full(CHUNK, value, dtype=np.float32)


def run(seg: Segmenter, probs: list[float]) -> list[tuple[int, object]]:
    events = []
    for i, p in enumerate(probs):
        events += [(i, e) for e in seg.feed(chunk(i), p)]
    return events


def ms(n: float) -> int:
    return round(n / CHUNK_MS)


def test_utterance_starts_after_start_window_and_ends_after_silence():
    seg = Segmenter(start_ms=96, end_silence_ms=500)
    probs = [0.0] * 5 + [0.9] * 20 + [0.0] * 20
    events = run(seg, probs)
    assert [type(e) for _, e in events] == [SpeechStarted, SpeechEnded]
    start_at, end_at = events[0][0], events[1][0]
    assert start_at == 5 + ms(96) - 1
    assert end_at == 25 + ms(500) - 1


def test_ended_audio_includes_preroll_so_the_first_syllable_is_not_clipped():
    seg = Segmenter(start_ms=96, end_silence_ms=200, preroll_ms=320)
    probs = [0.0] * 20 + [0.9] * 10 + [0.0] * 10
    ended = [e for _, e in run(seg, probs) if isinstance(e, SpeechEnded)][0]
    first_chunk_value = ended.audio[0]
    assert first_chunk_value == 20 - ms(320)


def test_short_blip_never_starts_speech():
    seg = Segmenter(start_ms=160)
    assert run(seg, [0.0, 0.9, 0.9, 0.0, 0.9, 0.0] * 5) == []


def test_brief_pause_inside_speech_does_not_end_the_utterance():
    seg = Segmenter(end_silence_ms=500)
    probs = [0.9] * 10 + [0.0] * ms(300) + [0.9] * 10 + [0.0] * ms(600)
    assert [type(e) for _, e in run(seg, probs)] == [SpeechStarted, SpeechEnded]


def test_raising_start_window_makes_it_harder_to_trigger():
    probs = [0.9] * ms(130) + [0.0] * 30
    assert run(Segmenter(start_ms=96), probs)
    assert run(Segmenter(start_ms=200), probs) == []


def test_rechunker_emits_fixed_chunks_and_keeps_the_remainder():
    r = Rechunker()
    assert r.push(np.ones(300)) == []
    out = r.push(np.ones(800))
    assert [len(c) for c in out] == [CHUNK, CHUNK]
    assert len(r.push(np.ones(0))) == 0
