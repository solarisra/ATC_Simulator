import importlib.util
import queue
import random
import sys
import threading
import types
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

from locations.Yuma.Scenarios.yuma import create_yuma_scenario
from simulator.radio.voice_audio import (
    MAX_RECORDING_SECONDS,
    PILOT_VOICES,
    SAMPLE_RATE,
    VoiceAudio,
    VoiceCapture,
    _speech_text,
    assign_pilot_voices,
)
from simulator.radio.voice_commands import PilotReply


class VoiceCaptureTests(unittest.TestCase):
    def test_pronunciation_override_only_changes_matching_speech_text(self):
        reply = PilotReply(
            "A1",
            "enroute_low",
            "Contact Los Angeles Center. Verify LOS ANGELES Center, not Albuquerque.",
        )
        speech = _speech_text(reply.text)
        self.assertIn("[Los Angeles](/", speech)
        self.assertIn("[LOS ANGELES](/", speech)
        self.assertIn("not Albuquerque.", speech)
        self.assertEqual(
            reply.text,
            "Contact Los Angeles Center. Verify LOS ANGELES Center, not Albuquerque.",
        )
        self.assertEqual(
            _speech_text("Los AngelesX and EastLos Angeles"),
            "Los AngelesX and EastLos Angeles",
        )

    def test_voice_initialization_does_not_load_unused_pilot_voices(self):
        audio = VoiceAudio.__new__(VoiceAudio)
        audio.events = queue.SimpleQueue()
        audio._jobs = queue.Queue()
        audio._jobs.put(None)
        audio._condition = threading.Condition()
        audio._closed = False
        audio._ready = False
        audio._sounddevice = None

        stream = Mock()
        sounddevice = types.ModuleType("sounddevice")
        sounddevice.InputStream = Mock(return_value=stream)
        kokoro_pipeline = Mock()
        kokoro_module = types.ModuleType("kokoro")
        kokoro_module.KPipeline = Mock(return_value=kokoro_pipeline)
        faster_whisper = types.ModuleType("faster_whisper")
        faster_whisper.WhisperModel = Mock()
        misaki = types.ModuleType("misaki")
        misaki.__path__ = []
        espeak = types.ModuleType("misaki.espeak")
        espeak.EspeakFallback = Mock()

        with (
            patch.dict(
                sys.modules,
                {
                    "sounddevice": sounddevice,
                    "faster_whisper": faster_whisper,
                    "kokoro": kokoro_module,
                    "misaki": misaki,
                    "misaki.espeak": espeak,
                },
            ),
            patch("torch.cuda.is_available", return_value=True),
            patch("simulator.radio.voice_audio.os.add_dll_directory", create=True),
        ):
            audio._run()

        kokoro_pipeline.load_voice.assert_not_called()
        statuses = []
        while not audio.events.empty():
            statuses.append(audio.events.get_nowait())
        self.assertIn(
            ("status", "Voice ready"),
            statuses,
        )

    @unittest.skipUnless(
        importlib.util.find_spec("kokoro") is not None
        and importlib.util.find_spec("en_core_web_sm") is not None,
        "Optional voice dependencies are not installed",
    )
    def test_kokoro_pronounces_centers_and_preserves_reply_text(self):
        from kokoro import KPipeline

        pipeline = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M", model=False)
        text = "Contact Los Angeles Center. Verify Albuquerque Center."
        original = next(pipeline(text))
        corrected = next(pipeline(_speech_text(text)))
        self.assertEqual(corrected.graphemes, text)
        self.assertIn("l\u0254s \u02c8\u00e6n\u02a4\u0259l\u0259s", corrected.phonemes)
        original_tokens = original.tokens
        corrected_tokens = corrected.tokens
        if original_tokens is None or corrected_tokens is None:
            self.fail("Kokoro did not return pronunciation tokens")
        original_albuquerque = next(
            token.phonemes for token in original_tokens if token.text == "Albuquerque"
        )
        corrected_albuquerque = next(
            token.phonemes for token in corrected_tokens if token.text == "Albuquerque"
        )
        self.assertEqual(
            original_albuquerque, "\u02c8\u00e6lb\u0259k\u02cc\u025c\u0279ki"
        )
        self.assertEqual(corrected_albuquerque, original_albuquerque)
        for city, expected in (
            ("Seattle", "si\u02c8\u00e6T\u1d4al"),
            ("San Francisco", "s\u02c8\u00e6n f\u0279\u00e6ns\u02c8\u026askO"),
        ):
            with self.subTest(city=city):
                phrase = f"Contact {city} Center."
                result = next(pipeline(_speech_text(phrase)))
                self.assertEqual(result.graphemes, phrase)
                self.assertIn(expected, result.phonemes)

    def test_capture_requires_a_channel_on_for_the_entire_transmission(self):
        capture = VoiceCapture()
        capture.feed(np.array([[0.5]], dtype=np.float32))
        self.assertIsNone(capture.switch(True, {"approach_low", "departure_high"}))
        first = np.array([[0.1], [0.2]], dtype=np.float32)
        capture.feed(first)
        first[:] = 0
        self.assertIsNone(capture.switch(True, {"departure_high", "enroute_high"}))
        capture.feed(np.array([[0.3]], dtype=np.float32))
        result = capture.switch(False, ())
        self.assertEqual(result.channels, frozenset({"departure_high"}))
        np.testing.assert_array_almost_equal(result.samples, [0.1, 0.2, 0.3])
        self.assertIsNone(capture.switch(False, ()))

        capture.switch(True, {"approach_low"})
        capture.feed(np.array([[0.4]], dtype=np.float32))
        capture.switch(True, {"enroute_high"})
        result = capture.switch(False, ())
        self.assertIsNone(result.samples)
        self.assertIn("entire transmission", result.error)

    def test_audio_errors_and_overlong_transmissions_are_not_submitted(self):
        capture = VoiceCapture()
        capture.switch(True, {"approach_low"})
        capture.feed(np.zeros((1, 1), dtype=np.float32), "input overflow")
        result = capture.switch(False, ())
        self.assertIsNone(result.samples)
        self.assertIn("input overflow", result.error)
        capture.switch(True, {"approach_low"})
        capture.feed(np.zeros((SAMPLE_RATE * MAX_RECORDING_SECONDS + 1, 1)))
        result = capture.switch(False, ())
        self.assertIsNone(result.samples)
        self.assertIn("exceeded", result.error)

    def test_replacement_discards_pending_and_late_transcripts(self):
        voice = VoiceAudio.__new__(VoiceAudio)
        voice.events = queue.SimpleQueue()
        voice._jobs = queue.Queue()
        voice._jobs.put((0, ("transcribe", "old audio")))
        voice._condition = threading.Condition()
        voice._generation = 0
        voice._closed = False
        voice._hot = True
        voice._playing = False
        voice._capture = VoiceCapture()
        voice._capture.switch(True, {"enroute_low"})
        voice._capture.feed(np.array([[0.5]], dtype=np.float32))
        voice.events.put(("transcript", ("old", {"enroute_low"})))
        voice.events.put(("error", "Microphone failed"))
        voice.discard_transmissions()
        voice._post_job_event(0, ("transcript", ("late", {"enroute_low"})))
        self.assertEqual(voice.events.get_nowait(), ("error", "Microphone failed"))
        self.assertTrue(voice.events.empty())
        self.assertTrue(voice._jobs.empty())
        self.assertIsNone(voice._capture.switch(False, ()))
        voice._post_job_event(1, ("transcript", ("new", {"enroute_low"})))
        self.assertEqual(voice.events.get_nowait()[1][0], "new")

    def test_playback_channel_clears_when_unmonitored_or_interrupted(self):
        voice = VoiceAudio.__new__(VoiceAudio)
        voice.events = queue.SimpleQueue()
        voice._condition = threading.Condition()
        voice._capture = Mock()
        voice._capture.switch.return_value = None
        voice._ready = True
        voice._closed = False
        voice._hot = False
        voice._playing = True
        voice._playing_channel = "enroute_low"
        voice._sounddevice = Mock()

        voice.sync(False, (), {"enroute_low"})
        self.assertEqual(voice.playing_channel, "enroute_low")
        voice._sounddevice.stop.assert_not_called()
        voice.sync(False, (), ())
        self.assertIsNone(voice.playing_channel)
        voice._sounddevice.stop.assert_called_once()

        voice._playing_channel = "approach_low"
        voice.sync(True, {"approach_low"}, {"approach_low"})
        self.assertIsNone(voice.playing_channel)
        self.assertEqual(voice._sounddevice.stop.call_count, 2)

    def test_pilot_voice_is_distinct_and_stable_for_each_scenario_aircraft(self):
        aircraft_list, _, _ = create_yuma_scenario()
        other_aircraft, _, _ = create_yuma_scenario()
        with patch(
            "simulator.radio.voice_audio.random.SystemRandom",
            side_effect=(random.Random(1), random.Random(2)),
        ):
            assign_pilot_voices(aircraft_list.aircraft_list)
            assign_pilot_voices(other_aircraft.aircraft_list)
        assigned = {
            aircraft.id: aircraft.pilot_voice
            for aircraft in aircraft_list.aircraft_list
        }
        self.assertEqual(len(set(assigned.values())), len(assigned))
        self.assertNotEqual(
            list(assigned.values()),
            [aircraft.pilot_voice for aircraft in other_aircraft.aircraft_list],
        )
        assign_pilot_voices(list(reversed(aircraft_list.aircraft_list)))
        self.assertEqual(
            assigned,
            {
                aircraft.id: aircraft.pilot_voice
                for aircraft in aircraft_list.aircraft_list
            },
        )

    def test_voice_reuse_is_reported_when_presets_are_exhausted(self):
        planes = [
            SimpleNamespace(pilot_voice=None) for _ in range(len(PILOT_VOICES) + 1)
        ]
        with self.assertLogs("simulator.radio.voice_audio", level="WARNING") as logs:
            assign_pilot_voices(planes)
        self.assertEqual(
            len({plane.pilot_voice for plane in planes}), len(PILOT_VOICES)
        )
        self.assertIn("reusing voice presets", logs.output[0])

    def test_speak_requires_and_queues_the_assigned_voice(self):
        voice = VoiceAudio.__new__(VoiceAudio)
        voice._submit = Mock()
        with self.assertRaisesRegex(ValueError, "No valid pilot voice"):
            voice.speak(PilotReply("A1", "enroute_low", "Ident."))
        reply = PilotReply("A1", "enroute_low", "Ident.", PILOT_VOICES[9])
        voice.speak(reply)
        voice._submit.assert_called_once_with(("speak", reply))


if __name__ == "__main__":
    unittest.main()
