import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from unittest.mock import patch

from locations.Yuma.Scenarios.generator import (
    AIRCRAFT_TYPES,
    OPERATIONS,
    PROFILES,
    GeneratorSettings,
    _itineraries,
    generate_yuma_scenario,
)
from locations.Yuma.Scenarios.routing import NoSafeRouteError, yuma_router
from locations.Yuma.Scenarios.sample_data import CIVILIAN_AIRPORTS
from locations.Yuma.Scenarios.yuma import create_yuma_scenario
from simulator.core.atc import FlightPlan, RadarControlState, TrackingPosition
from simulator.navigation.flight_navigation import NavigationData
from simulator.navigation.navmath import NavigationalCoordinateSystem
from simulator.radio.voice_commands import handle_transmission


class ScenarioGeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.navigation = NavigationData()

    def generate(self, settings, start_time=None):
        if start_time is None:
            start_time = datetime(2026, 11, 15, 20, 0, tzinfo=UTC)
        with patch(
            "locations.Yuma.Scenarios.generator.NavigationData",
            return_value=self.navigation,
        ):
            return generate_yuma_scenario(settings, start_time)

    def test_seed_reproduces_traffic_and_heavy_volume(self):
        settings = GeneratorSettings(seed=271, volume="heavy")
        first = self.generate(settings)
        second = self.generate(settings)

        def traffic(result):
            return [
                (
                    strip.aircraft.callsign,
                    strip.aircraft.aircraft_model.aircraft_type,
                    strip.aircraft.lat,
                    strip.aircraft.lon,
                    strip.flight_plan.origin,
                    strip.flight_plan.destination,
                    strip.flight_plan.route,
                )
                for strip in result[2]
            ]

        self.assertEqual(len(first[2]), 20)
        self.assertEqual(traffic(first), traffic(second))
        self.assertEqual(len({s.aircraft.callsign for s in first[2]}), 20)
        self.assertNotEqual(
            traffic(first), traffic(self.generate(GeneratorSettings(272, "heavy")))
        )

    def test_generated_civilian_registrations_are_valid_and_unique(self):
        types = dict.fromkeys(AIRCRAFT_TYPES, 0)
        types["small fixed-wing"] = 1
        _, _, strips, _ = self.generate(
            GeneratorSettings(7, "heavy", aircraft_types=types)
        )
        registrations = [strip.aircraft.callsign for strip in strips]
        self.assertEqual(len(set(registrations)), len(registrations))
        for registration in registrations:
            self.assertRegex(registration, r"^N[1-9][0-9]{2}[A-HJ-NP-Z]{2}$")

    def test_sample_incoming_ifr_starts_under_center_control(self):
        strips = create_yuma_scenario()[2]
        incoming = [
            s
            for s in strips
            if s.aircraft.flight_rules == "IFR" and s.flight_plan.origin != "KNYL"
        ]
        self.assertTrue(incoming)
        for strip in strips:
            track = strip.aircraft.track
            if strip in incoming:
                self.assertEqual(track.owner, TrackingPosition.LOS_ANGELES)
                self.assertEqual(track.communications_owner, track.owner)
                self.assertEqual(track.radar_return_state, RadarControlState.INCOMING)
            else:
                self.assertEqual(track.owner, TrackingPosition.YUMA)
                self.assertEqual(track.communications_owner, TrackingPosition.YUMA)
                self.assertEqual(
                    track.radar_return_state, RadarControlState.UNCONTROLLED
                )

    def test_generated_airborne_flights_start_with_yuma_ownership_and_comms(self):
        types = dict.fromkeys(AIRCRAFT_TYPES, 0)
        types["small fixed-wing"] = 1
        observed_rules = set()
        for operation in ("approaches", "enroute"):
            operations = dict.fromkeys(OPERATIONS, 0)
            operations[operation] = 1
            aircraft_list, facility, strips, _ = self.generate(
                GeneratorSettings(7, "heavy", operations, types)
            )
            for strip in strips:
                aircraft = strip.aircraft
                observed_rules.add(aircraft.flight_rules)
                self.assertIsNone(aircraft.departure)
                self.assertLess(aircraft.distance, 50)
                self.assertLessEqual(
                    aircraft.altitude, facility.upper_control_flight_level
                )
                self.assertEqual(aircraft.track.owner, TrackingPosition.YUMA)
                self.assertEqual(
                    aircraft.track.communications_owner, TrackingPosition.YUMA
                )
                self.assertIsNone(aircraft.track.handoff_target)
                self.assertFalse(aircraft.track.identification_confirmation_due)
                self.assertEqual(
                    aircraft.track.radar_return_state, RadarControlState.UNCONTROLLED
                )
            ifr = next(s.aircraft for s in strips if s.aircraft.flight_rules == "IFR")
            reply = handle_transmission(
                f"{ifr.callsign} heading 270",
                aircraft_list.aircraft_list,
                facility,
                {ifr.radio_channel},
            )
            self.assertEqual(reply.channel, ifr.radio_channel)
            self.assertIsNotNone(ifr.flight_guidance.vector_heading)
            handle_transmission(
                f"{ifr.callsign} radar contact",
                aircraft_list.aircraft_list,
                facility,
                {ifr.radio_channel},
            )
            self.assertEqual(ifr.track.radar_return_state, RadarControlState.CONTROLLED)
        self.assertEqual(observed_rules, {"IFR", "VFR"})

    def test_operation_and_type_weights_are_respected(self):
        operations = dict.fromkeys(OPERATIONS, 0)
        operations["approaches"] = 1
        types = dict.fromkeys(AIRCRAFT_TYPES, 0)
        types["helicopters"] = 1
        _, _, strips, warnings = self.generate(
            GeneratorSettings(7, "very light", operations, types)
        )
        self.assertEqual(len(strips), 3)
        self.assertTrue(all(s.flight_plan.destination == "KNYL" for s in strips))
        self.assertTrue(
            all(
                s.aircraft.aircraft_model.aircraft_type
                in {"EC35", "H60", "H46", "H53", "V22"}
                for s in strips
            )
        )
        self.assertEqual(warnings, [])

    def test_heavy_enroute_is_supported(self):
        operations = dict.fromkeys(OPERATIONS, 0)
        operations["approaches"] = operations["enroute"] = 1
        types = dict.fromkeys(AIRCRAFT_TYPES, 0)
        types["heavies"] = 1
        _, _, strips, warnings = self.generate(
            GeneratorSettings(1, "single", operations, types)
        )
        self.assertEqual(len(strips), 1)
        self.assertNotEqual(
            strips[0].flight_plan.origin, strips[0].flight_plan.destination
        )
        self.assertEqual(warnings, [])

    def test_invalid_or_unsupported_settings_fail(self):
        with self.assertRaises(ValueError):
            self.generate(GeneratorSettings(1, operations=dict.fromkeys(OPERATIONS, 0)))
        operations = dict.fromkeys(OPERATIONS, 0)
        operations["enroute"] = 1
        types = dict.fromkeys(AIRCRAFT_TYPES, 0)
        types["heavies"] = 1
        with (
            patch("locations.Yuma.Scenarios.generator._itineraries", return_value=[]),
            self.assertRaisesRegex(ValueError, "No supported combinations"),
        ):
            self.generate(
                GeneratorSettings(1, operations=operations, aircraft_types=types)
            )

    def test_all_itineraries_resolve_within_range_and_avoid_mexico(self):
        router = yuma_router(self.navigation)
        for profile in PROFILES:
            for operation in OPERATIONS:
                for origin, destination, route, _, _ in _itineraries(
                    profile, operation, router
                ):
                    with self.subTest(model=profile.model.aircraft_type, route=route):
                        plan = FlightPlan(
                            "T", origin, destination, route, 6000, profile.speed
                        )
                        points = self.navigation.resolve(plan)
                        self.assertNotIn("KRNM", route.split())
                        for token in route.split():
                            self.assertRegex(token, r"^[A-Z0-9]{3,5}$")
                        self.assertTrue(
                            all(router._safe(a, b) for a, b in pairwise(points))
                        )
                        distance = sum(
                            NavigationalCoordinateSystem.calculate_distance(
                                a.latitude, a.longitude, b.latitude, b.longitude
                            )
                            for a, b in pairwise(points)
                        )
                        self.assertLessEqual(distance, profile.model.max_range)

    def test_router_uses_airways_or_reports_a_safe_direct_fallback(self):
        router = yuma_router(self.navigation)
        route, _, fallback = router.flight("KNYL", "KPHX")
        self.assertIn("V66", route.split())
        self.assertFalse(fallback)
        with patch.object(router, "distances", {router.anchor_id: 0}):
            tokens, _, fallback = router._airport_leg("KPHX")
        self.assertEqual(tokens, ())
        self.assertTrue(fallback)
        with (
            patch.object(router, "distances", {router.anchor_id: 0}),
            patch.object(router, "_safe", return_value=False),
            self.assertRaisesRegex(ValueError, "No route avoiding Mexico"),
        ):
            router._airport_leg("KPHX")

    def test_unsafe_airports_are_omitted_and_reported(self):
        profile = replace(
            next(
                profile for profile in PROFILES if profile.model.aircraft_type == "C172"
            ),
            airports=("KPHX", "KSAN"),
        )
        operations = dict.fromkeys(OPERATIONS, 0)
        operations["departures"] = 1
        types = dict.fromkeys(AIRCRAFT_TYPES, 0)
        types["small fixed-wing"] = 1
        router = yuma_router(self.navigation)
        original = router.airport_leg

        def leg(airport):
            if airport == "KSAN":
                raise NoSafeRouteError(airport)
            return original(airport)

        with (
            patch("locations.Yuma.Scenarios.generator.PROFILES", (profile,)),
            patch.object(router, "airport_leg", side_effect=leg),
        ):
            _, _, strips, warnings = self.generate(
                GeneratorSettings(1, "single", operations, types)
            )
        self.assertEqual(strips[0].flight_plan.destination, "KPHX")
        self.assertIn("KSAN", warnings[0])

    def test_direct_fallback_is_reported_in_briefing_warnings_and_strip(self):
        profile = replace(
            next(
                profile for profile in PROFILES if profile.model.aircraft_type == "C172"
            ),
            airports=("KPHX",),
        )
        operations = dict.fromkeys(OPERATIONS, 0)
        operations["departures"] = 1
        types = dict.fromkeys(AIRCRAFT_TYPES, 0)
        types["small fixed-wing"] = 1
        router = yuma_router(self.navigation)
        with (
            patch("locations.Yuma.Scenarios.generator.PROFILES", (profile,)),
            patch.object(router, "airport_leg", return_value=((), 100, True)),
        ):
            _, _, strips, warnings = self.generate(
                GeneratorSettings(1, "single", operations, types)
            )
        self.assertEqual(strips[0].flight_plan.route, "DCT BZA DCT")
        self.assertEqual(strips[0].remarks, "DIRECT ROUTE FALLBACK")
        self.assertIn(strips[0].aircraft.callsign, warnings[0])

    def test_civilian_destinations_favor_primary_airports(self):
        operations = dict.fromkeys(OPERATIONS, 0)
        operations["departures"] = 1
        types = dict.fromkeys(AIRCRAFT_TYPES, 0)
        types["air carriers"] = 1
        tiers = []
        for seed in range(20):
            strips = self.generate(GeneratorSettings(seed, "heavy", operations, types))[
                2
            ]
            tiers.extend(
                CIVILIAN_AIRPORTS[s.flight_plan.destination][0] for s in strips
            )
        self.assertGreater(tiers.count("primary"), tiers.count("occasional"))
        self.assertGreater(tiers.count("occasional"), tiers.count("rare"))

    def test_departures_follow_daytime_heavy_spacing_and_utc_rollover(self):
        operations = dict.fromkeys(OPERATIONS, 0)
        operations["departures"] = 1
        types = dict.fromkeys(AIRCRAFT_TYPES, 0)
        types["small fixed-wing"] = 1
        settings = GeneratorSettings(9, "heavy", operations, types)
        start = datetime(2026, 11, 15, 23, 59, tzinfo=UTC)
        strips = self.generate(settings, start)[2]
        delays = [strip.aircraft.departure.delay for strip in strips]
        self.assertEqual(len(delays), 20)
        self.assertTrue(all(180 <= b - a <= 300 for a, b in zip([0, *delays], delays)))
        self.assertEqual(
            strips[-1].aircraft.departure.scheduled_utc,
            start + timedelta(seconds=delays[-1]),
        )
        self.assertGreater(
            strips[-1].aircraft.departure.scheduled_utc.date(), start.date()
        )
        self.assertEqual(
            delays,
            [s.aircraft.departure.delay for s in self.generate(settings, start)[2]],
        )

    def test_other_flows_schedule_within_30_minutes(self):
        operations = dict.fromkeys(OPERATIONS, 0)
        operations["departures"] = 1
        types = dict.fromkeys(AIRCRAFT_TYPES, 0)
        types["small fixed-wing"] = 1
        for volume, hour in (("moderate", 20), ("heavy", 12)):
            with self.subTest(volume=volume, utc_hour=hour):
                start = datetime(2026, 11, 15, hour, 0, tzinfo=UTC)
                strips = self.generate(
                    GeneratorSettings(4, volume, operations, types), start
                )[2]
                delays = [s.aircraft.departure.delay for s in strips]
                self.assertEqual(delays, sorted(delays))
                self.assertTrue(180 <= delays[0] <= 300)
                self.assertTrue(all(delays[0] <= delay <= 1800 for delay in delays))

    def test_very_light_military_departures_start_and_check_in(self):
        operations = dict.fromkeys(OPERATIONS, 0)
        operations["departures"] = 1
        types = dict.fromkeys(AIRCRAFT_TYPES, 0)
        types["military jets"] = 1
        _, _, strips, _ = self.generate(
            GeneratorSettings(1, "very light", operations, types)
        )
        self.assertEqual(len(strips), 3)
        self.assertGreater(
            len({s.aircraft.aircraft_model.aircraft_type for s in strips}), 1
        )
        first = strips[0].aircraft
        delay = first.departure.delay
        self.assertTrue(180 <= delay <= 300)
        first.update_position(delay - 1)
        self.assertEqual(first.departure.state, "waiting")
        first.update_position(90)
        self.assertTrue(first.departure.airborne)
        self.assertIn("282.325", first.departure.check_in)

    def test_overnight_reduces_departure_share(self):
        operations = dict.fromkeys(OPERATIONS, 0)
        operations["departures"] = operations["enroute"] = 1
        types = dict.fromkeys(AIRCRAFT_TYPES, 0)
        types["small fixed-wing"] = 1
        day = datetime(2026, 11, 15, 20, tzinfo=UTC)
        night = datetime(2026, 11, 15, 8, tzinfo=UTC)
        counts = []
        for start in (day, night):
            counts.append(
                sum(
                    sum(
                        s.aircraft.departure is not None
                        for s in self.generate(
                            GeneratorSettings(seed, "heavy", operations, types), start
                        )[2]
                    )
                    for seed in range(20)
                )
            )
        self.assertGreater(counts[0], counts[1])


if __name__ == "__main__":
    unittest.main()
