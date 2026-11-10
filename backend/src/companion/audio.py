import asyncio
import math
import queue
import threading
import time
from collections import deque
from collections.abc import AsyncIterator
from typing import Protocol

import numpy as np
from scipy.signal import firwin, lfilter, resample_poly

from companion.vad import SAMPLE_RATE as MIC_RATE

DEVICE_RATE = 48_000
FRAME = DEVICE_RATE // 100
DECIMATE = DEVICE_RATE // MIC_RATE


class AudioIO(Protocol):
    """Microphone in, speaker out. The voice loop only talks to this."""

    def frames(self) -> AsyncIterator[np.ndarray]:
        """16 kHz mono float32 microphone audio, echo removed where possible."""
        ...

    def play(self, audio: np.ndarray, sample_rate: int) -> float:
        """Queue audio and return the clock time it will start being heard."""
        ...

    def stop(self) -> None:
        """Drop everything queued, immediately."""
        ...

    @property
    def playing(self) -> bool: ...

    @property
    def level(self) -> float:
        """RMS of the audio playing right now, 0 to 1. Drives the mouth later."""
        ...

    def now(self) -> float: ...


def resample(audio: np.ndarray, src: int, dst: int) -> np.ndarray:
    if src == dst:
        return audio
    g = math.gcd(src, dst)
    return resample_poly(audio, dst // g, src // g).astype(np.float32)


def find_device(name: str | None, kind: str) -> int | None:
    import sounddevice as sd

    if not name:
        return None
    for index, device in enumerate(sd.query_devices()):
        if name.lower() in device["name"].lower() and device[f"max_{kind}_channels"] > 0:
            return index
    raise ValueError(f"No {kind} device matching {name!r}. Available: {[d['name'] for d in sd.query_devices()]}")


def input_devices() -> list[dict]:
    """Microphones for the menu. The kind is guessed from the name, since PortAudio does not say how a device connects."""
    import sounddevice as sd

    default = sd.default.device[0]
    found, seen = [], set()
    for index, device in enumerate(sd.query_devices()):
        name = device["name"]
        if device["max_input_channels"] < 1 or name in seen:
            continue
        seen.add(name)
        found.append({"name": name, "detail": _kind_of(name), "default": index == default})
    return found


def _kind_of(name: str) -> str:
    n = name.lower()
    if "macbook" in n or "built-in" in n:
        return "Built-in"
    if any(k in n for k in ("airpods", "bluetooth", "buds", "beats", "headset")):
        return "Bluetooth · adds delay"
    if any(k in n for k in ("blackhole", "loopback", "teams", "zoom", "soundflower", "aggregate", "virtual")):
        return "Virtual"
    return ""


class _Downsampler:
    """Device rate to 16 kHz with an anti-alias filter whose state carries across frames."""

    def __init__(self) -> None:
        self._taps = firwin(63, 0.45 * MIC_RATE, fs=DEVICE_RATE).astype(np.float32)
        self._state = np.zeros(len(self._taps) - 1, dtype=np.float32)

    def __call__(self, frame: np.ndarray) -> np.ndarray:
        filtered, self._state = lfilter(self._taps, 1.0, frame, zi=self._state)
        return filtered[::DECIMATE].astype(np.float32)


class DeviceAudio:
    """Live mic and speaker in one duplex stream, with WebRTC echo cancellation.

    Each mic frame is paired with the speaker frame played at the same moment, which is what the
    echo canceller needs to subtract the bot's own voice from what the mic hears.
    """

    def __init__(self, mic: str | None = None, speaker: str | None = None, echo_cancellation: bool = True) -> None:
        import sounddevice as sd

        self._devices = (find_device(mic, "input"), find_device(speaker, "output"))
        out_info = sd.query_devices(self._devices[1], "output")
        self._out_channels = min(2, out_info["max_output_channels"])
        self._echo_cancellation = echo_cancellation
        self._playback: deque[np.ndarray] = deque()
        self._lock = threading.Lock()
        self._pairs: queue.SimpleQueue[tuple[np.ndarray, np.ndarray] | None] = queue.SimpleQueue()
        self._level = 0.0
        self._queued_samples = 0
        self._stream: sd.Stream | None = None

    def now(self) -> float:
        return time.monotonic()

    @property
    def level(self) -> float:
        return self._level

    @property
    def playing(self) -> bool:
        return self._queued_samples > 0

    def play(self, audio: np.ndarray, sample_rate: int) -> float:
        pcm = (np.clip(resample(audio, sample_rate, DEVICE_RATE), -1, 1) * 32767).astype(np.int16)
        with self._lock:
            ahead = self._queued_samples / DEVICE_RATE
            self._playback.append(pcm)
            self._queued_samples += len(pcm)
        latency = self._stream.latency[1] if self._stream else 0.0
        return self.now() + ahead + latency

    def stop(self) -> None:
        with self._lock:
            self._playback.clear()
            self._queued_samples = 0

    def _pull(self, n: int) -> np.ndarray:
        out = np.zeros(n, dtype=np.int16)
        filled = 0
        with self._lock:
            while filled < n and self._playback:
                head = self._playback[0]
                take = min(n - filled, len(head))
                out[filled : filled + take] = head[:take]
                filled += take
                if take == len(head):
                    self._playback.popleft()
                else:
                    self._playback[0] = head[take:]
            self._queued_samples -= filled
        return out

    def _callback(self, indata, outdata, frames, _time, _status) -> None:
        out = self._pull(frames)
        outdata[:] = out[:, None]
        self._level = float(np.sqrt(np.mean((out / 32768.0) ** 2)))
        self._pairs.put((indata[:, 0].copy(), out))

    def _open(self, devices: tuple[int | None, int | None]):
        import sounddevice as sd

        stream = sd.Stream(
            samplerate=DEVICE_RATE,
            blocksize=FRAME,
            dtype="int16",
            channels=(1, self._out_channels),
            device=devices,
            callback=self._callback,
        )
        stream.start()
        return stream

    def use_mic(self, name: str | None) -> None:
        """Switch microphones while running. On failure the old one keeps working and the error is raised."""
        devices = (find_device(name, "input"), self._devices[1])
        if self._stream is None:
            self._devices = devices
            return
        self._stream.stop()
        self._stream.close()
        try:
            self._stream = self._open(devices)
        except Exception:
            self._stream = self._open(self._devices)
            raise
        self._devices = devices

    async def frames(self) -> AsyncIterator[np.ndarray]:
        loop = asyncio.get_running_loop()
        mic: asyncio.Queue[np.ndarray] = asyncio.Queue()
        worker = threading.Thread(target=self._process, args=(loop, mic), daemon=True)
        worker.start()
        self._stream = self._open(self._devices)
        try:
            while True:
                yield await mic.get()
        finally:
            self._stream.stop()
            self._stream.close()
            self._pairs.put(None)

    def _process(self, loop: asyncio.AbstractEventLoop, mic: asyncio.Queue) -> None:
        from livekit import rtc

        apm = rtc.AudioProcessingModule(echo_cancellation=self._echo_cancellation, noise_suppression=True, high_pass_filter=True)
        down = _Downsampler()
        while (pair := self._pairs.get()) is not None:
            near, far = pair
            apm.process_reverse_stream(rtc.AudioFrame(far.tobytes(), DEVICE_RATE, 1, FRAME))
            frame = rtc.AudioFrame(near.tobytes(), DEVICE_RATE, 1, FRAME)
            apm.process_stream(frame)
            clean = np.frombuffer(frame.data, dtype=np.int16).astype(np.float32) / 32768.0
            loop.call_soon_threadsafe(mic.put_nowait, down(clean))

