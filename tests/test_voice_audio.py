import queue
import threading
import unittest
from unittest.mock import Mock

import numpy as np

from Locations.Yuma.Scenarios.yuma import create_yuma_scenario
from simulator.radio.voice_audio import (
    MAX_RECORDING_SECONDS,
    PILOT_VOICES,
    SAMPLE_RATE,
    VoiceAudio,
    VoiceCapture,
)


class VoiceCaptureTests(unittest.TestCase):
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
        voice = VoiceAudio.__new__(VoiceAudio)
        voice._pilot_voices = {}
        assigned = {
            aircraft.id: voice._pilot_voice(aircraft.id)
            for aircraft in aircraft_list.aircraft_list
        }
        self.assertEqual(len(set(assigned.values())), len(assigned))
        for aircraft_id, selected_voice in reversed(list(assigned.items())):
            self.assertEqual(voice._pilot_voice(aircraft_id), selected_voice)

    def test_voice_reuse_is_reported_when_presets_are_exhausted(self):
        voice = VoiceAudio.__new__(VoiceAudio)
        voice._pilot_voices = {}
        for index in range(len(PILOT_VOICES)):
            voice._pilot_voice(str(index))
        with self.assertLogs("simulator.radio.voice_audio", level="WARNING") as logs:
            reused = voice._pilot_voice("additional")
        self.assertEqual(reused, voice._pilot_voices["0"])
        self.assertIn("reusing voice presets", logs.output[0])


if __name__ == "__main__":
    unittest.main()
