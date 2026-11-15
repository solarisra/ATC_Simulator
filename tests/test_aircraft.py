import runpy
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from aircraft import Aircraft, AircraftList
from aircraft_models import (
    airbus_a320,
    airbus_h135,
    av8b_harrier,
    bell_ah1w,
    bell_hh1n,
    boeing_767_freighter,
    boeing_b52,
    boeing_ch46e,
    cessna_172,
    cessna_208,
    cessna_citation_m2,
    f5_tiger_ii,
    f16,
    f35c,
    lockheed_c130j,
    piper_pa28,
    sikorsky_ch53d,
    sikorsky_uh60,
    v22_osprey,
)
from atc import ATCFacility, TrackingPosition
from navmath import NavigationalCoordinateSystem
from radar import RadarDisplay, RadarReturnManager, RadarSweep


def make_aircraft(
    aircraft_model=cessna_172,
    heading=90,
    altitude=50,
    speed=100,
    lat=32,
    lon=-114,
    flight_rules="IFR",
):
    return Aircraft(
        aircraft_id="A1",
        squawk="3471",
        mode_s="ID1",
        callsign="TEST",
        aircraft_model=aircraft_model,
        heading=heading,
        altitude=altitude,
        speed=speed,
        distance=0,
        lat=lat,
        lon=lon,
        flight_rules=flight_rules,
    )


