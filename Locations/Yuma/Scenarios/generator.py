"""Seeded, destination-based traffic generation for Yuma."""

import random
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from itertools import cycle

from Locations.Yuma.Scenarios.routing import NoSafeRouteError, yuma_router
from Locations.Yuma.Scenarios.sample_data import CIVILIAN_AIRPORTS
from simulator.core import aircraft_models as models
from simulator.core.aircraft import Aircraft, AircraftList, AircraftModel
from simulator.core.atc import ATCFacility, FlightPlan, FlightStrip
from simulator.navigation.departure import Departure
from simulator.navigation.flight_navigation import (
    FlightPlanGuidance,
    NavigationData,
    _bearing,
)
from simulator.navigation.navmath import NavigationalCoordinateSystem

TRAFFIC_LEVELS = {"single": 1, "very light": 3, "light": 5, "moderate": 10, "heavy": 20}
OPERATIONS = ("departures", "approaches", "enroute")
AIRCRAFT_TYPES = (
    "heavies",
    "military jets",
    "helicopters",
    "air carriers",
    "small fixed-wing",
)


@dataclass(frozen=True)
class AircraftProfile:
    model: AircraftModel
    category: str
    callsign: str
    rules: str
    airports: tuple[str, ...]
    civilian: bool
    speed: int


CIVILIAN_DESTINATIONS = tuple(CIVILIAN_AIRPORTS)
MILITARY_DESTINATIONS = ("KNKX", "KNZY", "KNFG", "KNJK", "KLUF", "KNFL")
HELICOPTER_DESTINATIONS = ("KNKX", "KNFG", "KNJK", "KLUF")
PROFILES = (
    AircraftProfile(
        models.cessna_172,
        "small fixed-wing",
        "N",
        "VFR",
        CIVILIAN_DESTINATIONS,
        True,
        110,
    ),
    AircraftProfile(
        models.piper_pa28,
        "small fixed-wing",
        "N",
        "VFR",
        CIVILIAN_DESTINATIONS,
        True,
        110,
    ),
    AircraftProfile(
        models.cessna_208,
        "small fixed-wing",
        "N",
        "VFR",
        CIVILIAN_DESTINATIONS,
        True,
        160,
    ),
    AircraftProfile(
        models.cessna_citation_m2,
        "small fixed-wing",
        "N",
        "IFR",
        CIVILIAN_DESTINATIONS,
        True,
        300,
    ),
    AircraftProfile(
        models.boeing_737,
        "air carriers",
        "AMF",
        "IFR",
        CIVILIAN_DESTINATIONS,
        True,
        300,
    ),
    AircraftProfile(
        models.airbus_a320,
        "air carriers",
        "AAL",
        "IFR",
        CIVILIAN_DESTINATIONS,
        True,
        300,
    ),
    AircraftProfile(
        models.boeing_767_freighter,
        "heavies",
        "FDX",
        "IFR",
        CIVILIAN_DESTINATIONS,
        True,
        330,
    ),
    AircraftProfile(
        models.boeing_b52, "heavies", "DOOM", "IFR", ("KLUF", "KNFL"), False, 400
    ),
    AircraftProfile(
        models.f18e, "military jets", "DEVIL", "IFR", MILITARY_DESTINATIONS, False, 400
    ),
    AircraftProfile(
        models.f16, "military jets", "VIPER", "IFR", MILITARY_DESTINATIONS, False, 400
    ),
    AircraftProfile(
        models.f35c, "military jets", "CAT", "IFR", MILITARY_DESTINATIONS, False, 400
    ),
    AircraftProfile(
        models.av8b_harrier,
        "military jets",
        "SHEEP",
        "IFR",
        MILITARY_DESTINATIONS,
        False,
        350,
    ),
    AircraftProfile(
        models.airbus_h135,
        "helicopters",
        "LIFE",
        "VFR",
        ("KNJK", "KIPL", "KBLH"),
        True,
        110,
    ),
    AircraftProfile(
        models.sikorsky_uh60,
        "helicopters",
        "MERLIN",
        "VFR",
        HELICOPTER_DESTINATIONS,
        False,
        120,
    ),
    AircraftProfile(
        models.boeing_ch46e,
        "helicopters",
        "KNIGHT",
        "VFR",
        HELICOPTER_DESTINATIONS,
        False,
        110,
    ),
    AircraftProfile(
        models.sikorsky_ch53d,
        "helicopters",
        "STALL",
        "VFR",
        HELICOPTER_DESTINATIONS,
        False,
        120,
    ),
    AircraftProfile(
        models.v22_osprey,
        "helicopters",
        "STORM",
        "IFR",
        HELICOPTER_DESTINATIONS,
        False,
        220,
    ),
)


