import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import arcade

from locations.Yuma.Scenarios.generator import (
    AIRCRAFT_TYPES,
    OPERATIONS,
    GeneratorSettings,
    generate_yuma_scenario,
)
from locations.Yuma.Scenarios.yuma import create_yuma_scenario
from simulator.app.briefing import briefing_pages
from simulator.app.scenario_storage import (
    read_scenario,
    saved_names,
    scenario_path,
    snapshot_scenario,
    write_scenario,
)
from simulator.core.aircraft import display_callsign
from simulator.core.aircraft_models import boeing_767_freighter
from simulator.core.atc import CoordinationKind, RadarControlState, TrackingPosition
from simulator.core.location import RadioState
from simulator.display.flight_strips import FlightStripPanel
from simulator.display.radar import RadarDisplay, RadarReturnManager, RadarSweep
from simulator.radio.communications import CommunicationsPanel
from simulator.radio.voice_audio import PILOT_VOICES, assign_pilot_voices
from simulator.radio.voice_commands import handle_transmission


class ScenarioStorageTests(unittest.TestCase):
    def test_incoming_handoff_and_checkin_state_survive_save_and_reload(self):
        operations = dict.fromkeys(OPERATIONS, 0)
        operations["approaches"] = 1
        types = dict.fromkeys(AIRCRAFT_TYPES, 0)
        types["air carriers"] = 1
        settings = GeneratorSettings(7, "light", operations, types)
        start = datetime(2026, 11, 15, 20, tzinfo=UTC)
        aircraft, facility, strips, _ = generate_yuma_scenario(settings, start)
        aircraft.aircraft_list[1].entry_remaining = 1
        aircraft.aircraft_list[0].lat += 1
        with patch("simulator.radio.communications.arcade.Text"):
            communications = CommunicationsPanel(
                facility.location.radio_frequencies,
                facility.location.coordination_lines,
                facility.location.interfacility_lines,
            )
        snapshot = snapshot_scenario(
            aircraft, facility, strips, start, settings, communications, [], set()
        )
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            write_scenario("INBOUND", snapshot, directory)
            restored = read_scenario("INBOUND", directory)
            first, second, *_ = restored.aircraft.aircraft_list
            self.assertEqual(first.track.handoff_target, TrackingPosition.YUMA)
            self.assertTrue(second.incoming_handoff_on_entry)
            self.assertIsNone(second.track.handoff_target)
            restored.aircraft.update_positions(1)
            self.assertEqual(second.track.handoff_target, TrackingPosition.YUMA)
            second.track.cancel()
            restored.aircraft.update_positions(1)
            self.assertIsNone(second.track.handoff_target)
            self.assertTrue(second.incoming_checkin_pending)
            first.track.accept(TrackingPosition.YUMA)
            first.track.transfer_communications()
            display = SimpleNamespace(
                aircraft_list=SimpleNamespace(aircraft_list=[first]),
                atc_facility=restored.facility, secondary_radar_returns=[],
                departure_checkins=[], reported_departures=set(),
                selected_aircraft_id=None, sweep=RadarSweep(),
                radar_return_manager=RadarReturnManager(),
                display_type=RadarDisplay.STARS, ARTS_IIE=RadarDisplay.ARTS_IIE,
                secondary_update_elapsed=0, emergency_flash_elapsed=0,
                calculate_range_and_bearing=lambda lat, lon: (30, 0),
                voice_audio=Mock(),
            )
            display.capture_secondary_radar_returns = lambda: (
                RadarDisplay.capture_secondary_radar_returns(display)
            )
            with patch.object(RadarDisplay, "process_voice"):
                RadarDisplay.on_update(display, 1)
            display.voice_audio.speak.assert_called_once()
            snapshot = snapshot_scenario(
                restored.aircraft, restored.facility, restored.strips, start,
                settings, communications, display.departure_checkins, set()
            )
            write_scenario("AFTER", snapshot, directory)
            after = read_scenario("AFTER", directory)
            self.assertFalse(after.aircraft.aircraft_list[0].incoming_checkin_pending)
            self.assertTrue(after.aircraft.aircraft_list[1].incoming_checkin_pending)
            self.assertIsNone(after.aircraft.aircraft_list[1].track.handoff_target)
            display.aircraft_list.aircraft_list = [after.aircraft.aircraft_list[0]]
            display.voice_audio.speak.reset_mock()
            with patch.object(RadarDisplay, "process_voice"):
                RadarDisplay.on_update(display, 1)
            display.voice_audio.speak.assert_not_called()
            after.aircraft.update_positions(1)
            self.assertIsNone(after.aircraft.aircraft_list[1].track.handoff_target)
            invalid = json.loads(json.dumps(snapshot))
            invalid["records"][1]["aircraft"]["incoming_handoff_on_entry"] = True
            with self.assertRaisesRegex(ValueError, "scheduled incoming handoff"):
                write_scenario("INVALID HANDOFF", invalid, directory)

    def test_scheduled_arrivals_survive_save_and_resume(self):
        operations = dict.fromkeys(OPERATIONS, 0)
        operations["approaches"] = 1
        settings = GeneratorSettings(0, "light", operations)
        start = datetime(2026, 11, 15, 20, tzinfo=UTC)
        aircraft, facility, strips, _ = generate_yuma_scenario(settings, start)
        for _ in range(24):
            aircraft.update_positions(5)
        expected = [plane.entry_remaining for plane in aircraft.aircraft_list]
        self.assertEqual(expected, [None, 180, 480, 780, 1080])
        with patch("simulator.radio.communications.arcade.Text"):
            communications = CommunicationsPanel(
                facility.location.radio_frequencies,
                facility.location.coordination_lines,
                facility.location.interfacility_lines,
            )
        snapshot = snapshot_scenario(
            aircraft, facility, strips, start + timedelta(seconds=120),
            settings, communications, [], set(),
        )
        briefing = briefing_pages(facility, strips, communications)
        self.assertIn("1 active aircraft; 4 scheduled inbound", briefing[0][-1])
        self.assertTrue(
            any("scheduled inbound in 180 seconds" in line for page in briefing for line in page)
        )
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            write_scenario("ARRIVALS", snapshot, directory)
            restored = read_scenario("ARRIVALS", directory)
            legacy = json.loads(json.dumps(snapshot))
            for record in legacy["records"]:
                del record["aircraft"]["entry_remaining"]
                del record["aircraft"]["incoming_handoff_on_entry"]
                del record["aircraft"]["incoming_checkin_pending"]
            write_scenario("OLD", legacy, directory)
            old = read_scenario("OLD", directory)
            invalid = json.loads(json.dumps(snapshot))
            invalid["records"][1]["aircraft"]["entry_remaining"] = -1
            with self.assertRaises(ValueError):
                write_scenario("INVALID ENTRY", invalid, directory)

        self.assertEqual(
            [plane.entry_remaining for plane in restored.aircraft.aircraft_list],
            expected,
        )
        self.assertTrue(all(plane.entry_remaining is None for plane in old.aircraft.aircraft_list))
        for _ in range(36):
            aircraft.update_positions(5)
            restored.aircraft.update_positions(5)
        self.assertEqual(
            [plane.entry_remaining for plane in restored.aircraft.aircraft_list],
            [plane.entry_remaining for plane in aircraft.aircraft_list],
        )
        self.assertIsNone(restored.aircraft.aircraft_list[1].entry_remaining)

    def test_pilot_voice_survives_scenario_save_and_reload(self):
        aircraft, facility, strips = create_yuma_scenario()
        assign_pilot_voices(aircraft.aircraft_list)
        plane = aircraft.aircraft_list[0]
        voices = [item.pilot_voice for item in aircraft.aircraft_list]
        with patch("simulator.radio.communications.arcade.Text"):
            communications = CommunicationsPanel(
                facility.location.radio_frequencies,
                facility.location.coordination_lines,
                facility.location.interfacility_lines,
            )
        snapshot = snapshot_scenario(
            aircraft,
            facility,
            strips,
            datetime.now(UTC),
            None,
            communications,
            [],
            set(),
        )
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            write_scenario("VOICES", snapshot, directory)
            restored = read_scenario("VOICES", directory)
        self.assertEqual(
            restored.aircraft.aircraft_list[0].pilot_voice, plane.pilot_voice
        )
        assign_pilot_voices(restored.aircraft.aircraft_list)
        self.assertEqual(
            [item.pilot_voice for item in restored.aircraft.aircraft_list], voices
        )
        reply = handle_transmission(
            "N135TC ident",
            restored.aircraft.aircraft_list,
            restored.facility,
            {"enroute_low"},
        )
        self.assertEqual(reply.pilot_voice, plane.pilot_voice)
        legacy = json.loads(json.dumps(snapshot))
        for record in legacy["records"]:
            del record["aircraft"]["pilot_voice"]
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            write_scenario("LEGACY VOICES", legacy, directory)
            restored_legacy = read_scenario("LEGACY VOICES", directory)
        self.assertTrue(
            all(
                item.pilot_voice is None
                for item in restored_legacy.aircraft.aircraft_list
            )
        )
        assign_pilot_voices(restored_legacy.aircraft.aircraft_list)
        self.assertTrue(
            all(
                item.pilot_voice in PILOT_VOICES
                for item in restored_legacy.aircraft.aircraft_list
            )
        )
        invalid = json.loads(json.dumps(snapshot))
        invalid["records"][0]["aircraft"]["pilot_voice"] = "not-a-voice"
        with tempfile.TemporaryDirectory() as folder, self.assertRaises(ValueError):
            write_scenario("INVALID VOICE", invalid, Path(folder))

    def test_accepted_handoff_keeps_radio_workflow_after_reload(self):
        aircraft, facility, strips = create_yuma_scenario()
        plane = next(item for item in aircraft.aircraft_list if item.id == "A1")
        plane.track.offer(TrackingPosition.LOS_ANGELES, "ZLA SECTOR 9")
        plane.track.advance(3)
        with patch("simulator.radio.communications.arcade.Text"):
            communications = CommunicationsPanel(
                facility.location.radio_frequencies,
                facility.location.coordination_lines,
                facility.location.interfacility_lines,
            )
        snapshot = snapshot_scenario(
            aircraft,
            facility,
            strips,
            datetime.now(UTC),
            None,
            communications,
            [],
            set(),
        )
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            write_scenario("HANDOFF", snapshot, directory)
            restored = read_scenario("HANDOFF", directory)
        plane = next(
            item for item in restored.aircraft.aircraft_list if item.id == "A1"
        )
        self.assertEqual(plane.track.owner, TrackingPosition.LOS_ANGELES)
        self.assertEqual(plane.track.communications_owner, TrackingPosition.YUMA)
        handle_transmission(
            "N135TC contact Los Angeles Center 128.6",
            restored.aircraft.aircraft_list,
            restored.facility,
            {"enroute_low"},
        )
        self.assertEqual(plane.radio_channel, "zla9_low")
        self.assertEqual(plane.track.communications_owner, TrackingPosition.LOS_ANGELES)

    def test_round_trip_preserves_operational_state_and_continues(self):
        operations = dict.fromkeys(OPERATIONS, 0)
        operations["departures"] = 1
        types = dict.fromkeys(AIRCRAFT_TYPES, 0)
        types["military jets"] = 1
        settings = GeneratorSettings(7, "very light", operations, types)
        start = datetime(2026, 11, 15, 20, tzinfo=UTC)
        aircraft, facility, strips, _ = generate_yuma_scenario(settings, start)
        first = aircraft.aircraft_list[0]
        elapsed = first.departure.delay + 60
        for plane in aircraft.aircraft_list:
            plane.update_position(elapsed)
        first.flight_guidance.assign_heading(275, "LEFT")
        first.flight_guidance.assign_altitude(9000)
        first.update_speed(250)
        first.callsign = "AAL381"
        first.aircraft_model = boeing_767_freighter
        first.scratchpad = "AB"
        first.activate_ident()
        first.track.radar_control_state = RadarControlState.CONTROLLED
        first.track.offer(TrackingPosition.LOS_ANGELES, "COORD")
        first.track.pending_radio_channel = "zla9_high"
        second = aircraft.aircraft_list[1]
        second.track.offer_coordination(
            CoordinationKind.POINT_OUT, TrackingPosition.LOS_ANGELES, "TEST"
        )
        strips[0].remarks = "REMARK"
        strips[0].offset_right = True
        strips[0].discarded = True
        strips.reverse()
        with patch("simulator.radio.communications.arcade.Text"):
            communications = CommunicationsPanel(
                facility.location.radio_frequencies,
                facility.location.coordination_lines,
                facility.location.interfacility_lines,
            )
        communications.channels[0].state = RadioState.LISTEN
        communications.lines[0].hot = True
        communications.interfacility_lines[2].hot = True
        self.assertTrue(
            any(
                "ZLA SECTOR 31: HOT" in page
                for page in briefing_pages(facility, strips, communications)
            )
        )
        time = start + timedelta(seconds=first.departure.elapsed)
        snapshot = snapshot_scenario(
            aircraft,
            facility,
            strips,
            time,
            settings,
            communications,
            [first.departure.check_in],
            {first.id},
        )
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            write_scenario("TEST ONE", snapshot, directory)
            self.assertEqual(saved_names(directory), ["TEST ONE"])
            restored = read_scenario("TEST ONE", directory)
            pending_copy = read_scenario("TEST ONE", directory)
            with self.assertRaises(FileExistsError):
                write_scenario("TEST ONE", snapshot, directory)
            path = scenario_path("TEST ONE", directory)
            original = path.read_bytes()
            with self.assertRaises(ValueError):
                write_scenario(
                    "TEST ONE", {**snapshot, "version": 999}, directory, overwrite=True
                )
            self.assertEqual(path.read_bytes(), original)
            invalid_offset = json.loads(json.dumps(snapshot))
            invalid_offset["records"][0]["strip"]["offset_right"] = "yes"
            with self.assertRaises(ValueError):
                write_scenario("INVALID", invalid_offset, directory)
            invalid_discarded = json.loads(json.dumps(snapshot))
            invalid_discarded["records"][0]["strip"]["discarded"] = "yes"
            with self.assertRaises(ValueError):
                write_scenario("INVALID", invalid_discarded, directory)
            legacy = json.loads(json.dumps(snapshot))
            for record in legacy["records"]:
                del record["aircraft"]["ident_remaining"]
                del record["track"]["radar_control_state"]
                del record["track"]["pending_radio_channel"]
                del record["strip"]["offset_right"]
                del record["strip"]["discarded"]
            for line in communications.interfacility_lines:
                del legacy["lines"][line.identifier]
            write_scenario("LEGACY", legacy, directory)
            legacy_restored = read_scenario("LEGACY", directory)
            self.assertEqual(
                legacy_restored.aircraft.aircraft_list[0].ident_remaining, 0
            )
            self.assertFalse(legacy_restored.lines["zla_sector_31"])
            self.assertTrue(
                all(not strip.offset_right for strip in legacy_restored.strips)
            )
            self.assertTrue(
                all(not strip.discarded for strip in legacy_restored.strips)
            )
        self.assertEqual(restored.time, time)
        self.assertEqual(restored.settings, settings)
        self.assertEqual(
            [s.flight_id for s in restored.strips], [s.flight_id for s in strips]
        )
        self.assertEqual(
            [s.offset_right for s in restored.strips], [s.offset_right for s in strips]
        )
        self.assertEqual(
            [s.discarded for s in restored.strips], [s.discarded for s in strips]
        )
        discarded = next(strip for strip in restored.strips if strip.discarded)
        with patch("simulator.display.flight_strips.arcade.Text"):
            panel = FlightStripPanel(restored.strips, restored.aircraft)
        self.assertNotIn(discarded, panel.active_strips())
        panel.on_key_press(arcade.key.R, None)
        self.assertIn(discarded, panel.visible_strips())
        panel.on_key_press(arcade.key.ENTER, discarded.aircraft.id)
        self.assertIn(discarded, panel.active_strips())
        self.assertIs(discarded.aircraft.flight_guidance.strip, discarded)
        self.assertEqual(
            restored.radios[communications.channels[0].identifier], RadioState.LISTEN
        )
        self.assertTrue(restored.lines[communications.lines[0].identifier])
        self.assertTrue(restored.lines["zla_sector_31"])
        self.assertEqual(restored.reported_departures, {first.id})
        restored_first = restored.aircraft.aircraft_list[0]
        self.assertEqual(restored_first.callsign, "AAL381")
        self.assertEqual(display_callsign(restored_first), "AAL381H")
        self.assertEqual(restored_first.ident_remaining, first.ident_remaining)
        self.assertEqual(
            restored_first.track.radar_return_state, RadarControlState.CONTROLLED
        )
        self.assertEqual(restored_first.scratchpad, "AB")
        self.assertEqual(
            restored_first.track.handoff_target, TrackingPosition.LOS_ANGELES
        )
        self.assertEqual(restored_first.track.pending_radio_channel, "zla9_high")
        pending_plane = pending_copy.aircraft.aircraft_list[0]
        display = SimpleNamespace(
            aircraft_list=SimpleNamespace(aircraft_list=[pending_plane]),
            atc_facility=pending_copy.facility,
            secondary_radar_returns=[],
            departure_checkins=[],
            reported_departures={pending_plane.id},
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
        RadarDisplay.on_update(display, 3)
        self.assertEqual(
            pending_plane.track.communications_owner, TrackingPosition.LOS_ANGELES
        )
        self.assertEqual(pending_plane.radio_channel, "zla9_high")
        self.assertEqual(
            restored.aircraft.aircraft_list[1].track.coordination.information, "TEST"
        )
        self.assertEqual(restored_first.flight_guidance.vector_heading, 275)
        self.assertEqual(restored_first.flight_guidance.assigned_altitude, 9000)
        self.assertEqual(restored_first.departure.check_in, first.departure.check_in)
        for before, after in zip(
            aircraft.aircraft_list, restored.aircraft.aircraft_list
        ):
            before.update_position(60)
            after.update_position(60)
            for name in ("lat", "lon", "heading", "speed", "altitude"):
                self.assertAlmostEqual(getattr(before, name), getattr(after, name))
            self.assertEqual(before.departure.state, after.departure.state)
            self.assertEqual(
                before.flight_guidance.next_index, after.flight_guidance.next_index
            )

    def test_invalid_files_and_unsafe_names_are_rejected(self):
        for name in ("", "../escape", "CON", "name.", "leading ", "A/B"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                scenario_path(name)
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            (directory / "BAD.json").write_text(
                json.dumps({"version": 1}), encoding="utf-8"
            )
            with self.assertRaises(ValueError):
                read_scenario("BAD", directory)


if __name__ == "__main__":
    unittest.main()