class AircraftTests(unittest.TestCase):
    def test_track_handoffs_require_an_offer_and_acceptance(self):
        track = make_aircraft().track
        self.assertEqual(track.owner, TrackingPosition.YUMA)
        with self.assertRaises(ValueError):
            track.accept(TrackingPosition.LOS_ANGELES)
        with self.assertRaises(ValueError):
            track.offer(TrackingPosition.YUMA)
        with self.assertRaises(TypeError):
            track.offer("M")

        track.offer(TrackingPosition.LOS_ANGELES)
        with self.assertRaises(ValueError):
            track.offer(TrackingPosition.ALBUQUERQUE)
        self.assertFalse(track.advance(2.9))
        self.assertEqual(track.owner, TrackingPosition.YUMA)
        self.assertTrue(track.advance(0.1))
        self.assertEqual(track.owner, TrackingPosition.LOS_ANGELES)
        with self.assertRaises(ValueError):
            track.offer(TrackingPosition.ALBUQUERQUE)
        track.offer(TrackingPosition.YUMA)
        self.assertFalse(track.advance(10))
        self.assertEqual(track.owner, TrackingPosition.LOS_ANGELES)
        with self.assertRaises(ValueError):
            track.accept(TrackingPosition.ALBUQUERQUE)
        track.accept(TrackingPosition.YUMA)
        self.assertEqual(track.owner, TrackingPosition.YUMA)

        track.offer(TrackingPosition.ALBUQUERQUE)
        track.cancel()
        self.assertEqual(track.owner, TrackingPosition.YUMA)
        self.assertIsNone(track.handoff_target)
        with self.assertRaises(ValueError):
            track.cancel()

    def test_initial_altitude_and_assigned_squawk_are_preserved(self):
        for flight_rules in ("VFR", "IFR", "None"):
            for heading in (90, 210):
                with self.subTest(flight_rules=flight_rules, heading=heading):
                    aircraft = make_aircraft(flight_rules=flight_rules, heading=heading)
                    self.assertEqual(aircraft.altitude, 50)
                    self.assertEqual(aircraft.squawk, "3471")
                    self.assertEqual(aircraft.flight_rules, flight_rules)

    def test_maneuvers_progress_at_model_rates_independent_of_frame_rate(self):
        for fps in (30, 60, 120):
            with self.subTest(fps=fps):
                aircraft = make_aircraft(heading=359)
                aircraft.update_heading(10)
                aircraft.climb(60)
                aircraft.accelerate(110)
                for _ in range(2 * fps):
                    aircraft.update_position(1 / fps)
                self.assertAlmostEqual(aircraft.heading, 5)
                self.assertAlmostEqual(aircraft.altitude, 50.15)
                self.assertAlmostEqual(aircraft.speed, 103)

                for _ in range(9 * fps):
                    aircraft.update_position(1 / fps)
                self.assertEqual(aircraft.heading, 10)
                self.assertEqual(aircraft.speed, 110)
                self.assertAlmostEqual(aircraft.altitude, 50.825)

    def test_descending_and_braking_stop_at_target_without_overshoot(self):
        aircraft = make_aircraft(altitude=50, speed=101.4)
        aircraft.descend(49.9)
        aircraft.decelerate(100)
        aircraft.update_position(1)
        self.assertAlmostEqual(aircraft.altitude, 49.925)
        self.assertAlmostEqual(aircraft.speed, 100.4)
        aircraft.update_position(1)
        self.assertEqual(aircraft.altitude, 49.9)
        self.assertEqual(aircraft.speed, 100)

    def test_turn_does_not_snap_before_reaching_target(self):
        aircraft = make_aircraft(heading=90)
        aircraft.update_heading(93.5)
        aircraft.update_position(1)
        self.assertEqual(aircraft.heading, 93)
        aircraft.update_position(1)
        self.assertEqual(aircraft.heading, 93.5)

    def test_braking_rate_larger_than_thrust_rate_does_not_overshoot(self):
        model = SimpleNamespace(
            max_speed=200,
            climb_rate=7.5,
            turn_rate=3,
            thrust_rate=1,
            air_braking_rate=5,
        )
        aircraft = make_aircraft(aircraft_model=model, speed=103)
        aircraft.decelerate(100)
        aircraft.update_position(1)
        self.assertEqual(aircraft.speed, 100)
        aircraft.update_position(1)
        self.assertEqual(aircraft.speed, 100)

    def test_speed_and_elapsed_time_validation(self):
        for speed in (-1, 123, float("nan"), float("inf")):
            with self.subTest(speed=speed):
                with self.assertRaises(ValueError):
                    make_aircraft(speed=speed)
                aircraft = make_aircraft()
                with self.assertRaises(ValueError):
                    aircraft.update_speed(speed)
                self.assertIsNone(aircraft.target_speed)
        aircraft = make_aircraft()
        for elapsed in (-1, float("nan"), float("inf")):
            with self.subTest(elapsed=elapsed), self.assertRaises(ValueError):
                aircraft.update_position(elapsed)

    def test_position_uses_time_averaged_speed_when_acceleration_completes(self):
        aircraft = make_aircraft(heading=0, speed=100)
        aircraft.accelerate(103)
        aircraft.update_position(4)
        distance = NavigationalCoordinateSystem.calculate_distance(
            32, -114, aircraft.lat, aircraft.lon
        )
        self.assertAlmostEqual(distance, (101.5 * 2 + 103 * 2) / 3600, places=8)

    def test_list_range_tracks_facility_and_does_not_wrap(self):
        facility = ATCFacility("Test", {"lat": 0, "lon": 0})
        aircraft = make_aircraft(lat=1.7, lon=0, heading=180)
        aircraft_list = AircraftList()
        aircraft_list.add_aircraft([aircraft])
        with self.assertRaises(ValueError):
            aircraft_list.update_positions(1)
        aircraft_list.assign_to_atc_facility(facility)
        initial = NavigationalCoordinateSystem.calculate_distance(
            0, 0, aircraft.lat, aircraft.lon
        )
        aircraft_list.update_positions(1)
        actual = NavigationalCoordinateSystem.calculate_distance(
            0, 0, aircraft.lat, aircraft.lon
        )
        self.assertGreater(actual, 100)
        self.assertLess(actual, initial)
        self.assertAlmostEqual(aircraft.distance, actual)
        aircraft.landed = True
        previous_position = aircraft.lat, aircraft.lon
        aircraft_list.update_positions(1)
        self.assertEqual((aircraft.lat, aircraft.lon), previous_position)
        self.assertAlmostEqual(aircraft.distance, actual)

    def test_add_aircraft_extends_list_in_order(self):
        aircraft_list = AircraftList()
        first, second, third = make_aircraft(), make_aircraft(), make_aircraft()
        aircraft_list.add_aircraft([first, second])
        aircraft_list.add_aircraft([])
        aircraft_list.add_aircraft([third])
        self.assertEqual(aircraft_list.aircraft_list, [first, second, third])
        facility = ATCFacility("Test", {"lat": 0, "lon": 0})
        aircraft_list.assign_to_atc_facility(facility)
        self.assertEqual(facility.aircraft_list, [first, second, third])

    def test_radar_update_advances_commands_and_captures_updated_state(self):
        aircraft = make_aircraft()
        aircraft.climb(60)
        aircraft.decelerate(90)
        display = SimpleNamespace(
            aircraft_list=SimpleNamespace(aircraft_list=[aircraft]),
            sweep=RadarSweep(),
            radar_return_manager=RadarReturnManager(),
            display_type="STARS",
            ARTS_IIE=RadarDisplay.ARTS_IIE,
            secondary_update_elapsed=0,
            emergency_flash_elapsed=0,
            selected_aircraft_id=None,
            secondary_radar_returns=[],
            calculate_range_and_bearing=lambda lat, lon: (10, 0),
        )
        display.capture_secondary_radar_returns = lambda: (
            RadarDisplay.capture_secondary_radar_returns(display)
        )
        RadarDisplay.on_update(display, 1)
        snapshot = display.secondary_radar_returns[0]
        self.assertAlmostEqual(snapshot.altitude, 50.075)
        self.assertEqual(snapshot.speed, 99)
        RadarDisplay.on_update(display, 1)
        self.assertAlmostEqual(aircraft.altitude, 50.15)
        self.assertEqual(aircraft.speed, 98)

    def test_altitude_indicator_tracks_sampled_climb_descent_and_level(self):
        for mode in (RadarDisplay.ARTS_IIE, RadarDisplay.STARS):
            with self.subTest(mode=mode):
                aircraft = make_aircraft()
                display = SimpleNamespace(
                    aircraft_list=SimpleNamespace(aircraft_list=[aircraft]),
                    sweep=RadarSweep(),
                    radar_return_manager=RadarReturnManager(),
                    display_type=mode,
                    ARTS_IIE=RadarDisplay.ARTS_IIE,
                    secondary_update_elapsed=0,
                    secondary_radar_returns=[],
                    emergency_flash_elapsed=0,
                    selected_aircraft_id=None,
                    center_x=600,
                    center_y=450,
                    calculate_range_and_bearing=lambda lat, lon: (10, 0),
                )
                display.capture_secondary_radar_returns = lambda display=display: (
                    RadarDisplay.capture_secondary_radar_returns(display)
                )
                display.capture_secondary_radar_returns()

                def altitude_field(display=display):
                    snapshot = display.secondary_radar_returns[0]
                    return (
                        RadarDisplay.secondary_return_layout(snapshot, 0, 0, 10)[0]
                        .splitlines()[1]
                        .split()[0]
                    )

                self.assertEqual(altitude_field(), "050")
                aircraft.climb(60)
                RadarDisplay.on_update(display, 0.5)
                self.assertEqual(altitude_field(), "050")
                RadarDisplay.on_update(display, 0.5)
                self.assertEqual(altitude_field(), "+050")
                aircraft.descend(aircraft.altitude - 0.02)
                RadarDisplay.on_update(display, 1)
                self.assertEqual(altitude_field(), "-050")
                RadarDisplay.on_update(display, 1)
                self.assertEqual(altitude_field(), "050")

    def test_sample_aircraft_are_constructed_with_valid_speeds(self):
        with patch("radar.RadarDisplay") as display, patch("arcade.run") as run:
            runpy.run_path("main.py", run_name="__main__")
        aircraft = display.call_args.args[0].aircraft_list
        self.assertEqual([item.speed for item in aircraft[:3]], [120, 600, 160])
        self.assertEqual([item.altitude for item in aircraft[:3]], [50, 40, 75])
        display.return_value.setup.assert_called_once()
        run.assert_called_once()

    def test_new_models_support_flight_and_maneuvers(self):
        models = (
            airbus_a320,
            boeing_767_freighter,
            cessna_208,
            piper_pa28,
            cessna_citation_m2,
            airbus_h135,
            f16,
            lockheed_c130j,
            sikorsky_uh60,
            boeing_b52,
            f5_tiger_ii,
            v22_osprey,
            f35c,
            sikorsky_ch53d,
            boeing_ch46e,
            av8b_harrier,
            bell_ah1w,
            bell_hh1n,
        )
        self.assertEqual(len({model.aircraft_type for model in models}), len(models))
        for model in models:
            with self.subTest(aircraft_type=model.aircraft_type):
                self.assertGreater(model.cruise_speed, 0)
                self.assertLessEqual(model.cruise_speed, model.max_speed)
                aircraft = make_aircraft(aircraft_model=model, speed=model.cruise_speed)
                aircraft.update_heading(180)
                aircraft.climb(60)
                aircraft.decelerate(model.cruise_speed / 2)
                initial_position = aircraft.lat, aircraft.lon
                aircraft.update_position(1)
                self.assertNotEqual((aircraft.lat, aircraft.lon), initial_position)
                self.assertGreater(aircraft.heading, 90)
                self.assertGreater(aircraft.altitude, 50)
                self.assertLess(aircraft.speed, model.cruise_speed)

    def test_startup_traffic_is_within_radar_coverage(self):
        with patch("radar.RadarDisplay") as display, patch("arcade.run"):
            runpy.run_path("main.py", run_name="__main__")
        aircraft_list, facility = display.call_args.args
        aircraft = aircraft_list.aircraft_list
        self.assertEqual(
            {item.id for item in aircraft},
            {
                "A1",
                "A3",
                "A6",
                "A7",
                "A8",
                "A9",
                "A10",
                "A11",
                "A12",
                "A14",
                "A15",
                "A16",
            },
        )
        self.assertEqual(len({item.id for item in aircraft}), len(aircraft))
        self.assertEqual(len({item.callsign for item in aircraft}), len(aircraft))
        for item in aircraft:
            with self.subTest(callsign=item.callsign):
                distance = NavigationalCoordinateSystem.calculate_distance(
                    facility.location["lat"],
                    facility.location["lon"],
                    item.lat,
                    item.lon,
                )
                self.assertLess(distance, 100)
                self.assertLessEqual(item.speed, item.aircraft_model.max_speed)


if __name__ == "__main__":
    unittest.main()