@dataclass(frozen=True)
class GeneratorSettings:
    seed: int
    volume: str = "moderate"
    operations: dict[str, int] = field(
        default_factory=lambda: dict.fromkeys(OPERATIONS, 1)
    )
    aircraft_types: dict[str, int] = field(
        default_factory=lambda: dict.fromkeys(AIRCRAFT_TYPES, 1)
    )

    def validate(self):
        if type(self.seed) is not int:
            raise ValueError("Seed must be an integer")
        if self.volume not in TRAFFIC_LEVELS:
            raise ValueError("Unknown traffic level")
        for label, weights, keys in (
            ("operation", self.operations, OPERATIONS),
            ("aircraft type", self.aircraft_types, AIRCRAFT_TYPES),
        ):
            if (
                set(weights) != set(keys)
                or any(
                    type(value) is not int or value < 0 for value in weights.values()
                )
                or not any(weights.values())
            ):
                raise ValueError(
                    f"{label} weights must be non-negative integers with at least one enabled"
                )


def _airport_weight(airport):
    if airport not in CIVILIAN_AIRPORTS:
        return 1.0
    tiers = {"primary": 80, "occasional": 15, "rare": 5}
    tier = CIVILIAN_AIRPORTS[airport][0]
    count = sum(value[0] == tier for value in CIVILIAN_AIRPORTS.values())
    return tiers[tier] / count


def _itineraries(profile, operation, router, unavailable=None):
    airports = profile.airports
    if operation == "departures":
        pairs = (("KNYL", airport) for airport in airports)
    elif operation == "approaches":
        pairs = ((airport, "KNYL") for airport in airports)
    else:
        # Cross the Yuma area instead of making a local out-and-back flight.
        anchor = router.anchor
        west = [
            airport
            for airport in airports
            if router.navigation.airport(airport).longitude < anchor.longitude
        ]
        east = [
            airport
            for airport in airports
            if router.navigation.airport(airport).longitude > anchor.longitude
        ]
        pairs = (
            pair
            for western in west
            for eastern in east
            for pair in ((western, eastern), (eastern, western))
        )
    itineraries = []
    for origin, destination in pairs:
        try:
            route, distance, fallback = router.flight(origin, destination)
        except NoSafeRouteError as error:
            if unavailable is not None:
                unavailable.add(error.airport)
            continue
        if distance <= profile.model.max_range:
            weight = 1.0
            if profile.civilian:
                for airport in (origin, destination):
                    if airport != "KNYL":
                        weight *= _airport_weight(airport)
            itineraries.append((origin, destination, route, fallback, weight))
    return itineraries


def _airborne_position(route, anchor, rng):
    anchor_index = next(
        index for index, point in enumerate(route) if point.name == anchor.name
    )
    remaining = rng.uniform(25, 40)
    for index in range(anchor_index, 0, -1):
        end, start = route[index], route[index - 1]
        distance = NavigationalCoordinateSystem.calculate_distance(
            end.latitude, end.longitude, start.latitude, start.longitude
        )
        if remaining <= distance:
            heading = _bearing(end.latitude, end.longitude, start)
            lat, lon = NavigationalCoordinateSystem.calculate_new_position(
                end.latitude, end.longitude, remaining, heading, 3600
            )
            return float(lat), float(lon), _bearing(float(lat), float(lon), end)
        remaining -= distance
    raise ValueError("Route is too short to place an inbound aircraft near Yuma")


