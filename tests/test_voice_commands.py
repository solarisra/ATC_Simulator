import queue
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import arcade

from Locations.Yuma.Scenarios.yuma import create_yuma_scenario
from simulator.core.aircraft_models import boeing_767_freighter, cessna_172
from simulator.core.atc import CoordinationKind, TrackingPosition, TrackOwnership
from simulator.display.radar import RadarDisplay, RadarReturnManager, RadarSweep
from simulator.radio.communications import CommunicationsPanel
from simulator.radio.voice_commands import handle_transmission


class VoiceCommandTests(unittest.TestCase):
    def setUp(self):
        aircraft_list, self.facility, self.strips = create_yuma_scenario()
        self.aircraft = aircraft_list.aircraft_list
        self.by_id = {aircraft.id: aircraft for aircraft in self.aircraft}
        track = self.by_id["A3"].track
        track.offer(TrackingPosition.YUMA)
        track.accept(TrackingPosition.YUMA)
        track.transfer_communications()
        track.confirm_identification()

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
        self.assertAlmostEqual(aircraft.flight_guidance.vector_heading, 280 + 14 / 60)
        self.assertEqual(reply.channel, "enroute_high")
        self.assertIn("two seven zero", reply.text)
        handle_transmission(
            "Devil 279er fly heading 275",
            self.aircraft,
            self.facility,
            {"enroute_high"},
        )
        self.assertAlmostEqual(aircraft.flight_guidance.vector_heading, 285 + 14 / 60)
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

    def test_correction_replaces_values_and_entire_instructions(self):
        aircraft = self.by_id["A3"]
        reply = handle_transmission(
            "Devil 279 turn right heading 270 correction 280",
            self.aircraft,
            self.facility,
            {"enroute_high"},
        )
        self.assertAlmostEqual(aircraft.flight_guidance.vector_heading, 290 + 14 / 60)
        self.assertIn("turn right, heading two eight zero", reply.text.lower())
        handle_transmission(
            "Devil 279 climb and maintain 5000 correction 6000",
            self.aircraft,
            self.facility,
            {"enroute_high"},
        )
        self.assertEqual(aircraft.flight_guidance.assigned_altitude, 6000)
        handle_transmission(
            "Devil 279 maintain two thousand correction five thousand",
            self.aircraft,
            self.facility,
            {"enroute_high"},
        )
        self.assertEqual(aircraft.flight_guidance.assigned_altitude, 5000)
        handle_transmission(
            "Devil 279 maintain flight level 90 correction 100",
            self.aircraft,
            self.facility,
            {"enroute_high"},
        )
        self.assertEqual(aircraft.flight_guidance.assigned_altitude, 10000)
        fix = aircraft.flight_guidance.route[aircraft.flight_guidance.next_index].name
        handle_transmission(
            f"Devil 279 direct BAD correction {fix}",
            self.aircraft,
            self.facility,
            {"enroute_high"},
        )
        self.assertEqual(
            aircraft.flight_guidance.route[aircraft.flight_guidance.next_index].name,
            fix,
        )
        handle_transmission(
            "Devil 279 maintain bearing two six five correction two eight zero",
            self.aircraft,
            self.facility,
            {"enroute_high"},
        )
        self.assertAlmostEqual(aircraft.flight_guidance.vector_heading, 290 + 14 / 60)
        handle_transmission(
            "Devil 279 squawk 3000 correction 4000 correction 5000",
            self.aircraft,
            self.facility,
            {"enroute_high"},
        )
        self.assertEqual(aircraft.squawk, "5000")
        handle_transmission(
            "Devil 279 heading 270 correction squawk 3000",
            self.aircraft,
            self.facility,
            {"enroute_high"},
        )
        self.assertEqual(aircraft.squawk, "3000")
        self.assertAlmostEqual(aircraft.flight_guidance.vector_heading, 290 + 14 / 60)

    def test_correction_can_replace_a_callsign(self):
        aircraft = self.by_id["A3"]
        for original in ("Devil 278", "N135TC"):
            with self.subTest(original=original):
                reply = handle_transmission(
                    f"{original} correction Devil 279 heading 280",
                    self.aircraft,
                    self.facility,
                    {"enroute_high"},
                )
                self.assertEqual(reply.aircraft_id, aircraft.id)
                self.assertAlmostEqual(
                    aircraft.flight_guidance.vector_heading, 290 + 14 / 60
                )

    def test_correction_replaces_contact_frequency_before_transfer(self):
        aircraft = self.by_id["A1"]
        aircraft.track.offer(TrackingPosition.LOS_ANGELES, "ZLA SECTOR 9")
        self.assertTrue(aircraft.track.advance(3))
        reply = handle_transmission(
            "N135TC contact Los Angeles Center on 292.2 correction 128.6",
            self.aircraft,
            self.facility,
            {"enroute_low"},
        )
        self.assertIn("Contact Los Angeles Center on 128.600", reply.text)
        self.assertEqual(aircraft.radio_channel, "zla9_low")

    def test_invalid_correction_never_executes_original_instruction(self):
        aircraft = self.by_id["A3"]
        original_heading = aircraft.flight_guidance.vector_heading
        for text in (
            "Devil 279 heading 270 correction",
            "Devil 279 heading 270 correction 999",
            "Devil 279 ident correction 280",
            "Devil 279 maintain bearing 265 to Imperial correction 280",
        ):
            with self.subTest(text=text), self.assertRaises(ValueError):
                handle_transmission(text, self.aircraft, self.facility, {"enroute_high"})
            self.assertEqual(aircraft.flight_guidance.vector_heading, original_heading)
            self.assertEqual(aircraft.ident_remaining, 0)

    def test_airline_callsigns_and_heavy_are_recognized_and_spoken(self):
        aircraft = self.by_id["A1"]
        aircraft.aircraft_model = boeing_767_freighter
        for callsign, spoken in (
            ("AAL381", "American 381 heavy"),
            ("AAL381", "American Airlines 381 heavy"),
            ("AAL381", "AAL381H"),
            ("AAL381", "American 381"),
            ("UAL27", "United two seven heavy"),
        ):
            aircraft.callsign = callsign
            with self.subTest(spoken=spoken):
                reply = handle_transmission(
                    f"{spoken} squawk 3000",
                    self.aircraft,
                    self.facility,
                    {"enroute_low"},
                )
                self.assertEqual(reply.aircraft_id, aircraft.id)
                self.assertEqual(aircraft.squawk, "3000")
                self.assertIn(
                    "American" if callsign.startswith("AAL") else "United", reply.text
                )
                self.assertIn("heavy", reply.text.lower())
                self.assertNotIn("hotel", reply.text.lower())
                self.assertEqual(aircraft.callsign, callsign)

    def test_amf_is_addressed_and_spoken_as_am_flight(self):
        aircraft = self.by_id["A1"]
        aircraft.callsign = "AMF123"
        for spoken in ("Am Flight one two three", "AMF123", "AmFlight123", "Am Flight123"):
            with self.subTest(spoken=spoken):
                reply = handle_transmission(
                    f"{spoken} squawk 3000",
                    self.aircraft,
                    self.facility,
                    {"enroute_low"},
                )
                self.assertEqual(reply.aircraft_id, aircraft.id)
                self.assertTrue(reply.text.endswith("Am Flight one two three."))
                self.assertEqual(aircraft.callsign, "AMF123")
        aircraft.aircraft_model = boeing_767_freighter
        reply = handle_transmission(
            "Am Flight 123 heavy ident", self.aircraft, self.facility, {"enroute_low"}
        )
        self.assertTrue(reply.text.endswith("Am Flight one two three heavy."))
        ambiguous = SimpleNamespace(
            callsign="AMFLIGHT123", aircraft_model=cessna_172
        )
        with self.assertRaisesRegex(ValueError, "unambiguous"):
            handle_transmission(
                "Am Flight 123 squawk 3000",
                [aircraft, ambiguous],
                self.facility,
                {"enroute_low"},
            )

    def test_airline_aliases_remain_unambiguous_and_heavy_is_not_for_light_aircraft(
        self,
    ):
        aircraft = self.by_id["A1"]
        aircraft.callsign = "AAL381"
        with self.assertRaises(ValueError):
            handle_transmission(
                "American 381 heavy squawk 3000",
                self.aircraft,
                self.facility,
                {"enroute_low"},
            )
        self.assertEqual(aircraft.squawk, "1200")
        ambiguous = SimpleNamespace(
            callsign="AMERICAN381", aircraft_model=aircraft.aircraft_model
        )
        with self.assertRaisesRegex(ValueError, "unambiguous"):
            handle_transmission(
                "American 381 squawk 3000",
                [aircraft, ambiguous],
                self.facility,
                {"enroute_low"},
            )

    def test_real_h_suffix_is_preserved_and_display_collisions_are_rejected(self):
        aircraft = self.by_id["A1"]
        aircraft.callsign = "N123H"
        reply = handle_transmission(
            "November 123 hotel ident", [aircraft], self.facility, {"enroute_low"}
        )
        self.assertIn("hotel", reply.text.lower())
        self.assertNotIn("heavy", reply.text.lower())
        aircraft.aircraft_model = boeing_767_freighter
        reply = handle_transmission(
            "November 123 hotel heavy ident", [aircraft], self.facility, {"enroute_low"}
        )
        self.assertIn("hotel heavy", reply.text.lower())
        collision = SimpleNamespace(callsign="N123HH", aircraft_model=cessna_172)
        with self.assertRaisesRegex(ValueError, "unambiguous"):
            handle_transmission(
                "November 123 hotel hotel ident",
                [aircraft, collision],
                self.facility,
                {"enroute_low"},
            )

    def test_squawk_changes_transponder_and_reads_back_each_digit(self):
        aircraft = self.by_id["A3"]
        aircraft.callsign = "DEVIL7"
        strip = next(strip for strip in self.strips if strip.aircraft is aircraft)
        original_strip_code = strip.beacon_code
        for text, code, spoken in (
            ("devil seven squawk three zero zero zero", "3000", "three zero zero zero"),
            (
                "double seven squawk three zero zero zero",
                "3000",
                "three zero zero zero",
            ),
            ("double seven squawk zero four two one", "0421", "zero four two one"),
            ("double7 squawk 0000", "0000", "zero zero zero zero"),
            ("devil seven squawk 7700", "7700", "seven seven zero zero"),
        ):
            with self.subTest(text=text):
                reply = handle_transmission(
                    text, self.aircraft, self.facility, {"enroute_high"}
                )
                self.assertEqual(aircraft.squawk, code)
                self.assertIn(spoken, reply.text.lower())
                self.assertEqual(strip.beacon_code, original_strip_code)

    def test_invalid_squawk_and_ambiguous_callsign_do_not_change_transponder(self):
        aircraft = self.by_id["A3"]
        aircraft.callsign = "DEVIL7"
        original = aircraft.squawk
        for text in (
            "devil seven squawk",
            "devil seven squawk three zero zero",
            "devil seven squawk three zero zero eight",
            "devil seven squawk three zero zero zero ident",
            "devil seven squawk ident",
            "devil seven radar contact squawk three zero zero zero",
        ):
            with self.subTest(text=text), self.assertRaises(ValueError):
                handle_transmission(
                    text, self.aircraft, self.facility, {"enroute_high"}
                )
            self.assertEqual(aircraft.squawk, original)
        with self.assertRaisesRegex(ValueError, "unambiguous"):
            handle_transmission(
                "double seven squawk three zero zero zero",
                [
                    aircraft,
                    SimpleNamespace(
                        callsign="DOUBLE7", aircraft_model=aircraft.aircraft_model
                    ),
                ],
                self.facility,
                {"enroute_high"},
            )
        self.assertEqual(aircraft.squawk, original)
        other = self.by_id["A1"]
        other.callsign = "DOUBLE7"
        reply = handle_transmission(
            "double seven squawk three zero zero zero",
            [other],
            self.facility,
            {"enroute_low"},
        )
        self.assertEqual(reply.aircraft_id, other.id)
        self.assertEqual(other.squawk, "3000")
        self.assertEqual(aircraft.squawk, original)
        with self.assertRaisesRegex(ValueError, "transmitting frequency"):
            handle_transmission(
                "devil seven squawk three zero zero zero",
                self.aircraft,
                self.facility,
                {"approach_low"},
            )
        self.assertEqual(aircraft.squawk, original)
        aircraft.track.owner = TrackingPosition.LOS_ANGELES
        with self.assertRaisesRegex(
            ValueError, "Yuma must own track and communications"
        ):
            handle_transmission(
                "devil seven squawk three zero zero zero",
                self.aircraft,
                self.facility,
                {"enroute_high"},
            )
        self.assertEqual(aircraft.squawk, original)

    def test_squawk_change_reaches_the_secondary_radar_snapshot(self):
        aircraft = self.by_id["A3"]
        display = SimpleNamespace(
            aircraft_list=SimpleNamespace(aircraft_list=[aircraft]),
            atc_facility=self.facility,
            secondary_radar_returns=[],
            departure_checkins=[],
            reported_departures=set(),
            selected_aircraft_id=None,
            sweep=RadarSweep(),
            radar_return_manager=RadarReturnManager(),
            display_type=RadarDisplay.STARS,
            ARTS_IIE=RadarDisplay.ARTS_IIE,
            secondary_update_elapsed=0,
            emergency_flash_elapsed=0,
            calculate_range_and_bearing=lambda lat, lon: (0, 0),
        )
        display.capture_secondary_radar_returns = lambda: (
            RadarDisplay.capture_secondary_radar_returns(display)
        )
        display.capture_secondary_radar_returns()
        previous = display.secondary_radar_returns[0]
        self.assertIn(
            f"{previous.aircraft_type} {previous.squawk}",
            RadarDisplay.secondary_return_layout(previous, 0, 0, 10)[0],
        )
        handle_transmission(
            "devil 279 squawk seven seven zero zero",
            self.aircraft,
            self.facility,
            {"enroute_high"},
        )
        RadarDisplay.on_update(display, 1)
        snapshot = display.secondary_radar_returns[0]
        self.assertEqual(snapshot.squawk, "7700")
        self.assertIn(
            f"{snapshot.aircraft_type} 7700",
            RadarDisplay.secondary_return_layout(snapshot, 0, 0, 10)[0],
        )

    def test_to_as_two_in_callsign_squawk_and_heading(self):
        aircraft = self.by_id["A3"]
        aircraft.callsign = "DEVIL2"
        reply = handle_transmission(
            "double to squawk to zero zero zero",
            self.aircraft,
            self.facility,
            {"enroute_high"},
        )
        self.assertEqual(aircraft.squawk, "2000")
        self.assertIn("two zero zero zero", reply.text)
        handle_transmission(
            "devil to heading to seven zero",
            self.aircraft,
            self.facility,
            {"enroute_high"},
        )
        self.assertAlmostEqual(
            aircraft.flight_guidance.vector_heading,
            self.facility.location.magnetic_to_true(270),
        )

    def test_two_transcribed_as_to_in_bearing_and_frequency(self):
        aircraft = self.by_id["A1"]
        aircraft.track.offer(TrackingPosition.LOS_ANGELES, "ZLA SECTOR 9")
        aircraft.track.advance(3)
        reply = handle_transmission(
            "N135TC maintain bearing to six five to Imperial contact Los Angeles Center 291.to",
            self.aircraft,
            self.facility,
            {"enroute_low"},
        )
        self.assertAlmostEqual(
            aircraft.flight_guidance.vector_heading,
            self.facility.location.magnetic_to_true(265),
        )
        self.assertIn("Verify Los Angeles Center frequency 291.200.", reply.text)
        self.assertIsNone(aircraft.track.handoff_target)

    def test_two_transcribed_for_to_keeps_clearance_grammar(self):
        aircraft = self.by_id["A3"]
        handle_transmission(
            "devil 279 climb 2 9000",
            self.aircraft,
            self.facility,
            {"enroute_high"},
        )
        self.assertEqual(aircraft.flight_guidance.assigned_altitude, 9000)
        fix = aircraft.flight_guidance.route[aircraft.flight_guidance.next_index].name
        handle_transmission(
            f"devil 279 direct 2 {fix}",
            self.aircraft,
            self.facility,
            {"enroute_high"},
        )
        self.assertEqual(
            aircraft.flight_guidance.route[aircraft.flight_guidance.next_index].name,
            fix,
        )
        handle_transmission(
            "devil 279 maintain bearing 265 2 Imperial",
            self.aircraft,
            self.facility,
            {"enroute_high"},
        )
        self.assertAlmostEqual(
            aircraft.flight_guidance.vector_heading,
            self.facility.location.magnetic_to_true(265),
        )

    def test_magnetic_heading_drives_true_geographic_motion(self):
        aircraft = self.by_id["A3"]
        aircraft.heading = 100 + 14 / 60
        latitude, longitude = aircraft.lat, aircraft.lon
        reply = handle_transmission(
            "Devil 279 heading 090",
            self.aircraft,
            self.facility,
            {"enroute_high"},
        )
        self.assertIn("Heading zero niner zero.", reply.text)
        self.assertNotIn("true", reply.text.lower())
        self.assertAlmostEqual(aircraft.flight_guidance.vector_heading, 100 + 14 / 60)
        aircraft.update_position(10)
        self.assertLess(aircraft.lat, latitude)
        self.assertGreater(aircraft.lon, longitude)

    def test_bearing_with_incorrect_center_frequency_keeps_bearing_and_questions_it(
        self,
    ):
        aircraft = self.by_id["A1"]
        aircraft.callsign = "SHEEP1"
        original_channel = aircraft.radio_channel
        aircraft.track.offer(TrackingPosition.LOS_ANGELES, "ZLA SECTOR 9")
        aircraft.track.advance(3)
        reply = handle_transmission(
            "Sheep 1 maintain bearing 265 to Imperial contact Los Angeles Center 292.2",
            self.aircraft,
            self.facility,
            {"enroute_low"},
        )
        self.assertAlmostEqual(aircraft.flight_guidance.vector_heading, 275 + 14 / 60)
        self.assertIn("Maintain bearing two six five.", reply.text)
        self.assertIn("Verify Los Angeles Center frequency 292.200.", reply.text)
        self.assertEqual(aircraft.radio_channel, original_channel)
        self.assertIsNone(aircraft.track.handoff_target)
        self.assertIsNone(aircraft.track.pending_radio_channel)

    def test_accepted_handoff_keeps_radio_until_pilot_is_told_to_contact_center(self):
        aircraft = self.by_id["A1"]
        aircraft.track.offer(TrackingPosition.LOS_ANGELES, "ZLA SECTOR 9")
        self.assertTrue(aircraft.track.advance(3))
        reply = handle_transmission(
            "N135TC heading 270", self.aircraft, self.facility, {"enroute_low"}
        )
        self.assertIn("Heading two seven zero", reply.text)
        self.assertEqual(aircraft.track.owner, TrackingPosition.LOS_ANGELES)
        self.assertEqual(aircraft.track.communications_owner, TrackingPosition.YUMA)
        self.assertEqual(aircraft.radio_channel, "enroute_low")
        handle_transmission(
            "N135TC squawk 0421", self.aircraft, self.facility, {"enroute_low"}
        )
        self.assertEqual(aircraft.squawk, "0421")
        self.assertIn(
            "Ident.",
            handle_transmission(
                "N135TC ident", self.aircraft, self.facility, {"enroute_low"}
            ).text,
        )
        self.assertIn(
            "Nearest traffic",
            handle_transmission(
                "N135TC say traffic", self.aircraft, self.facility, {"enroute_low"}
            ).text,
        )
        with self.assertRaisesRegex(ValueError, "does not own this track"):
            handle_transmission(
                "N135TC radar contact", self.aircraft, self.facility, {"enroute_low"}
            )

        reply = handle_transmission(
            "N135TC contact Los Angeles Center on 128.6",
            self.aircraft,
            self.facility,
            {"enroute_low"},
        )
        self.assertIn("Contact Los Angeles Center on 128.600", reply.text)
        self.assertEqual(reply.channel, "enroute_low")
        self.assertEqual(aircraft.radio_channel, "zla9_low")
        self.assertEqual(
            aircraft.track.communications_owner, TrackingPosition.LOS_ANGELES
        )
        with self.assertRaises(ValueError):
            handle_transmission(
                "N135TC heading 180", self.aircraft, self.facility, {"enroute_low"}
            )
        with self.assertRaises(ValueError):
            handle_transmission(
                "N135TC heading 180", self.aircraft, self.facility, {"zla9_low"}
            )

    def test_contact_requires_accepted_matching_handoff_and_valid_sector_frequency(
        self,
    ):
        aircraft = self.by_id["A1"]
        for instruction in (
            "contact Los Angeles Center 128.6",
            "maintain bearing 265 contact Los Angeles Center 128.6",
        ):
            with (
                self.subTest(instruction=instruction),
                self.assertRaisesRegex(ValueError, "Complete an outgoing handoff"),
            ):
                handle_transmission(
                    f"N135TC {instruction}",
                    self.aircraft,
                    self.facility,
                    {"enroute_low"},
                )
        self.assertIsNone(aircraft.track.handoff_target)
        self.assertIsNone(aircraft.flight_guidance.vector_heading)
        aircraft.track.offer(TrackingPosition.LOS_ANGELES, "ZLA SECTOR 9")
        with self.assertRaisesRegex(ValueError, "Complete an outgoing handoff"):
            handle_transmission(
                "N135TC contact Los Angeles Center 128.6",
                self.aircraft,
                self.facility,
                {"enroute_low"},
            )
        aircraft.track.advance(3)
        with self.assertRaisesRegex(ValueError, "center that accepted"):
            handle_transmission(
                "N135TC contact Albuquerque Center 125.25",
                self.aircraft,
                self.facility,
                {"enroute_low"},
            )
        for frequency in ("128.15", "292.2"):
            reply = handle_transmission(
                f"N135TC contact Los Angeles Center {frequency}",
                self.aircraft,
                self.facility,
                {"enroute_low"},
            )
            self.assertIn("Verify Los Angeles Center frequency", reply.text)
            self.assertEqual(aircraft.track.communications_owner, TrackingPosition.YUMA)
            self.assertEqual(aircraft.radio_channel, "enroute_low")
        aircraft.altitude = 240
        handle_transmission(
            "N135TC contact Los Angeles Center 128.6",
            self.aircraft,
            self.facility,
            {"enroute_low"},
        )
        self.assertEqual(aircraft.radio_channel, "zla9_low")

    def test_contact_uses_frequency_for_each_configured_sector(self):
        aircraft = self.by_id["A1"]
        for target, label, center, frequency, channel in (
            (
                TrackingPosition.LOS_ANGELES,
                "ZLA SECTOR 9",
                "Los Angeles",
                "128.6",
                "zla9_low",
            ),
            (
                TrackingPosition.LOS_ANGELES,
                "ZLA SECTOR 10",
                "Los Angeles",
                "285.6",
                "zla10_high",
            ),
            (
                TrackingPosition.LOS_ANGELES,
                "ZLA SECTOR 31",
                "Los Angeles",
                "126.775",
                "zla31_low",
            ),
            (
                TrackingPosition.ALBUQUERQUE,
                "ZAB SECTOR 42",
                "Albuquerque",
                "307.3",
                "zab42_high",
            ),
        ):
            with self.subTest(sector=label):
                aircraft.track = TrackOwnership()
                aircraft.radio_channel = "enroute_low"
                aircraft.track.offer(target, label)
                aircraft.track.advance(3)
                handle_transmission(
                    f"N135TC contact {center} Center {frequency}",
                    self.aircraft,
                    self.facility,
                    {"enroute_low"},
                )
                self.assertEqual(aircraft.track.communications_owner, target)
                self.assertEqual(aircraft.radio_channel, channel)

    def test_contact_readback_is_queued_on_the_original_channel(self):
        aircraft = self.by_id["A1"]
        aircraft.track.offer(TrackingPosition.LOS_ANGELES, "ZLA SECTOR 9")
        aircraft.track.advance(3)
        display = Mock(spec=RadarDisplay)
        with patch("simulator.radio.communications.arcade.Text"):
            display.communications_panel = CommunicationsPanel()
        display.aircraft_list = Mock(aircraft_list=self.aircraft)
        display.atc_facility = self.facility
        display.voice_audio = Mock(events=queue.SimpleQueue())
        display.voice_audio.events.put(
            ("transcript", ("N135TC contact Los Angeles Center 128.6", {"enroute_low"}))
        )
        RadarDisplay.process_voice(display)
        self.assertEqual(
            display.voice_audio.speak.call_args.args[0].channel, "enroute_low"
        )
        self.assertEqual(aircraft.radio_channel, "zla9_low")

    def test_bearing_handoff_flashes_then_transfers_to_correct_frequency(self):
        aircraft = self.by_id["A1"]
        aircraft.callsign = "SHEEP1"
        display = SimpleNamespace(
            aircraft_list=SimpleNamespace(aircraft_list=[aircraft]),
            atc_facility=self.facility,
            secondary_radar_returns=[],
            departure_checkins=[],
            reported_departures=set(),
            selected_aircraft_id=None,
            sweep=RadarSweep(),
            radar_return_manager=RadarReturnManager(),
            display_type=RadarDisplay.STARS,
            ARTS_IIE=RadarDisplay.ARTS_IIE,
            secondary_update_elapsed=0,
            emergency_flash_elapsed=0,
            calculate_range_and_bearing=lambda lat, lon: (0, 0),
        )
        display.capture_secondary_radar_returns = lambda: (
            RadarDisplay.capture_secondary_radar_returns(display)
        )
        display.capture_secondary_radar_returns()
        aircraft.track.offer(TrackingPosition.LOS_ANGELES, "ZLA SECTOR 9")
        self.assertEqual(aircraft.radio_channel, "enroute_low")
        RadarDisplay.on_update(display, 1)
        snapshot = display.secondary_radar_returns[0]
        self.assertEqual(snapshot.handoff_target, TrackingPosition.LOS_ANGELES)
        with (
            patch("arcade.draw_circle_filled") as circle,
            patch("arcade.draw_line"),
            patch("arcade.Text"),
        ):
            RadarDisplay.draw_secondary_return(
                snapshot, 100, 200, 1, text_size=(50, 30), flash_visible=False
            )
            circle.assert_not_called()
            RadarDisplay.draw_secondary_return(
                snapshot, 100, 200, 1, text_size=(50, 30), flash_visible=True
            )
            circle.assert_called_once()
        RadarDisplay.on_update(display, 2)
        self.assertEqual(aircraft.track.owner, TrackingPosition.LOS_ANGELES)
        self.assertEqual(aircraft.track.communications_owner, TrackingPosition.YUMA)
        self.assertEqual(aircraft.radio_channel, "enroute_low")
        reply = handle_transmission(
            "Sheep 1 maintain bearing 265 to Imperial contact Los Angeles Center 291.7",
            self.aircraft,
            self.facility,
            {"enroute_low"},
        )
        self.assertIn("Maintain bearing two six five.", reply.text)
        self.assertEqual(
            aircraft.track.communications_owner, TrackingPosition.LOS_ANGELES
        )
        self.assertEqual(aircraft.radio_channel, "zla9_high")
        self.assertIsNone(aircraft.track.pending_radio_channel)
        self.assertIsNone(display.secondary_radar_returns[0].handoff_target)

    def test_bearing_handoff_rejects_pending_coordination_without_turning(self):
        aircraft = self.by_id["A1"]
        aircraft.track.offer_coordination(
            CoordinationKind.POINT_OUT, TrackingPosition.LOS_ANGELES, "TEST"
        )
        with self.assertRaisesRegex(ValueError, "Complete an outgoing handoff"):
            handle_transmission(
                "N135TC maintain bearing 265 contact Los Angeles Center 291.7",
                self.aircraft,
                self.facility,
                {"enroute_low"},
            )
        self.assertIsNone(aircraft.flight_guidance.vector_heading)
        self.assertIsNone(aircraft.track.handoff_target)

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
        self.assertAlmostEqual(aircraft.flight_guidance.vector_heading, 190 + 14 / 60)

    def test_directional_turns_follow_the_requested_direction_and_stop(self):
        aircraft = self.by_id["A1"]
        for direction, initial, target, halfway in (
            ("right", 10, 350, 310),
            ("left", 350, 10, 50),
        ):
            with self.subTest(direction=direction):
                aircraft.heading = self.facility.location.magnetic_to_true(initial)
                reply = handle_transmission(
                    f"N135TC turn {direction} heading {target}",
                    self.aircraft,
                    self.facility,
                    {"enroute_low"},
                )
                self.assertIn(f"Turn {direction}", reply.text)
                aircraft.update_position(100)
                self.assertAlmostEqual(
                    aircraft.heading, self.facility.location.magnetic_to_true(halfway)
                )
                aircraft.update_position(20)
                self.assertAlmostEqual(
                    aircraft.heading, self.facility.location.magnetic_to_true(target)
                )
                self.assertIsNone(aircraft.flight_guidance.vector_turn_direction)
                aircraft.update_position(5)
                self.assertAlmostEqual(
                    aircraft.heading, self.facility.location.magnetic_to_true(target)
                )

    def test_directional_heading_accepts_separated_callsign_and_hyphenated_digits(self):
        aircraft = self.by_id["A1"]
        aircraft.heading = 350
        reply = handle_transmission(
            "N 135 T C turn right heading 0-1-0",
            self.aircraft,
            self.facility,
            {"enroute_low"},
        )
        self.assertIn("Turn right, heading zero one zero.", reply.text)
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

    def test_return_color_follows_contact_and_handoffs(self):
        aircraft_list, facility, _ = create_yuma_scenario()
        aircraft = next(item for item in aircraft_list.aircraft_list if item.id == "A3")
        uncontrolled = next(
            item for item in aircraft_list.aircraft_list if item.id == "A1"
        )
        display = SimpleNamespace(
            aircraft_list=SimpleNamespace(aircraft_list=[aircraft, uncontrolled]),
            atc_facility=facility,
            secondary_radar_returns=[],
            departure_checkins=[],
            reported_departures=set(),
            selected_aircraft_id=None,
            sweep=RadarSweep(),
            radar_return_manager=RadarReturnManager(),
            display_type=RadarDisplay.STARS,
            ARTS_IIE=RadarDisplay.ARTS_IIE,
            secondary_update_elapsed=0,
            emergency_flash_elapsed=0,
            calculate_range_and_bearing=lambda lat, lon: (0, 0),
        )
        display.capture_secondary_radar_returns = lambda: (
            RadarDisplay.capture_secondary_radar_returns(display)
        )
        display.capture_secondary_radar_returns()
        labels = {
            item.id: SimpleNamespace(color=arcade.color.WHITE, draw=Mock())
            for item in (aircraft, uncontrolled)
        }

        def color(item):
            snapshot = next(
                s for s in display.secondary_radar_returns if s.aircraft_id == item.id
            )
            with (
                patch("arcade.draw_circle_filled") as circle,
                patch("arcade.draw_line"),
            ):
                RadarDisplay.draw_secondary_return(
                    snapshot, 100, 200, 1, text_size=(50, 30), label=labels[item.id]
                )
            dot_color = circle.call_args.args[3]
            self.assertEqual(labels[item.id].color, dot_color)
            return dot_color

        self.assertEqual(color(aircraft), arcade.color.GOLD)
        self.assertEqual(color(uncontrolled), arcade.color.WHITE)
        with self.assertRaisesRegex(ValueError, "Yuma must own"):
            handle_transmission(
                "Devil 279 radar contact",
                aircraft_list.aircraft_list,
                facility,
                {"enroute_high"},
            )
        track = aircraft.track
        track.offer(TrackingPosition.YUMA)
        track.accept(TrackingPosition.YUMA)
        track.transfer_communications()
        track.confirm_identification()
        RadarDisplay.on_update(display, 0.1)
        self.assertEqual(color(aircraft), arcade.color.GOLD)
        display.communications_panel = SimpleNamespace(
            mic_hot=False, transmitting=[], monitored=[]
        )
        display.voice_audio = Mock(events=queue.SimpleQueue())
        display.set_caption = Mock()
        display.voice_audio.events.put(
            ("transcript", ("Devil 279 radar contact", {"enroute_high"}))
        )
        RadarDisplay.on_update(display, 0.1)
        self.assertIn(
            "Radar contact, roger", display.voice_audio.speak.call_args.args[0].text
        )
        self.assertEqual(color(aircraft), arcade.color.LIME_GREEN)
        self.assertEqual(color(uncontrolled), arcade.color.WHITE)
        track.offer(TrackingPosition.LOS_ANGELES)
        RadarDisplay.on_update(display, 1)
        self.assertEqual(color(aircraft), arcade.color.LIME_GREEN)
        RadarDisplay.on_update(display, 2)
        self.assertEqual(color(aircraft), arcade.color.DODGER_BLUE)
        track.transfer_communications()
        track.offer(TrackingPosition.YUMA)
        RadarDisplay.on_update(display, 0.1)
        self.assertEqual(color(aircraft), arcade.color.GOLD)
        track.cancel()
        RadarDisplay.on_update(display, 0.1)
        self.assertEqual(color(aircraft), arcade.color.DODGER_BLUE)

    def test_ident_acknowledges_and_displays_until_it_expires(self):
        aircraft = self.by_id["A1"]
        display = SimpleNamespace(
            aircraft_list=SimpleNamespace(aircraft_list=[aircraft]),
            atc_facility=self.facility,
            secondary_radar_returns=[],
            departure_checkins=[],
            reported_departures=set(),
            selected_aircraft_id=None,
            sweep=RadarSweep(),
            radar_return_manager=RadarReturnManager(),
            display_type=RadarDisplay.STARS,
            ARTS_IIE=RadarDisplay.ARTS_IIE,
            secondary_update_elapsed=0,
            emergency_flash_elapsed=0,
            calculate_range_and_bearing=lambda lat, lon: (0, 0),
        )
        display.capture_secondary_radar_returns = lambda: (
            RadarDisplay.capture_secondary_radar_returns(display)
        )
        display.capture_secondary_radar_returns()
        with self.assertRaisesRegex(ValueError, "transmitting frequency"):
            handle_transmission(
                "N135TC ident", self.aircraft, self.facility, {"approach_low"}
            )
        with self.assertRaisesRegex(ValueError, "separately"):
            handle_transmission(
                "N135TC radar contact ident",
                self.aircraft,
                self.facility,
                {"enroute_low"},
            )
        for variant in ("identity", "identical", "i dent"):
            with self.subTest(variant=variant):
                with self.assertRaisesRegex(ValueError, "separately"):
                    handle_transmission(
                        f"N135TC radar contact {variant}",
                        self.aircraft,
                        self.facility,
                        {"enroute_low"},
                    )
                with self.assertRaisesRegex(
                    ValueError, "Unrecognized voice instruction"
                ):
                    handle_transmission(
                        f"N135TC squawk {variant}",
                        self.aircraft,
                        self.facility,
                        {"enroute_low"},
                    )
        with self.assertRaisesRegex(ValueError, "Unrecognized voice instruction"):
            handle_transmission(
                "N135TC squawk ident", self.aircraft, self.facility, {"enroute_low"}
            )
        self.assertEqual(aircraft.ident_remaining, 0)
        for instruction in ("ident", "identity", "identical", "i dent"):
            reply = handle_transmission(
                f"N135TC {instruction}", self.aircraft, self.facility, {"enroute_low"}
            )
            self.assertIn("Ident.", reply.text)
            RadarDisplay.on_update(display, 1)
            snapshot = display.secondary_radar_returns[0]
            self.assertIn(
                " ID", RadarDisplay.secondary_return_layout(snapshot, 0, 0, 0)[0]
            )
            with (
                patch("arcade.draw_circle_filled") as circle,
                patch("arcade.draw_line"),
                patch("arcade.Text"),
            ):
                RadarDisplay.draw_secondary_return(
                    snapshot, 100, 200, 1, text_size=(50, 30), flash_visible=False
                )
                circle.assert_not_called()
        RadarDisplay.on_update(display, 17)
        snapshot = display.secondary_radar_returns[0]
        self.assertNotIn(
            " ID", RadarDisplay.secondary_return_layout(snapshot, 0, 0, 0)[0]
        )
        self.assertEqual(aircraft.ident_remaining, 0)

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
        self.assertAlmostEqual(
            self.by_id["A3"].flight_guidance.vector_heading, 280 + 14 / 60
        )
        reply = display.voice_audio.speak.call_args.args[0]
        self.assertEqual(reply.aircraft_id, "A3")
        self.assertEqual(reply.channel, "enroute_high")
        display.voice_audio.events.put(
            ("transcript", ("Devil 279 squawk three zero zero zero", {"enroute_high"}))
        )
        RadarDisplay.process_voice(display)
        self.assertEqual(self.by_id["A3"].squawk, "3000")
        self.assertIn(
            "three zero zero zero", display.voice_audio.speak.call_args.args[0].text
        )

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
