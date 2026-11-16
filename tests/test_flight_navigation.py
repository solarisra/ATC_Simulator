import json
import random
import unittest
from collections import Counter
from itertools import pairwise
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from shapely.geometry import LineString, Point, box, shape
from shapely.ops import unary_union
from shapely.prepared import prep

from Locations.Yuma.Scenarios.sample_data import (
    ACTIVE_SAMPLE_AIRCRAFT,
    CIVILIAN_AIRPORTS,
    CIVILIAN_ELIGIBLE_AIRPORTS,
    CIVILIAN_ROUTE_TEMPLATES,
    INACTIVE_SAMPLE_AIRCRAFT,
    SAMPLE_PLANS,
)
from Locations.Yuma.Scenarios.yuma import (
    _choose_civilian_airports,
    create_yuma_scenario,
)
from simulator.core.aircraft import AircraftList
from simulator.core.aircraft_models import boeing_767_freighter
from simulator.core.atc import ATCFacility, FlightPlan, FlightStrip
from simulator.display.radar import RadarDisplay, RadarReturnManager, RadarSweep
from simulator.navigation.flight_navigation import (
    FlightPlanGuidance,
    NavigationData,
    Waypoint,
    _bearing,
    _initial_leg,
)
from simulator.navigation.navmath import NavigationalCoordinateSystem
from tests.test_aircraft import make_aircraft


class FlightNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = NavigationData()

    def test_airway_resolution_uses_fixes_not_similarly_named_airports(self):
        plan = FlightPlan("T", "KNJK", "KLUF", "IPL V66 GBN", 13000, 400)
        route = self.data.resolve(plan)
        names = [point.name for point in route]
        self.assertEqual(names[:3], ["KNJK", "IPL", "ARGUS"])
        self.assertLess(names.index("BZA"), names.index("GBN"))
        self.assertEqual(names[-1], "KLUF")
        ipl = route[1]
        airport = self.data.airport("KIPL")
        self.assertGreater(
            NavigationalCoordinateSystem.calculate_distance(
                ipl.latitude, ipl.longitude, airport.latitude, airport.longitude
            ),
            5,
        )

    def test_unrecognized_or_disconnected_routes_fail_explicitly(self):
        for route in (
            "I-8",
            "HOLTVILLE",
            "RAMONA BORREGO SPRINGS",
            "BZA V66 HIDEN",
            "MOHAK ARLIN4",
        ):
            with self.subTest(route=route), self.assertRaises(ValueError):
                self.data.resolve(FlightPlan("T", "KNYL", "KSDL", route, 9000, 100))

    def test_all_sample_routes_use_identifiers_and_resolve(self):
        for identifier, fields in SAMPLE_PLANS.items():
            with self.subTest(aircraft=identifier):
                self.assertNotIn("KRNM", fields[2].split())
                for token in fields[2].split():
                    self.assertRegex(token, r"^[A-Z0-9]{3,5}$")
                route = self.data.resolve(FlightPlan(identifier, *fields))
                self.assertEqual(route[0].name, fields[0])
                self.assertEqual(route[-1].name, fields[1])

    def test_ifr_routes_end_at_airports_and_use_main_course_altitudes(self):
        plans = [
            (aircraft[0], SAMPLE_PLANS[aircraft[0]])
            for aircraft in ACTIVE_SAMPLE_AIRCRAFT + INACTIVE_SAMPLE_AIRCRAFT
            if aircraft[11] == "IFR"
        ]
        plans.extend(
            (f"A8-{airport}", ("KNYL", airport, route, altitude, 300))
            for airport, (route, altitude) in CIVILIAN_ROUTE_TEMPLATES["A8"].items()
        )
        for identifier, fields in plans:
            with self.subTest(flight=identifier):
                plan = FlightPlan(identifier, *fields)
                route = self.data.resolve(plan)
                self.assertEqual(route[-1], self.data.airport(plan.destination))
                self.assertLessEqual(
                    NavigationalCoordinateSystem.calculate_distance(
                        route[-2].latitude,
                        route[-2].longitude,
                        route[-1].latitude,
                        route[-1].longitude,
                    ),
                    65,
                )
                for start, end in pairwise(route):
                    self.assertLessEqual(
                        NavigationalCoordinateSystem.calculate_distance(
                            start.latitude, start.longitude, end.latitude, end.longitude
                        ),
                        150,
                    )
                if plan.origin == plan.destination:
                    continue
                origin = self.data.airport(plan.origin)
                true_course = _bearing(origin.latitude, origin.longitude, route[-1])
                self.assertEqual(plan.altitude % 1000, 0)
                # The included route-fix variations are roughly 7-16 degrees east.
                for east_variation in (7, 16):
                    magnetic_course = (true_course - east_variation) % 360
                    self.assertEqual(
                        (plan.altitude // 1000) % 2,
                        1 if magnetic_course < 180 else 0,
                        (identifier, magnetic_course, plan.altitude),
                    )

    def test_miramar_arrival_joins_route_west_of_yuma(self):
        _, _, strips = create_yuma_scenario()
        aircraft = next(s.aircraft for s in strips if s.aircraft.id == "A12")
        route = aircraft.flight_guidance.route
        self.assertEqual(
            [point.name for point in route], ["KNKX", "KUMBA", "KIPL", "BZA", "KNYL"]
        )
        self.assertLess(aircraft.lon, route[-1].longitude)
        self.assertEqual(route[aircraft.flight_guidance.next_index].name, "KIPL")

    def test_initial_leg_uses_nearest_segment_without_returning_to_origin(self):
        route = [
            Waypoint("A", 0, 0),
            Waypoint("B", 0, 1),
            Waypoint("C", 0, 2),
        ]
        self.assertEqual(_initial_leg(route, 0.2, 1.5), 2)
        self.assertEqual(_initial_leg(route, 0, 1), 2)
        self.assertEqual(_initial_leg(route, 0, 3), 2)

    def test_guidance_tracks_route_climbs_and_lands(self):
        aircraft = make_aircraft(lat=0, lon=0.05, heading=0, altitude=20, speed=100)
        plan = FlightPlan("A1", "A", "C", "B", 5000, 110)
        strip = FlightStrip("A1", aircraft, plan)
        points = [
            Waypoint("A", 0, 0, 0),
            Waypoint("B", 0, 0.4),
            Waypoint("C", 0, 1, 0),
        ]
        aircraft.flight_guidance = FlightPlanGuidance(
            strip, SimpleNamespace(resolve=lambda plan, points=points: points)
        )

        aircraft.update_position(20)
        self.assertAlmostEqual(aircraft.heading, 60, delta=0.1)
        self.assertAlmostEqual(aircraft.altitude, 21.5)
        self.assertEqual(aircraft.speed, 100)
        self.assertEqual(aircraft.flight_guidance.next_index, 1)

        aircraft.update_position(1400)
        self.assertEqual(aircraft.flight_guidance.next_index, 2)
        self.assertFalse(aircraft.landed)
        self.assertGreater(aircraft.altitude * 100, 300)
        aircraft.update_position(4000)
        self.assertEqual(aircraft.flight_guidance.next_index, 2)
        self.assertTrue(aircraft.landed)
        self.assertFalse(strip.active)
        self.assertEqual((aircraft.lat, aircraft.lon, aircraft.speed), (0, 1, 0))
        self.assertEqual(aircraft.altitude, 0)

    def test_controller_vector_direct_and_resume_preserve_remaining_route(self):
        aircraft = make_aircraft(lat=0, lon=0.05, heading=90, altitude=20, speed=100)
        plan = FlightPlan("A1", "A", "D", "B C", 5000, 110)
        strip = FlightStrip("A1", aircraft, plan)
        points = [
            Waypoint("A", 0, 0, 0),
            Waypoint("B", 0, 0.4),
            Waypoint("C", 0, 0.8),
            Waypoint("D", 0, 1.2, 0),
        ]
        guidance = FlightPlanGuidance(
            strip, SimpleNamespace(resolve=lambda plan: points)
        )
        aircraft.flight_guidance = guidance
        guidance.assign_heading(360)
        aircraft.update_position(100)
        self.assertAlmostEqual(aircraft.heading, 0)
        self.assertEqual(guidance.next_index, 1)
        self.assertFalse(aircraft.landed)
        guidance.resume_route()
        aircraft.update_position(10)
        self.assertGreater(aircraft.heading, 0)
        guidance.direct_to("C")
        self.assertEqual(guidance.next_index, 2)
        self.assertIsNone(guidance.vector_heading)
        with self.assertRaisesRegex(ValueError, "remaining route"):
            guidance.direct_to("B")
        with self.assertRaisesRegex(ValueError, "heading vector"):
            guidance.resume_route()
        self.assertEqual(plan.route, "B C")

    def test_assigned_altitude_persists_and_prevents_automatic_landing(self):
        aircraft = make_aircraft(lat=0, lon=0.05, altitude=20, speed=100)
        strip = FlightStrip(
            "A1", aircraft, FlightPlan("A1", "A", "B", "DCT", 5000, 100)
        )
        points = [Waypoint("A", 0, 0, 0), Waypoint("B", 0, 0.2, 0)]
        guidance = FlightPlanGuidance(
            strip, SimpleNamespace(resolve=lambda plan: points)
        )
        aircraft.flight_guidance = guidance
        guidance.assign_altitude(3000)
        aircraft.update_position(600)
        self.assertEqual(aircraft.altitude, 30)
        self.assertFalse(aircraft.landed)
        self.assertTrue(strip.active)
        self.assertEqual(strip.assigned_altitude, "")
        guidance.assign_heading(270)
        aircraft.update_position(30)
        self.assertEqual(aircraft.altitude, 30)
        guidance.resume_route()
        guidance.clear_altitude()
        aircraft.update_position(6000)
        self.assertTrue(aircraft.landed)
        with self.assertRaisesRegex(ValueError, "No assigned altitude"):
            guidance.clear_altitude()

    def test_vector_cancels_pending_automatic_approach_braking(self):
        aircraft = make_aircraft(lat=0, lon=0, altitude=20, speed=100)
        strip = FlightStrip(
            "A1", aircraft, FlightPlan("A1", "A", "B", "DCT", 5000, 100)
        )
        points = [Waypoint("A", 0, 0, 0), Waypoint("B", 0, 0.1, 0)]
        guidance = FlightPlanGuidance(
            strip, SimpleNamespace(resolve=lambda plan: points)
        )
        aircraft.flight_guidance = guidance
        aircraft.update_position(1)
        self.assertTrue(guidance.approach)
        self.assertIsNotNone(aircraft.target_speed)
        guidance.assign_heading(360)
        self.assertIsNone(aircraft.target_speed)
        speed = aircraft.speed
        aircraft.update_position(10)
        self.assertEqual(aircraft.speed, speed)

    def test_revised_route_is_resolved_and_invalid_edit_is_not_ignored(self):
        aircraft = make_aircraft(lat=0, lon=0.05, speed=100)
        plan = FlightPlan("A1", "A", "B", "DCT", 5000, 100)
        strip = FlightStrip("A1", aircraft, plan)
        points = [Waypoint("A", 0, 0, 0), Waypoint("B", 0, 1, 0)]
        revised = [points[0], Waypoint("NEW", 0.1, 0.5), points[1]]

        def resolve(plan):
            if plan.route == "DCT":
                return points
            if plan.route == "NEW":
                return revised
            raise ValueError("Invalid revised route")

        aircraft.flight_guidance = FlightPlanGuidance(
            strip, SimpleNamespace(resolve=resolve)
        )
        plan.update_route("NEW")
        aircraft.update_position(1)
        self.assertEqual(aircraft.flight_guidance.route, revised)
        plan.update_route("INVALID")
        with self.assertRaisesRegex(ValueError, "Invalid revised route"):
            aircraft.update_position(1)

    def test_landing_deactivates_strip_through_both_update_paths(self):
        for radar_update in (False, True):
            with self.subTest(radar_update=radar_update):
                aircraft = make_aircraft(
                    lat=0, lon=0, heading=90, altitude=5, speed=100
                )
                strip = FlightStrip(
                    "A1", aircraft, FlightPlan("A1", "A", "B", "DCT", 500, 100)
                )
                points = [Waypoint("A", 0, 0, 0), Waypoint("B", 0, 0.1, 0)]
                aircraft.flight_guidance = FlightPlanGuidance(
                    strip, SimpleNamespace(resolve=lambda plan, points=points: points)
                )
                aircraft_list = AircraftList()
                aircraft_list.add_aircraft([aircraft])
                facility = ATCFacility("Test", {"lat": 0, "lon": 0})
                aircraft_list.assign_to_atc_facility(facility)
                display = SimpleNamespace(
                    aircraft_list=aircraft_list,
                    atc_facility=facility,
                    secondary_radar_returns=[],
                    selected_aircraft_id=None,
                    sweep=RadarSweep(),
                    radar_return_manager=RadarReturnManager(),
                    display_type=RadarDisplay.STARS,
                    ARTS_IIE=RadarDisplay.ARTS_IIE,
                    secondary_update_elapsed=0,
                    emergency_flash_elapsed=0,
                    calculate_range_and_bearing=lambda lat, lon: (0, 0),
                )
                display.capture_secondary_radar_returns = lambda display=display: (
                    RadarDisplay.capture_secondary_radar_returns(display)
                )
                display.capture_secondary_radar_returns()
                self.assertEqual(len(display.secondary_radar_returns), 1)
                if radar_update:
                    RadarDisplay.on_update(display, 1000)
                else:
                    aircraft_list.update_positions(1000)
                    display.capture_secondary_radar_returns()
                self.assertTrue(aircraft.landed)
                self.assertFalse(strip.active)
                self.assertEqual(display.secondary_radar_returns, [])

    def test_departures_wait_then_check_in_once_and_appear_on_radar(self):
        aircraft_list, facility, strips = create_yuma_scenario()
        departures = [s for s in strips if s.flight_plan.origin == "KNYL"]
        self.assertEqual(len(departures), 3)
        airport = self.data.airport("KNYL")
        for strip in departures:
            aircraft = strip.aircraft
            self.assertTrue(strip.active)
            self.assertEqual(aircraft.departure.state, "waiting")
            self.assertEqual(
                (aircraft.lat, aircraft.lon), (airport.latitude, airport.longitude)
            )
            self.assertEqual(aircraft.altitude * 100, airport.elevation)
            self.assertEqual(aircraft.speed, 0)
            self.assertEqual(aircraft.flight_guidance.next_index, 1)

        display = SimpleNamespace(
            aircraft_list=aircraft_list,
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
        self.assertEqual(len(display.secondary_radar_returns), 7)
        RadarDisplay.on_update(display, 29)
        self.assertTrue(
            all(s.aircraft.departure.state == "waiting" for s in departures)
        )
        self.assertTrue(all(s.aircraft.speed == 0 for s in departures))
        RadarDisplay.on_update(display, 31)
        self.assertEqual(departures[0].aircraft.departure.state, "takeoff")
        self.assertEqual(departures[0].aircraft.altitude * 100, airport.elevation)
        self.assertGreater(departures[0].aircraft.speed, 0)
        self.assertEqual(departures[2].aircraft.departure.state, "waiting")
        display.voice_audio = Mock()
        with patch.object(RadarDisplay, "process_voice"):
            RadarDisplay.on_update(display, 115)
        self.assertTrue(all(s.aircraft.departure.airborne for s in departures))
        self.assertEqual(len(display.secondary_radar_returns), 10)
        self.assertEqual(len(display.departure_checkins), 3)
        self.assertEqual(
            [message.split(":")[0] for message in display.departure_checkins],
            ["LIFE12", "N380CJ", "REACH47"],
        )
        self.assertTrue(
            all("YUMA DEPARTURE" in msg for msg in display.departure_checkins)
        )
        replies = [call.args[0] for call in display.voice_audio.speak.call_args_list]
        self.assertEqual(len(replies), 3)
        for reply, message in zip(replies, display.departure_checkins):
            self.assertIn(", ON ", message)
            self.assertIn(", on ", reply.text)
            self.assertRegex(message, r"\d+ FT, (CLIMBING|DESCENDING|LEVEL) \d+ FT$")
            self.assertRegex(
                reply.text, r"\d+ feet, (CLIMBING|DESCENDING|LEVEL) \d+ feet$"
            )
            self.assertIn(reply.channel, ("departure_low", "departure_high"))
            self.assertIn(
                "125.500" if reply.channel == "departure_low" else "282.325", message
            )
            self.assertIn(
                "125.500" if reply.channel == "departure_low" else "282.325",
                reply.text,
            )
        with patch.object(RadarDisplay, "process_voice"):
            RadarDisplay.on_update(display, 1)
        self.assertEqual(len(display.departure_checkins), 3)
        self.assertEqual(display.voice_audio.speak.call_count, 3)

    def test_departures_also_progress_through_aircraft_list_updates(self):
        aircraft_list, _, strips = create_yuma_scenario()
        departure = next(s.aircraft for s in strips if s.aircraft.id == "A8")
        aircraft_list.update_positions(29)
        self.assertEqual(departure.departure.state, "waiting")
        aircraft_list.update_positions(100)
        self.assertTrue(departure.departure.airborne)
        self.assertIn("N380CJ", departure.departure.check_in)

    def test_heavy_airline_departure_checkin_is_displayed_and_spoken(self):
        for callsign, spoken in (("AAL381", "American"), ("AMF381", "Am Flight")):
            with self.subTest(callsign=callsign):
                _, facility, strips = create_yuma_scenario()
                aircraft = next(s.aircraft for s in strips if s.aircraft.id == "A8")
                aircraft.callsign = callsign
                aircraft.aircraft_model = boeing_767_freighter
                aircraft.departure.state = "airborne"
                aircraft.departure.record_airborne(aircraft, 15)
                aircraft.update_position = Mock()
                display = SimpleNamespace(
                    aircraft_list=SimpleNamespace(aircraft_list=[aircraft]),
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
                    voice_audio=Mock(),
                )
                with patch.object(RadarDisplay, "process_voice"):
                    RadarDisplay.on_update(display, 0)
                self.assertTrue(display.departure_checkins[0].startswith(f"{callsign}H:"))
                reply = display.voice_audio.speak.call_args.args[0]
                self.assertTrue(reply.text.startswith(f"{spoken} three eight one heavy:"))
                self.assertEqual(aircraft.callsign, callsign)

    def test_departure_checkin_uses_controller_assigned_altitude(self):
        _, _, strips = create_yuma_scenario()
        aircraft = next(s.aircraft for s in strips if s.aircraft.id == "A8")
        for _ in range(200):
            aircraft.update_position(1)
            if aircraft.departure.airborne:
                break
        self.assertTrue(aircraft.departure.airborne)
        self.assertIsNone(aircraft.departure.check_in)
        aircraft.flight_guidance.assign_altitude(6000)
        aircraft.update_position(15)
        self.assertIn("CLIMBING 6000 FT", aircraft.departure.check_in)

    @staticmethod
    def mexico_boundary():
        path = (
            Path(__file__).resolve().parents[1]
            / "GIS_JSON"
            / "us-state-boundaries.geojson"
        )
        with path.open(encoding="utf-8") as file:
            features = json.load(file)["features"]
        states = unary_union(
            [
                shape(feature["geometry"])
                for feature in features
                if feature["properties"]["stusab"] in ("CA", "AZ")
            ]
        )
        return prep(box(-119, 25, -108, 32.72).difference(states))

    def test_civilian_airport_weights_and_eligibility(self):
        rng = random.Random(120)
        counts = Counter()
        observed = set()
        for _ in range(10000):
            choices = _choose_civilian_airports(rng)
            self.assertEqual(set(choices), set(CIVILIAN_ELIGIBLE_AIRPORTS))
            for identifier, airport in choices.items():
                self.assertIn(airport, CIVILIAN_ELIGIBLE_AIRPORTS[identifier])
                observed.add((identifier, airport))
            special = [
                CIVILIAN_AIRPORTS[airport][0]
                for airport in choices.values()
                if CIVILIAN_AIRPORTS[airport][0] != "primary"
            ]
            self.assertLessEqual(len(special), 1)
            counts[special[0] if special else "primary"] += 1
        self.assertTrue(7800 <= counts["primary"] <= 8200, counts)
        self.assertTrue(1350 <= counts["occasional"] <= 1650, counts)
        self.assertTrue(400 <= counts["rare"] <= 600, counts)
        self.assertEqual(
            observed,
            {
                (identifier, airport)
                for identifier, airports in CIVILIAN_ELIGIBLE_AIRPORTS.items()
                for airport in airports
            },
        )
        self.assertEqual(
            _choose_civilian_airports(random.Random(99)),
            _choose_civilian_airports(random.Random(99)),
        )

    def test_all_civilian_routes_are_suitable_and_stay_north_of_mexico(self):
        mexico = self.mexico_boundary()
        for identifier, airports in CIVILIAN_ELIGIBLE_AIRPORTS.items():
            for airport in airports:
                with self.subTest(aircraft=identifier, airport=airport):
                    choices = {
                        aircraft_id: eligible[0]
                        for aircraft_id, eligible in CIVILIAN_ELIGIBLE_AIRPORTS.items()
                    }
                    choices[identifier] = airport
                    with patch(
                        "Locations.Yuma.Scenarios.yuma._choose_civilian_airports",
                        return_value=choices,
                    ):
                        _, _, strips = create_yuma_scenario()
                    strip = next(s for s in strips if s.aircraft.id == identifier)
                    plan, aircraft = strip.flight_plan, strip.aircraft
                    self.assertIn(airport, (plan.origin, plan.destination))
                    self.assertNotIn("KRNM", plan.route.split())
                    for token in plan.route.split():
                        self.assertRegex(token, r"^[A-Z0-9]{3,5}$")
                    route = aircraft.flight_guidance.route
                    distance = 0
                    for start, end in pairwise(route):
                        distance += NavigationalCoordinateSystem.calculate_distance(
                            start.latitude, start.longitude, end.latitude, end.longitude
                        )
                        self.assertFalse(
                            mexico.intersects(
                                LineString(
                                    [
                                        (start.longitude, start.latitude),
                                        (end.longitude, end.latitude),
                                    ]
                                )
                            )
                        )
                    self.assertLess(distance, aircraft.aircraft_model.max_range)
                    self.assertFalse(mexico.contains(Point(aircraft.lon, aircraft.lat)))
                    for _ in range(2000):
                        previous = aircraft.lon, aircraft.lat
                        aircraft.update_position(10)
                        self.assertFalse(
                            mexico.intersects(
                                LineString([previous, (aircraft.lon, aircraft.lat)])
                            )
                        )
                        if aircraft.landed:
                            break
                    self.assertTrue(aircraft.landed)

    def test_startup_routes_and_flights_remain_north_of_mexico(self):
        mexico = self.mexico_boundary()
        for fields in INACTIVE_SAMPLE_AIRCRAFT:
            with self.subTest(inactive_aircraft=fields[0]):
                self.assertFalse(mexico.contains(Point(fields[10], fields[9])))
        for identifier, fields in SAMPLE_PLANS.items():
            route = self.data.resolve(FlightPlan(identifier, *fields))
            with self.subTest(route=identifier):
                for start, end in pairwise(route):
                    self.assertFalse(
                        mexico.intersects(
                            LineString(
                                [
                                    (start.longitude, start.latitude),
                                    (end.longitude, end.latitude),
                                ]
                            )
                        )
                    )
        _, _, strips = create_yuma_scenario()
        for strip in strips:
            aircraft = strip.aircraft
            route = aircraft.flight_guidance.route
            with self.subTest(aircraft=aircraft.id):
                self.assertFalse(mexico.contains(Point(aircraft.lon, aircraft.lat)))
                for start, end in pairwise(route):
                    leg = LineString(
                        [
                            (start.longitude, start.latitude),
                            (end.longitude, end.latitude),
                        ]
                    )
                    self.assertFalse(mexico.intersects(leg))
                for _ in range(2000):
                    previous = aircraft.lon, aircraft.lat
                    aircraft.update_position(10)
                    track = LineString([previous, (aircraft.lon, aircraft.lat)])
                    self.assertFalse(mexico.intersects(track))
                    if aircraft.landed:
                        break
                self.assertTrue(aircraft.landed)


if __name__ == "__main__":
    unittest.main()