def generate_yuma_scenario(settings, start_time=None):
    """Return aircraft, facility, strips, and warnings for a seeded scenario."""
    settings.validate()
    if start_time is None:
        start_time = datetime.now(UTC)
    if start_time.tzinfo is None or start_time.utcoffset() is None:
        raise ValueError("Scenario start time must include a UTC offset")
    start_time = start_time.astimezone(UTC)
    local_hour = (start_time - timedelta(hours=7)).hour
    daytime = 6 <= local_hour < 22
    rng = random.Random(settings.seed)
    facility = ATCFacility.get_atc_facility_by_name("KNYL")
    if facility is None:
        raise ValueError("The KNYL facility is not configured")
    facility.active_runways = ("03L", "03R", "35")
    facility.helicopter_pads = ("P1", "P2", "P3", "P5")
    navigation = NavigationData()
    router = yuma_router(navigation)
    requested = [
        (aircraft_type, operation)
        for aircraft_type in AIRCRAFT_TYPES
        for operation in OPERATIONS
        if settings.aircraft_types[aircraft_type] and settings.operations[operation]
    ]
    candidates = {}
    unavailable = set()
    for category, operation in requested:
        profiles = []
        for profile in PROFILES:
            if profile.category == category:
                itineraries = _itineraries(profile, operation, router, unavailable)
                if itineraries:
                    profiles.append((profile, itineraries))
        if profiles:
            candidates[(category, operation)] = profiles
    supported = [key for key in requested if key in candidates]
    if not supported:
        detail = (
            f"; no safe route to {', '.join(sorted(unavailable))}"
            if unavailable
            else ""
        )
        raise ValueError(
            "No supported combinations of aircraft type and operation" + detail
        )
    missing = [key for key in requested if key not in candidates]
    warnings = (
        ["No suitable routes for: " + ", ".join(f"{a} / {o}" for a, o in missing)]
        if missing
        else []
    )
    if unavailable:
        warnings.append("No safe route for airports: " + ", ".join(sorted(unavailable)))
    weights = [
        settings.aircraft_types[category]
        * settings.operations[operation]
        * (1 if operation == "departures" and not daytime else 2)
        for category, operation in supported
    ]
    aircraft_list = AircraftList()
    strips = []
    runway_cycle = cycle(("03L", "03R"))
    pad_cycle = cycle(facility.helicopter_pads)
    departures = []
    direct_callsigns = []
    registration_rng = random.Random(f"{settings.seed}:registrations")
    registration_numbers = registration_rng.sample(
        range(100, 1000), TRAFFIC_LEVELS[settings.volume]
    )
    for index in range(TRAFFIC_LEVELS[settings.volume]):
        category, operation = rng.choices(supported, weights=weights, k=1)[0]
        profile, itineraries = rng.choice(candidates[(category, operation)])
        origin, destination, route_text, fallback, _ = rng.choices(
            itineraries, weights=[item[4] for item in itineraries], k=1
        )[0]
        identifier = f"G{index + 1}"
        origin_point = navigation.airport(origin)
        destination_point = navigation.airport(destination)
        course = facility.location.true_to_magnetic(
            _bearing(origin_point.latitude, origin_point.longitude, destination_point)
        )
        eastbound = course < 180
        if profile.rules == "VFR":
            altitude = (
                (4500 if eastbound else 3500)
                if category == "helicopters"
                else (7500 if eastbound else 6500)
            )
        else:
            altitude = (
                (17000 if eastbound else 16000)
                if category != "helicopters"
                else (9000 if eastbound else 8000)
            )
        plan = FlightPlan(
            identifier, origin, destination, route_text, altitude, profile.speed
        )
        route = navigation.resolve(plan)
        if operation == "departures":
            lat, lon, heading = origin_point.latitude, origin_point.longitude, 0
        else:
            lat, lon, heading = _airborne_position(route, router.anchor, rng)
        if profile.callsign == "N":
            letters = "".join(registration_rng.choices("ABCDEFGHJKLMNPQRSTUVWXYZ", k=2))
            callsign = f"N{registration_numbers[index]}{letters}"
        else:
            callsign = f"{profile.callsign}{index + 1}"
        squawk = f"{0o2000 + index:04o}" if profile.rules == "IFR" else "1200"
        aircraft = Aircraft(
            identifier,
            squawk,
            f"G{index + 1:05d}",
            callsign,
            profile.model,
            heading,
            altitude / 100,
            profile.speed,
            0,
            lat,
            lon,
            profile.rules,
        )
        strip = FlightStrip(identifier, aircraft, plan)
        # Generated airborne traffic starts locally, so retain Yuma ownership.
        if fallback:
            direct_callsigns.append(callsign)
            strip.remarks = "DIRECT ROUTE FALLBACK"
        if operation != "enroute":
            if category == "helicopters" and profile.model is not models.v22_osprey:
                strip.operation_area = next(pad_cycle)
            elif profile.model in (
                models.cessna_172,
                models.piper_pa28,
                models.cessna_208,
            ):
                strip.operation_area = "35"
            else:
                strip.operation_area = next(runway_cycle)
        role = {
            "departures": "departure",
            "approaches": "approach",
            "enroute": "enroute",
        }[operation]
        aircraft.radio_channel = f"{role}_{'low' if profile.civilian else 'high'}"
        if operation == "departures":
            aircraft.departure = Departure(
                strip, navigation.airport("KNYL"), 0, facility.location
            )
            departures.append(aircraft.departure)
        aircraft.flight_guidance = FlightPlanGuidance(strip, navigation)
        aircraft.distance = NavigationalCoordinateSystem.calculate_distance(
            facility.location.latitude,
            facility.location.longitude,
            aircraft.lat,
            aircraft.lon,
        )
        aircraft_list.add_aircraft([aircraft])
        strips.append(strip)
    if direct_callsigns:
        warnings.append("Direct routing fallback: " + ", ".join(direct_callsigns))
    if settings.volume == "heavy" and daytime:
        delays = []
        elapsed = 0
        for _ in departures:
            elapsed += rng.randint(180, 300)
            delays.append(elapsed)
    elif departures:
        first = rng.randint(180, 300)
        delays = [first, *sorted(rng.randint(first, 30 * 60) for _ in departures[1:])]
    else:
        delays = []
    for departure, delay in zip(departures, delays):
        departure.delay = delay
        departure.scheduled_utc = start_time + timedelta(seconds=delay)
    aircraft_list.assign_to_atc_facility(facility)
    return aircraft_list, facility, strips, warnings
