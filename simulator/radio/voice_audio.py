"""Local, asynchronous push-to-talk recording and speech processing."""

import logging
import os
import queue
import random
import re
import threading
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16000
MAX_RECORDING_SECONDS = 60
PILOT_VOICES = (
    "am_adam",
    "af_heart",
    "am_michael",
    "af_bella",
    "am_echo",
    "af_nicole",
    "am_eric",
    "af_sarah",
    "am_fenrir",
    "af_sky",
    "am_liam",
    "af_nova",
    "am_onyx",
    "af_jessica",
    "am_puck",
    "af_kore",
    "am_santa",
    "af_aoede",
    "af_alloy",
    "af_river",
)


def assign_pilot_voices(aircraft):
    counts = Counter(
        plane.pilot_voice for plane in aircraft if plane.pilot_voice is not None
    )
    if any(voice not in PILOT_VOICES for voice in counts):
        raise ValueError("Unknown pilot voice")
    unassigned = [plane for plane in aircraft if plane.pilot_voice is None]
    if not unassigned:
        return
    voices = list(PILOT_VOICES)
    random.SystemRandom().shuffle(voices)
    reused = False
    for plane in unassigned:
        voice = min(voices, key=lambda candidate: counts[candidate])
        reused = reused or counts[voice] > 0
        plane.pilot_voice = voice
        counts[voice] += 1
    if reused:
        logging.getLogger(__name__).warning(
            "More aircraft than distinct pilot voices; reusing voice presets"
        )


def _speech_text(text: str) -> str:
    # Misaki otherwise mispronounces the city name; its inline markup supplies phonemes.
    return re.sub(
        r"\bLos Angeles\b",
        lambda match: (
            f"[{match.group()}](/l\u0254s \u02c8\u00e6n\u02a4\u0259l\u0259s/)"
        ),
        text,
        flags=re.IGNORECASE,
    )


@dataclass(frozen=True)
class CaptureResult:
    channels: frozenset[str]
    samples: np.ndarray | None
    error: str | None = None


class VoiceCapture:
    def __init__(self):
        self._lock = threading.Lock()
        self._active = False
        self._channels = frozenset()
        self._chunks = []
        self._frames = 0
        self._error = None

    def feed(self, samples, status=None):
        with self._lock:
            if not self._active or not self._channels or self._error:
                return
            if status:
                self._error = f"Microphone input error: {status}"
                self._chunks.clear()
            elif self._frames + len(samples) > SAMPLE_RATE * MAX_RECORDING_SECONDS:
                self._error = f"Transmission exceeded {MAX_RECORDING_SECONDS} seconds"
                self._chunks.clear()
            else:
                self._chunks.append(samples.copy().reshape(-1))
                self._frames += len(samples)

    def switch(self, active, channels):
        channels = frozenset(channels)
        with self._lock:
            if active and not self._active:
                self._active = True
                self._channels = channels
                return None
            if active and self._active:
                self._channels = self._channels.intersection(channels)
                if not self._channels:
                    self._chunks.clear()
                return None
            if not self._active:
                return None
            old_channels, chunks, error = self._channels, self._chunks, self._error
            self._active = False
            self._channels = frozenset()
            self._chunks = []
            self._frames = 0
            self._error = None
        if not old_channels and not error:
            error = "No frequency remained On for the entire transmission"
        samples = np.concatenate(chunks) if chunks else None
        return CaptureResult(old_channels, samples, error)


