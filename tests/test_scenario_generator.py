import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from types import SimpleNamespace
from unittest.mock import Mock, patch

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
from locations.Yuma.Scenarios.yuma import (
    assign_incoming_controller,
    create_yuma_scenario,
)
from simulator.core.aircraft import MIN_ENTRY_SEPARATION_NM, advance_aircraft_entry
from simulator.core.atc import FlightPlan, RadarControlState, TrackingPosition
from simulator.core.clearances import is_airborne
from simulator.display.flight_strips import FlightStripPanel
from simulator.display.radar import RadarDisplay, RadarReturnManager, RadarSweep
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
                expected = (
                    TrackingPosition.LOS_ANGELES
                    if strip.aircraft.altitude > 230
                    or strip.aircraft.lon <= -114.6056
                    else TrackingPosition.ALBUQUERQUE
                )
                self.assertEqual(track.owner, expected)
                self.assertEqual(track.communications_owner, track.owner)
                self.assertEqual(track.handoff_target, TrackingPosition.YUMA)
                self.assertEqual(track.radar_return_state, RadarControlState.INCOMING)
            else:
                self.assertEqual(track.owner, TrackingPosition.YUMA)
                self.assertEqual(track.communications_owner, TrackingPosition.YUMA)
                self.assertEqual(
                    track.radar_return_state, RadarControlState.UNCONTROLLED
                )

    def test_generated_inbound_ifr_offers_handoff_vfr_remains_local(self):
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
                self.assertFalse(aircraft.track.identification_confirmation_due)
                if aircraft.flight_rules == "IFR":
                    self.assertIn(
                        aircraft.track.owner,
                        (TrackingPosition.LOS_ANGELES, TrackingPosition.ALBUQUERQUE),
                    )
                    self.assertEqual(aircraft.track.communications_owner, aircraft.track.owner)
                    self.assertEqual(aircraft.track.handoff_target, TrackingPosition.YUMA)
                    self.assertEqual(aircraft.track.radar_return_state, RadarControlState.INCOMING)
                else:
                    self.assertEqual(aircraft.track.owner, TrackingPosition.YUMA)
                    self.assertEqual(aircraft.track.communications_owner, TrackingPosition.YUMA)
                    self.assertIsNone(aircraft.track.handoff_target)
                    self.assertEqual(aircraft.track.radar_return_state, RadarControlState.UNCONTROLLED)
            ifr = next(s.aircraft for s in strips if s.aircraft.flight_rules == "IFR")
            ifr.track.accept(TrackingPosition.YUMA)
            ifr.track.transfer_communications()
            ifr.track.confirm_identification()
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

    def test_incoming_center_selection_at_longitude_and_altitude_boundaries(self):
        _, facility, strips = create_yuma_scenario()
        strip = next(s for s in strips if s.aircraft.id == "A3")
        for offset, altitude, expected in (
            (-0.01, 230, TrackingPosition.LOS_ANGELES),
            (0, 230, TrackingPosition.LOS_ANGELES),
            (0.01, 230, TrackingPosition.ALBUQUERQUE),
            (0.01, 231, TrackingPosition.LOS_ANGELES),
        ):
            with self.subTest(offset=offset, altitude=altitude):
                strip.aircraft.lon = facility.location.longitude + offset
                strip.aircraft.altitude = altitude
                strip.aircraft.track.cancel()
                assign_incoming_controller(strip, facility)
                self.assertEqual(strip.aircraft.track.owner, expected)
                self.assertEqual(strip.aircraft.track.handoff_target, TrackingPosition.YUMA)

    def test_ifr_departures_do_not_receive_incoming_handoffs(self):
        operations = dict.fromkeys(OPERATIONS, 0)
        operations["departures"] = 1
        types = dict.fromkeys(AIRCRAFT_TYPES, 0)
        types["air carriers"] = 1
        aircraft_list, _, _, _ = self.generate(
            GeneratorSettings(7, "light", operations, types)
        )
        for plane in aircraft_list.aircraft_list:
            self.assertEqual(plane.flight_rules, "IFR")
            self.assertEqual(plane.track.owner, TrackingPosition.YUMA)
            self.assertIsNone(plane.track.handoff_target)
            self.assertFalse(plane.incoming_checkin_pending)

    def test_scheduled_handoff_waits_for_unblocked_entry_and_is_not_repeated(self):
        operations = dict.fromkeys(OPERATIONS, 0)
        operations["approaches"] = 1
        types = dict.fromkeys(AIRCRAFT_TYPES, 0)
        types["air carriers"] = 1
        aircraft_list, _, _, _ = self.generate(
            GeneratorSettings(7, "light", operations, types)
        )
        first, second, *_ = aircraft_list.aircraft_list
        self.assertEqual(first.track.handoff_target, TrackingPosition.YUMA)
        self.assertIsNone(second.track.handoff_target)
        self.assertTrue(second.incoming_handoff_on_entry)
        first.lat, first.lon = second.lat, second.lon
        second.entry_remaining = 1
        advance_aircraft_entry(second, aircraft_list.aircraft_list, 1)
        self.assertEqual(second.entry_remaining, 0)
        self.assertIsNone(second.track.handoff_target)
        first.lat += 1
        advance_aircraft_entry(second, aircraft_list.aircraft_list, 0)
        self.assertIsNone(second.track.handoff_target)
        advance_aircraft_entry(second, aircraft_list.aircraft_list, 1)
        self.assertIsNone(second.entry_remaining)
        self.assertEqual(second.track.handoff_target, TrackingPosition.YUMA)
        self.assertFalse(second.incoming_handoff_on_entry)
        second.track.cancel()
        advance_aircraft_entry(second, aircraft_list.aircraft_list, 10)
        self.assertIsNone(second.track.handoff_target)

    def test_inbound_checkin_waits_for_handoff_comms_and_30_nm(self):
        operations = dict.fromkeys(OPERATIONS, 0)
        operations["enroute"] = 1
        for category, channel, frequency in (
            ("air carriers", "approach_low", "124.700"),
            ("military jets", "approach_high", "371.975"),
        ):
            with self.subTest(category=category):
                types = dict.fromkeys(AIRCRAFT_TYPES, 0)
                types[category] = 1
                aircraft_list, facility, _, _ = self.generate(
                    GeneratorSettings(7, "single", operations, types)
                )
                aircraft = aircraft_list.aircraft_list[0]
                distance = [29.9]
                display = SimpleNamespace(
                    aircraft_list=aircraft_list, atc_facility=facility,
                    secondary_radar_returns=[], departure_checkins=[],
                    reported_departures=set(), selected_aircraft_id=None,
                    sweep=RadarSweep(), radar_return_manager=RadarReturnManager(),
                    display_type=RadarDisplay.STARS, ARTS_IIE=RadarDisplay.ARTS_IIE,
                    secondary_update_elapsed=0, emergency_flash_elapsed=0,
                    voice_audio=Mock(),
                    calculate_range_and_bearing=lambda lat, lon, d=distance: (d[0], 0),
                )
                display.capture_secondary_radar_returns = lambda d=display: (
                    RadarDisplay.capture_secondary_radar_returns(d)
                )
                with patch.object(RadarDisplay, "process_voice"):
                    RadarDisplay.on_update(display, 1)
                    aircraft.track.accept(TrackingPosition.YUMA)
                    RadarDisplay.on_update(display, 1)
                    aircraft.track.transfer_communications()
                    distance[0] = 30.1
                    RadarDisplay.on_update(display, 1)
                    self.assertTrue(aircraft.incoming_checkin_pending)
                    display.voice_audio.speak.assert_not_called()
                    distance[0] = 30
                    RadarDisplay.on_update(display, 0)
                    display.voice_audio.speak.assert_not_called()
                    RadarDisplay.on_update(display, 1)
                    RadarDisplay.on_update(display, 1)
                self.assertFalse(aircraft.incoming_checkin_pending)
                self.assertTrue(aircraft.track.identification_confirmation_due)
                self.assertEqual(aircraft.radio_channel, channel)
                reply = display.voice_audio.speak.call_args.args[0]
                self.assertEqual(display.voice_audio.speak.call_count, 1)
                self.assertEqual(reply.channel, channel)
                self.assertIn("YUMA APPROACH", reply.text)
                self.assertIn(frequency, reply.text)
                self.assertEqual(len(display.departure_checkins), 1)

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

    def test_light_inbound_traffic_enters_five_minutes_apart(self):
        operations = dict.fromkeys(OPERATIONS, 0)
        operations["approaches"] = 5
        aircraft_list, facility, strips, _ = self.generate(
            GeneratorSettings(0, "light", operations)
        )
        planes = aircraft_list.aircraft_list
        self.assertEqual([p.entry_remaining for p in planes], [None, 300, 600, 900, 1200])
        initial = [(p.lat, p.lon) for p in planes]
        with patch("simulator.display.flight_strips.arcade.Text"):
            panel = FlightStripPanel(strips, aircraft_list)
        self.assertEqual(panel.active_strips(), [strips[0]])
        display = type("Display", (), {})()
        display.aircraft_list = aircraft_list
        display.secondary_radar_returns = []
        RadarDisplay.capture_secondary_radar_returns(display)
        self.assertEqual([s.aircraft_id for s in display.secondary_radar_returns], [planes[0].id])
        with self.assertRaisesRegex(ValueError, "unambiguous"):
            handle_transmission(
                f"{planes[1].callsign} ident",
                planes,
                facility,
                {planes[1].radio_channel},
            )

        for elapsed in range(5, 1201, 5):
            aircraft_list.update_positions(5)
            for index, plane in enumerate(planes):
                if elapsed < index * 300:
                    self.assertFalse(is_airborne(plane))
                    self.assertEqual((plane.lat, plane.lon), initial[index])
                elif elapsed == index * 300 and index:
                    self.assertTrue(is_airborne(plane))
                    for other in planes[:index]:
                        if is_airborne(other):
                            self.assertGreaterEqual(
                                NavigationalCoordinateSystem.calculate_distance(
                                    plane.lat, plane.lon, other.lat, other.lon
                                ),
                                MIN_ENTRY_SEPARATION_NM,
                            )
            if elapsed % 300 == 0:
                self.assertEqual(
                    panel.active_strips(),
                    [
                        strip
                        for strip in strips
                        if strip.active and strip.aircraft.entry_remaining is None
                    ],
                )

    def test_occupied_entry_delays_following_arrivals(self):
        operations = dict.fromkeys(OPERATIONS, 0)
        operations["approaches"] = 1
        aircraft_list, _, _, _ = self.generate(GeneratorSettings(2, "light", operations))
        first, second, third, *_ = aircraft_list.aircraft_list
        first.lat, first.lon = second.lat, second.lon
        second.entry_remaining = 10
        third.entry_remaining = 310
        self.assertEqual(advance_aircraft_entry(second, aircraft_list.aircraft_list, 60), 0)
        self.assertEqual(second.entry_remaining, 0)
        self.assertEqual(third.entry_remaining, 360)
        self.assertEqual(advance_aircraft_entry(third, aircraft_list.aircraft_list, 60), 0)
        self.assertEqual(third.entry_remaining, 300)
        self.assertEqual(advance_aircraft_entry(second, aircraft_list.aircraft_list, 30), 0)
        self.assertEqual(advance_aircraft_entry(third, aircraft_list.aircraft_list, 30), 0)
        self.assertEqual(third.entry_remaining, 300)
        first.lat += 1
        self.assertEqual(advance_aircraft_entry(second, aircraft_list.aircraft_list, 1), 1)
        self.assertIsNone(second.entry_remaining)
        self.assertEqual(advance_aircraft_entry(third, aircraft_list.aircraft_list, 1), 0)
        self.assertEqual(third.entry_remaining, 299)

    def test_light_mixed_traffic_staggers_only_inbound_aircraft(self):
        aircraft_list, _, _, _ = self.generate(GeneratorSettings(0, "light"))
        departures = [p for p in aircraft_list.aircraft_list if p.departure is not None]
        inbound = [p for p in aircraft_list.aircraft_list if p.departure is None]
        self.assertTrue(departures)
        self.assertEqual(
            [p.entry_remaining for p in inbound], [None, 300, 600, 900]
        )
        self.assertTrue(all(p.entry_remaining is None for p in departures))
        moderate, _, _, _ = self.generate(GeneratorSettings(0, "moderate"))
        self.assertTrue(
            all(p.entry_remaining is None for p in moderate.aircraft_list)
        )

    def test_seeded_arrival_waits_until_its_entry_point_is_clear(self):
        operations = dict.fromkeys(OPERATIONS, 0)
        operations["approaches"] = 1
        aircraft_list, _, _, _ = self.generate(GeneratorSettings(2, "light", operations))
        planes = aircraft_list.aircraft_list
        previous = {planes[0].id}
        entries = []
        for elapsed in range(5, 1801, 5):
            aircraft_list.update_positions(5)
            active = {p.id for p in planes if p.entry_remaining is None}
            for plane in planes:
                if plane.id in active - previous:
                    entries.append(elapsed)
                    for other in planes:
                        if other.id in previous and is_airborne(other):
                            self.assertGreaterEqual(
                                NavigationalCoordinateSystem.calculate_distance(
                                    plane.lat, plane.lon, other.lat, other.lon
                                ),
                                MIN_ENTRY_SEPARATION_NM,
                            )
            previous = active
        self.assertEqual(entries[:3], [300, 600, 900])
        self.assertGreater(entries[3], 1200)

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
