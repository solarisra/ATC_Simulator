import queue
import unittest
from unittest.mock import Mock, patch

from Locations.Yuma.Scenarios.yuma import create_yuma_scenario
from simulator.display.radar import RadarDisplay
from simulator.radio.communications import CommunicationsPanel
from simulator.radio.voice_commands import handle_transmission


class VoiceCommandTests(unittest.TestCase):
    def setUp(self):
        aircraft_list, self.facility, self.strips = create_yuma_scenario()
        self.aircraft = aircraft_list.aircraft_list
        self.by_id = {aircraft.id: aircraft for aircraft in self.aircraft}

    def test_scenario_assigns_role_and_band(self):
        self.assertEqual(self.by_id["A1"].radio_channel, "enroute_low")
        self.assertEqual(self.by_id["A3"].radio_channel, "enroute_high")
        self.assertEqual(self.by_id["A7"].radio_channel, "approach_low")
        self.assertEqual(self.by_id["A8"].radio_channel, "departure_low")
        self.assertEqual(self.by_id["A11"].radio_channel, "departure_high")
        self.assertEqual(self.by_id["A12"].radio_channel, "approach_high")

    def test_callsign_heading_and_altitude_clearances(self):
        aircraft = self.by_id["A3"]
        reply = handle_transmission(
            "Devil 279 or fly. Heading 270.",
            self.aircraft,
            self.facility,
            {"enroute_high"},
        )
        self.assertEqual(aircraft.flight_guidance.vector_heading, 270)
        self.assertEqual(reply.channel, "enroute_high")
        self.assertIn("two seven zero", reply.text)
        handle_transmission(
            "Devil 279er fly heading 275",
            self.aircraft,
            self.facility,
            {"enroute_high"},
        )
        self.assertEqual(aircraft.flight_guidance.vector_heading, 275)
        handle_transmission(
            "Devil 279 climb and maintain one three thousand",
            self.aircraft,
            self.facility,
            {"enroute_high"},
        )
        self.assertEqual(aircraft.flight_guidance.assigned_altitude, 13000)
        handle_transmission(
            "Devil 279 resume filed altitude",
            self.aircraft,
            self.facility,
            {"enroute_high"},
        )
        self.assertIsNone(aircraft.flight_guidance.assigned_altitude)

    def test_callsign_and_frequency_are_required(self):
        aircraft = self.by_id["A1"]
        for text, channels in (
            ("heading 180", {"enroute_low"}),
            ("November one three five tango charlie heading 180", {"approach_low"}),
            (
                "November one three five tango charlie turn left then heading 180",
                {"enroute_low"},
            ),
            (
                "November one three five tango charlie maintain 9 or 500",
                {"enroute_low"},
            ),
        ):
            with self.subTest(text=text), self.assertRaises(ValueError):
                handle_transmission(text, self.aircraft, self.facility, channels)
            self.assertIsNone(aircraft.flight_guidance.vector_heading)
        handle_transmission(
            "November one three five tango charlie heading one eight zero",
            self.aircraft,
            self.facility,
            {"enroute_low"},
        )
        self.assertEqual(aircraft.flight_guidance.vector_heading, 180)

    def test_directional_turns_follow_the_requested_direction_and_stop(self):
        aircraft = self.by_id["A1"]
        for direction, initial, target, halfway in (
            ("right", 10, 350, 310),
            ("left", 350, 10, 50),
        ):
            with self.subTest(direction=direction):
                aircraft.heading = initial
                reply = handle_transmission(
                    f"N135TC turn {direction} heading {target}",
                    self.aircraft,
                    self.facility,
                    {"enroute_low"},
                )
                self.assertIn(f"Turn {direction}", reply.text)
                aircraft.update_position(100)
                self.assertAlmostEqual(aircraft.heading, halfway)
                aircraft.update_position(20)
                self.assertAlmostEqual(aircraft.heading, target)
                self.assertIsNone(aircraft.flight_guidance.vector_turn_direction)
                aircraft.update_position(5)
                self.assertAlmostEqual(aircraft.heading, target)

    def test_directional_heading_accepts_separated_callsign_and_hyphenated_digits(self):
        aircraft = self.by_id["A1"]
        aircraft.heading = 350
        reply = handle_transmission(
            "N 135 T C turn right heading 0-1-0",
            self.aircraft,
            self.facility,
            {"enroute_low"},
        )
        self.assertIn("Turn right, heading zero one zero true", reply.text)
        aircraft.update_position(1)
        self.assertGreater(aircraft.heading, 350)

    def test_turn_direction_cannot_be_applied_to_another_clearance(self):
        aircraft = self.by_id["A1"]
        with self.assertRaises(ValueError):
            handle_transmission(
                "N135TC turn right direct BZA",
                self.aircraft,
                self.facility,
                {"enroute_low"},
            )
        self.assertIsNone(aircraft.flight_guidance.vector_heading)

    def test_observed_whisper_variants_for_heading_and_climb(self):
        aircraft = self.by_id["A1"]
        aircraft.heading = 350
        reply = handle_transmission(
            "November 1 3 5 Tango Charlie turn right hitting 0 1 0",
            self.aircraft,
            self.facility,
            {"enroute_low"},
        )
        self.assertIn("Turn right, heading zero one zero", reply.text)
        aircraft.update_position(1)
        self.assertGreater(aircraft.heading, 350)
        reply = handle_transmission(
            "November 1 3 5 Tango Charlie climbed to 7,500",
            self.aircraft,
            self.facility,
            {"enroute_low"},
        )
        self.assertEqual(aircraft.flight_guidance.assigned_altitude, 7500)
        self.assertIn("7500 feet", reply.text)
        altitude = aircraft.altitude
        aircraft.update_position(10)
        self.assertGreater(aircraft.altitude, altitude)
        with self.assertRaises(ValueError):
            handle_transmission(
                "November 1 3 5 Tango Charlie hitting 010 climbed to 7500",
                self.aircraft,
                self.facility,
                {"enroute_low"},
            )

    def test_turned_transcription_preserves_turn_direction(self):
        aircraft = self.by_id["A1"]
        aircraft.heading = 350
        reply = handle_transmission(
            "November 1 3 5 Tango Charlie turned right hitting 0 1 0",
            self.aircraft,
            self.facility,
            {"enroute_low"},
        )
        self.assertIn("Turn right, heading zero one zero", reply.text)
        aircraft.update_position(1)
        self.assertGreater(aircraft.heading, 350)

    def test_advisory_with_transcribed_clearance_is_rejected(self):
        aircraft = self.by_id["A1"]
        for instruction in ("turned right heading 010", "climbed to 7500"):
            with (
                self.subTest(instruction=instruction),
                self.assertRaisesRegex(ValueError, "separately"),
            ):
                handle_transmission(
                    f"N135TC radar contact {instruction}",
                    self.aircraft,
                    self.facility,
                    {"enroute_low"},
                )
        self.assertIsNone(aircraft.flight_guidance.vector_heading)
        self.assertIsNone(aircraft.flight_guidance.assigned_altitude)

    def test_voice_direct_resume_and_control_limits(self):
        aircraft = self.by_id["A3"]
        route = aircraft.flight_guidance.route
        fix = route[aircraft.flight_guidance.next_index + 1].name
        handle_transmission(
            f"Devil 279 direct {fix}", self.aircraft, self.facility, {"enroute_high"}
        )
        self.assertEqual(
            aircraft.flight_guidance.route[aircraft.flight_guidance.next_index].name,
            fix,
        )
        handle_transmission(
            "Devil 279 heading 90", self.aircraft, self.facility, {"enroute_high"}
        )
        handle_transmission(
            "Devil 279 resume route", self.aircraft, self.facility, {"enroute_high"}
        )
        self.assertIsNone(aircraft.flight_guidance.vector_heading)
        with self.assertRaisesRegex(ValueError, "above Yuma control limit"):
            handle_transmission(
                "Devil 279 maintain flight level two four zero",
                self.aircraft,
                self.facility,
                {"enroute_high"},
            )
        self.assertIsNone(aircraft.flight_guidance.assigned_altitude)

    def test_traffic_and_radar_contact_calls(self):
        advisory = handle_transmission(
            "Devil 279 traffic twelve o'clock five miles",
            self.aircraft,
            self.facility,
            {"enroute_high"},
        )
        self.assertIn("Looking for traffic", advisory.text)
        report = handle_transmission(
            "Devil 279 say traffic", self.aircraft, self.facility, {"enroute_high"}
        )
        self.assertIn("Nearest traffic", report.text)
        radar = handle_transmission(
            "Devil 279 radar contact bearing 240 altitude 13000 speed 400",
            self.aircraft,
            self.facility,
            {"enroute_high"},
        )
        self.assertIn("Radar contact, roger", radar.text)
        with self.assertRaisesRegex(ValueError, "separately"):
            handle_transmission(
                "Devil 279 radar contact turn heading 270",
                self.aircraft,
                self.facility,
                {"enroute_high"},
            )
        self.assertIsNone(self.by_id["A3"].flight_guidance.vector_heading)

    def test_transcribed_clearance_is_applied_and_queued_for_readback(self):
        display = Mock(spec=RadarDisplay)
        with patch("simulator.radio.communications.arcade.Text"):
            display.communications_panel = CommunicationsPanel()
        display.aircraft_list = Mock(aircraft_list=self.aircraft)
        display.atc_facility = self.facility
        display.voice_audio = Mock(events=queue.SimpleQueue())
        display.voice_audio.events.put(
            ("transcript", ("Devil 279 or fly heading 270", {"enroute_high"}))
        )
        RadarDisplay.process_voice(display)
        self.assertEqual(self.by_id["A3"].flight_guidance.vector_heading, 270)
        reply = display.voice_audio.speak.call_args.args[0]
        self.assertEqual(reply.aircraft_id, "A3")
        self.assertEqual(reply.channel, "enroute_high")

    def test_rejection_logs_the_recognized_transcript(self):
        display = Mock(spec=RadarDisplay)
        with patch("simulator.radio.communications.arcade.Text"):
            display.communications_panel = CommunicationsPanel()
        display.aircraft_list = Mock(aircraft_list=self.aircraft)
        display.atc_facility = self.facility
        display.voice_audio = Mock(events=queue.SimpleQueue())
        display.voice_audio.events.put(
            ("transcript", ("Unrecognized callsign heading 010", {"enroute_low"}))
        )
        with self.assertLogs("simulator.display.radar", level="WARNING") as logs:
            RadarDisplay.process_voice(display)
        self.assertIn("Unrecognized callsign heading 010", logs.output[0])
        self.assertIn("unambiguous aircraft callsign", logs.output[0])
        display.voice_audio.speak.assert_not_called()


if __name__ == "__main__":
    unittest.main()