class VoiceAudio:
    def __init__(self):
        self.events = queue.SimpleQueue()
        self._jobs = queue.Queue(maxsize=8)
        self._capture = VoiceCapture()
        self._condition = threading.Condition()
        self._ready = False
        self._closed = False
        self._hot = False
        self._monitored = frozenset()
        self._playing = False
        self._playing_channel: str | None = None
        self._sounddevice = None
        self._generation = 0
        self._thread = threading.Thread(
            target=self._run, name="voice-audio", daemon=True
        )
        self._thread.start()

    def _submit(self, job):
        with self._condition:
            try:
                self._jobs.put_nowait((self._generation, job))
            except queue.Full:
                self.events.put(
                    ("error", "Voice processing is busy; transmission dropped")
                )

    @property
    def ready(self):
        with self._condition:
            return self._ready and not self._closed

    @property
    def playing_channel(self):
        with self._condition:
            return self._playing_channel

    def _post_job_event(self, generation, event):
        with self._condition:
            if generation == self._generation and not self._closed:
                self.events.put(event)

    def discard_transmissions(self):
        with self._condition:
            self._generation += 1
            self._hot = False
            self._capture.switch(False, ())
            if self._playing:
                if self._sounddevice is None:
                    raise RuntimeError("Audio playback has no device")
                self._sounddevice.stop()
                self._playing_channel = None
            while True:
                try:
                    job = self._jobs.get_nowait()
                except queue.Empty:
                    break
                if job is None:
                    self._jobs.put_nowait(None)
                    break
            errors = []
            while True:
                try:
                    event = self.events.get_nowait()
                except queue.Empty:
                    break
                if event[0] == "error":
                    errors.append(event)
            for event in errors:
                self.events.put(event)
            self._condition.notify_all()

    def sync(self, hot, transmitting, monitored):
        with self._condition:
            was_hot = self._hot
            self._hot = hot
            self._monitored = frozenset(monitored)
            if (
                self._playing
                and self._playing_channel is not None
                and (hot or self._playing_channel not in self._monitored)
            ):
                if self._sounddevice is None:
                    raise RuntimeError("Audio playback has no device")
                self._sounddevice.stop()
                self._playing_channel = None
            self._condition.notify_all()
            ready = self._ready and not self._closed
        result = self._capture.switch(hot and ready, transmitting)
        if result is not None:
            if not ready:
                self.events.put(("error", "Voice stopped; transmission discarded"))
            elif result.error:
                self.events.put(("error", result.error))
            elif result.samples is None or not len(result.samples):
                self.events.put(("error", "No microphone audio was captured"))
            else:
                self._submit(("transcribe", result))
        if hot and not was_hot:
            if not ready:
                self.events.put(("error", "Voice is not ready"))
            elif not transmitting:
                self.events.put(("error", "No radio frequency is On"))

    def speak(self, reply):
        if reply.pilot_voice not in PILOT_VOICES:
            raise ValueError(f"No valid pilot voice assigned to {reply.aircraft_id}")
        self._submit(("speak", reply))

    def _callback(self, indata, frames, time_info, status):
        self._capture.feed(indata, status)

    def _run(self):
        stream = None
        dll_directory = None
        try:
            import sounddevice as sd
            import torch

            device = "cuda" if torch.cuda.is_available() else "cpu"
            if device == "cpu":
                self.events.put(("status", "Warning: Using CPU (slower). NVIDIA GPU recommended for better performance"))
            if os.name == "nt":
                dll_directory = os.add_dll_directory(
                    str(Path(torch.__file__).parent / "lib")
                )
            from faster_whisper import WhisperModel
            from kokoro import KPipeline
            from misaki.espeak import EspeakFallback

            self.events.put(("status", "Loading speech models"))
            EspeakFallback(british=False)
            compute_type = "float16" if device == "cuda" else "float32"
            whisper = WhisperModel("small.en", device=device, compute_type=compute_type)
            kokoro = KPipeline(
                lang_code="a", repo_id="hexgrad/Kokoro-82M", device=device
            )
            for index, pilot_voice in enumerate(PILOT_VOICES, start=1):
                with self._condition:
                    if self._closed:
                        return
                self.events.put(
                    ("status", f"Loading pilot voices {index}/{len(PILOT_VOICES)}")
                )
                kokoro.load_voice(pilot_voice)
            stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                callback=self._callback,
            )
            stream.start()
            with self._condition:
                self._sounddevice = sd
                self._ready = True
            self.events.put(("status", "Voice ready"))
            while True:
                with self._condition:
                    if self._closed:
                        break
                try:
                    job = self._jobs.get(timeout=0.25)
                except queue.Empty:
                    continue
                if job is None:
                    break
                generation, (kind, item) = job
                with self._condition:
                    if generation != self._generation:
                        continue
                if kind == "transcribe":
                    if np.max(np.abs(item.samples)) < 0.001:
                        self._post_job_event(
                            generation, ("error", "No speech detected")
                        )
                        continue
                    self._post_job_event(generation, ("status", "Transcribing"))
                    segments, _ = whisper.transcribe(
                        item.samples,
                        language="en",
                        beam_size=5,
                        condition_on_previous_text=False,
                    )
                    text = " ".join(
                        segment.text.strip() for segment in segments
                    ).strip()
                    if text:
                        self._post_job_event(
                            generation, ("transcript", (text, item.channels))
                        )
                    else:
                        self._post_job_event(
                            generation, ("error", "No speech recognized")
                        )
                elif kind == "speak":
                    self._post_job_event(
                        generation, ("status", "Generating pilot reply")
                    )
                    chunks = []
                    for result in kokoro(
                        _speech_text(item.text),
                        voice=item.pilot_voice,
                    ):
                        audio = result.audio
                        if audio is None:
                            raise RuntimeError("Kokoro produced no audio")
                        chunks.append(audio.cpu().numpy())
                    if not chunks:
                        raise RuntimeError("Kokoro produced no audio")
                    with self._condition:
                        self._condition.wait_for(
                            lambda generation=generation: (
                                not self._hot
                                or self._closed
                                or generation != self._generation
                            )
                        )
                        if self._closed:
                            break
                        if generation != self._generation:
                            continue
                        if item.channel not in self._monitored:
                            self.events.put(("status", "Pilot reply not monitored"))
                            continue
                        sd.play(np.concatenate(chunks), 24000, blocking=False)
                        self._playing = True
                        self._playing_channel = item.channel
                    try:
                        sd.wait()
                    finally:
                        with self._condition:
                            self._playing = False
                            self._playing_channel = None
                    self._post_job_event(generation, ("status", "Voice ready"))
        except Exception as error:
            logging.getLogger(__name__).exception("Voice audio failed")
            self.events.put(("error", f"Voice audio failed: {error}"))
        finally:
            with self._condition:
                self._ready = False
            if stream is not None:
                stream.close()
            if dll_directory is not None:
                dll_directory.close()

    def close(self):
        with self._condition:
            if self._closed:
                return
            self._closed = True
            if self._playing:
                if self._sounddevice is None:
                    raise RuntimeError("Audio playback has no device")
                self._sounddevice.stop()
                self._playing_channel = None
            self._condition.notify_all()
        self._capture.switch(False, ())
        try:
            self._jobs.put_nowait(None)
        except queue.Full:
            logging.getLogger(__name__).warning("Voice queue is full during shutdown")
        self._thread.join(timeout=1)
        if self._thread.is_alive():
            logging.getLogger(__name__).warning("Voice worker is still shutting down")
