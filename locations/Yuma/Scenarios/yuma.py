"""Build the Yuma scenario from the sample data."""

import random
from itertools import cycle

from locations.Yuma.Scenarios.sample_data import (
    ACTIVE_SAMPLE_AIRCRAFT,
    CIVILIAN_AIRPORTS,
    CIVILIAN_ARRIVAL_STARTS,
    CIVILIAN_ELIGIBLE_AIRPORTS,
    CIVILIAN_ROUTE_TEMPLATES,
    CIVILIAN_SAMPLE_AIRCRAFT,
    HELICOPTER_SAMPLES,
    RUNWAY_03_SAMPLES,
    SAMPLE_PLANS,
    SAMPLE_REMARKS,
    SMALL_CIVILIAN_SAMPLES,
)
from simulator.core.aircraft import Aircraft, AircraftList
from simulator.core.atc import ATCFacility, FlightPlan, FlightStrip, TrackingPosition
from simulator.navigation.departure import Departure
from simulator.navigation.flight_navigation import FlightPlanGuidance, NavigationData


def create_sample_aircraft():
    aircraft_list = AircraftList()
    aircraft_list.add_aircraft([Aircraft(*fields) for fields in ACTIVE_SAMPLE_AIRCRAFT])
    return aircraft_list


def create_sample_strips(aircraft_list, facility, plans=None):
    if plans is None:
        plans = SAMPLE_PLANS
    strips = [
        FlightStrip(aircraft.id, aircraft, FlightPlan(aircraft.id, *plans[aircraft.id]))
        for aircraft in aircraft_list.aircraft_list
        if aircraft.id in plans
    ]
    for strip in strips:
        strip.remarks = SAMPLE_REMARKS.get(strip.flight_id, "")
    if facility.airport_code == "KNYL" and facility.active_runways:
        if not {"03L", "03R", "35"}.issubset(facility.active_runways):
            raise ValueError("Yuma sample traffic requires 03L, 03R and 35")
        runway_cycle = cycle(("03L", "03R"))
        pad_cycle = cycle(facility.helicopter_pads)
        for strip in strips:
            plan = strip.flight_plan
            if (
                not plan.origin
                or not plan.destination
                or facility.airport_code not in (plan.origin, plan.destination)
            ):
                continue
            if strip.aircraft.id in SMALL_CIVILIAN_SAMPLES:
                strip.operation_area = "35"
            elif strip.aircraft.id in HELICOPTER_SAMPLES:
                strip.operation_area = (
                    next(pad_cycle) if facility.helicopter_pads else "PAD"
                )
            elif strip.aircraft.id in RUNWAY_03_SAMPLES:
                strip.operation_area = next(runway_cycle)
    return strips


def assign_incoming_controller(strip, facility):
    if (
        strip.aircraft.flight_rules == "IFR"
        and strip.flight_plan.origin != facility.airport_code
    ):
        aircraft = strip.aircraft
        center = (
            TrackingPosition.LOS_ANGELES
            if facility.above_control_limit(aircraft.altitude)
            or aircraft.lon <= facility.location.longitude
            else TrackingPosition.ALBUQUERQUE
        )
        aircraft.track.owner = center
        aircraft.track.communications_owner = center
        aircraft.incoming_checkin_pending = True
        if aircraft.entry_remaining is None:
            aircraft.track.offer(TrackingPosition.YUMA)
        else:
            aircraft.incoming_handoff_on_entry = True


def _choose_civilian_airports(rng):
    choices = {
        aircraft_id: rng.choice(
            [
                airport
                for airport in eligible
                if CIVILIAN_AIRPORTS[airport][0] == "primary"
            ]
        )
        for aircraft_id, eligible in CIVILIAN_ELIGIBLE_AIRPORTS.items()
    }
    tier = rng.choices(("primary", "occasional", "rare"), weights=(80, 15, 5))[0]
    if tier != "primary":
        airports = [
            airport
            for airport, (airport_tier, _) in CIVILIAN_AIRPORTS.items()
            if airport_tier == tier
            and any(
                airport in eligible for eligible in CIVILIAN_ELIGIBLE_AIRPORTS.values()
            )
        ]
        airport = rng.choice(airports)
        aircraft_id = rng.choice(
            [
                identifier
                for identifier, eligible in CIVILIAN_ELIGIBLE_AIRPORTS.items()
                if airport in eligible
            ]
        )
        choices[aircraft_id] = airport
    return choices


def create_yuma_scenario(rng=None):
    facility = ATCFacility.get_atc_facility_by_name("KNYL")
    if facility is None:
        raise ValueError("The KNYL facility is not configured")
    facility.active_runways = ("03L", "03R", "35")
    facility.helicopter_pads = ("P1", "P2", "P3", "P5")

    aircraft_list = create_sample_aircraft()
    rng = rng if rng is not None else random
    civilian_airports = _choose_civilian_airports(rng)
    plans = dict(SAMPLE_PLANS)
    for aircraft in aircraft_list.aircraft_list:
        if aircraft.id not in CIVILIAN_ELIGIBLE_AIRPORTS:
            continue
        airport = civilian_airports[aircraft.id]
        direction = CIVILIAN_AIRPORTS[airport][1]
        route_key = airport if aircraft.id == "A8" else direction
        route, altitude = CIVILIAN_ROUTE_TEMPLATES[aircraft.id][route_key]
        if aircraft.id == "A1":
            origin, destination = "KPHX", airport
        elif aircraft.id == "A7":
            origin, destination = airport, "KNYL"
            aircraft.lat, aircraft.lon, aircraft.heading = CIVILIAN_ARRIVAL_STARTS[
                direction
            ]
        else:
            origin, destination = "KNYL", airport
        plans[aircraft.id] = (
            origin,
            destination,
            route,
            altitude,
            plans[aircraft.id][4],
        )
    aircraft_list.assign_to_atc_facility(facility)
    strips = create_sample_strips(aircraft_list, facility, plans)
    navigation_data = NavigationData()
    departure_count = 0
    for strip in strips:
        assign_incoming_controller(strip, facility)
        plan = strip.flight_plan
        if plan.origin == facility.airport_code:
            radio_role = "departure"
        elif plan.destination == facility.airport_code:
            radio_role = "approach"
        else:
            radio_role = "enroute"
        band = "low" if strip.aircraft.id in CIVILIAN_SAMPLE_AIRCRAFT else "high"
        strip.aircraft.radio_channel = f"{radio_role}_{band}"
        if strip.flight_plan.origin == facility.airport_code:
            departure_count += 1
            strip.aircraft.departure = Departure(
                strip,
                navigation_data.airport(facility.airport_code),
                30 * departure_count,
                facility.location,
            )
        strip.aircraft.flight_guidance = FlightPlanGuidance(strip, navigation_data)
    return aircraft_list, facility, strips
