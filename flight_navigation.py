import csv
import heapq
import math
import re
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path

from navmath import NavigationalCoordinateSystem

ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Waypoint:
    name: str
    latitude: float
    longitude: float
    elevation: float | None = None


def _dms(value):
    match = re.fullmatch(r"(\d+)-(\d+)-(\d+(?:\.\d+)?)([NSEW])", value)
    if not match:
        raise ValueError(f"Invalid coordinate: {value!r}")
    degrees, minutes, seconds, hemisphere = match.groups()
    result = int(degrees) + int(minutes) / 60 + float(seconds) / 3600
    return -result if hemisphere in "SW" else result


class NavigationData:
    def __init__(self, root=ROOT):
        self.airports = {}
        self.points = {}
        self.point_ids = {}
        self.airways = {}
        directory = Path(root) / "GIS_CSV"
        with (directory / "Airports.csv").open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                if not row["X"] or not row["Y"] or not row["ELEVATION"]:
                    continue
                point = Waypoint(
                    row["ICAO_ID"] or row["IDENT"],
                    float(row["Y"]),
                    float(row["X"]),
                    float(row["ELEVATION"]),
                )
                self.airports[row["IDENT"]] = point
                if row["ICAO_ID"]:
                    self.airports[row["ICAO_ID"]] = point
        with (directory / "Designated_Point.csv").open(
            encoding="utf-8-sig", newline=""
        ) as f:
            for row in csv.DictReader(f):
                if not row["LATITUDE"] or not row["LONGITUDE"]:
                    continue
                latitude = float(row["Y"]) if row["Y"] else _dms(row["LATITUDE"])
                longitude = float(row["X"]) if row["X"] else _dms(row["LONGITUDE"])
                point = Waypoint(row["IDENT"], latitude, longitude)
                self.points.setdefault(point.name, []).append(row["GLOBAL_ID"])
                self.point_ids[row["GLOBAL_ID"]] = point
        with (directory / "ATS_Route.csv").open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                if not re.fullmatch(r"V\d+", row["IDENT"]):
                    continue
                start, end = row["STARTPT_ID"], row["ENDPT_ID"]
                if start not in self.point_ids or end not in self.point_ids:
                    continue
                if row["LENGTH_VAL"]:
                    length = float(row["LENGTH_VAL"])
                else:
                    first, last = self.point_ids[start], self.point_ids[end]
                    length = NavigationalCoordinateSystem.calculate_distance(
                        first.latitude, first.longitude, last.latitude, last.longitude
                    )
                if not math.isfinite(length) or length <= 0:
                    raise ValueError(f"Invalid {row['IDENT']} segment length")
                graph = self.airways.setdefault(row["IDENT"], {})
                graph.setdefault(start, []).append((end, length))
                graph.setdefault(end, []).append((start, length))

    def airport(self, name):
        try:
            return self.airports[name]
        except KeyError as error:
            raise ValueError(f"Unknown airport {name}") from error

    def point(self, name):
        matches = self.points.get(name, [])
        if len(matches) == 1:
            return self.point_ids[matches[0]]
        if not matches and name in self.airports:
            return self.airport(name)
        raise ValueError(f"Unknown or ambiguous waypoint {name}")

    def airway(self, name, start, end):
        graph = self.airways.get(name)
        if graph is None:
            raise ValueError(f"Unknown airway {name}")
        starts = self.points.get(start.name, [])
        ends = set(self.points.get(end.name, []))
        pending: list[tuple[float, str, tuple[str, ...]]] = [
            (0.0, identifier, ()) for identifier in starts
        ]
        heapq.heapify(pending)
        seen = set()
        while pending:
            distance, identifier, path = heapq.heappop(pending)
            if identifier in seen:
                continue
            seen.add(identifier)
            path = (*path, identifier)
            if identifier in ends:
                return [self.point_ids[item] for item in path]
            for neighbor, length in graph.get(identifier, []):
                if neighbor not in seen:
                    heapq.heappush(pending, (distance + length, neighbor, path))
        raise ValueError(f"No {name} route from {start.name} to {end.name}")

    def resolve(self, plan):
        origin = self.airport(plan.origin)
        destination = self.airport(plan.destination)
        if not isinstance(plan.altitude, (int, float)) or not math.isfinite(
            plan.altitude
        ):
            raise ValueError(f"Invalid filed altitude for {plan.flight_id}")
        tokens = plan.route.upper().split()
        if not tokens:
            raise ValueError(f"Empty route for {plan.flight_id}")
        for token in tokens:
            if not re.fullmatch(r"[A-Z0-9]{3,5}", token):
                raise ValueError(f"Invalid route identifier {token}")

        route = [origin]
        index = 0
        while index < len(tokens):
            token = tokens[index]
            if token == "DCT":
                index += 1
                continue
            if re.fullmatch(r"V\d+", token):
                if len(route) == 1 or index + 1 >= len(tokens):
                    raise ValueError(f"Airway {token} needs entry and exit fixes")
                end = self.point(tokens[index + 1])
                route.extend(self.airway(token, route[-1], end)[1:])
                index += 2
                continue
            point = self.point(token)
            if (point.latitude, point.longitude) != (
                route[-1].latitude,
                route[-1].longitude,
            ):
                route.append(point)
            index += 1
        if (destination.latitude, destination.longitude) != (
            route[-1].latitude,
            route[-1].longitude,
        ):
            route.append(destination)
        else:
            route[-1] = destination
        if len(route) < 2:
            raise ValueError(f"Route for {plan.flight_id} has no travel segment")
        return route


def _distance(latitude, longitude, waypoint):
    return NavigationalCoordinateSystem.calculate_distance(
        latitude, longitude, waypoint.latitude, waypoint.longitude
    )


def _bearing(latitude, longitude, waypoint):
    lat1, lat2 = math.radians(latitude), math.radians(waypoint.latitude)
    delta_lon = math.radians(waypoint.longitude - longitude)
    y = math.sin(delta_lon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(
        delta_lon
    )
    return math.degrees(math.atan2(y, x)) % 360


def _initial_leg(route, latitude, longitude):
    scale = math.cos(math.radians(latitude))
    best_distance = math.inf
    best_index = 1
    for index, (start, end) in enumerate(pairwise(route), start=1):
        ax = (start.longitude - longitude) * scale
        ay = start.latitude - latitude
        bx = (end.longitude - longitude) * scale
        by = end.latitude - latitude
        dx, dy = bx - ax, by - ay
        length = dx * dx + dy * dy
        fraction = max(0, min(1, -(ax * dx + ay * dy) / length)) if length else 0
        distance = (ax + fraction * dx) ** 2 + (ay + fraction * dy) ** 2
        if distance <= best_distance:
            best_distance, best_index = distance, index
    return best_index


class FlightPlanGuidance:
    def __init__(self, strip, navigation_data):
        self.strip = strip
        self.navigation_data = navigation_data
        self.signature = None
        self.route = []
        self.next_index = 1
        self.approach = False
        self.vector_heading = None
        self.assigned_altitude = None
        self._refresh_route(strip.aircraft)
        strip.aircraft.target_speed = None

    def assign_heading(self, heading):
        if not isinstance(heading, int) or not 1 <= heading <= 360:
            raise ValueError("Heading must be 001 to 360 true")
        self.vector_heading = heading % 360
        self._cancel_approach()

    def assign_altitude(self, altitude):
        aircraft = self.strip.aircraft
        if (
            not isinstance(altitude, int)
            or not 1 <= altitude <= aircraft.aircraft_model.service_ceiling
        ):
            raise ValueError("Altitude must be positive and within aircraft ceiling")
        self.assigned_altitude = altitude
        self._cancel_approach()

    def _cancel_approach(self):
        if self.approach:
            self.strip.aircraft.target_speed = None
        self.approach = False

    def clear_altitude(self):
        if self.assigned_altitude is None:
            raise ValueError("No assigned altitude to clear")
        self.assigned_altitude = None

    def direct_to(self, name):
        matches = [
            index
            for index in range(self.next_index, len(self.route))
            if self.route[index].name == name.upper()
        ]
        if not matches:
            raise ValueError("Fix is not on the remaining route")
        if len(matches) > 1:
            raise ValueError("Fix occurs more than once on the remaining route")
        self.next_index = matches[0]
        self.vector_heading = None
        self._cancel_approach()

    def resume_route(self):
        if self.vector_heading is None:
            raise ValueError("Aircraft is not on a heading vector")
        self.vector_heading = None
        self._cancel_approach()

    def _refresh_route(self, aircraft):
        plan = self.strip.flight_plan
        signature = (plan.origin, plan.destination, plan.route, plan.altitude)
        if signature != self.signature:
            route = self.navigation_data.resolve(plan)
            self.route = route
            self.next_index = _initial_leg(route, aircraft.lat, aircraft.lon)
            self.signature = signature
            self.approach = False

    def update(self, aircraft, delta_time):
        self._refresh_route(aircraft)
        remaining_time = delta_time
        while remaining_time > 0 and not aircraft.landed:
            step = min(remaining_time, 1.0)
            self._step(aircraft, step)
            remaining_time -= step

    def _step(self, aircraft, delta_time):
        turn_rate = aircraft.aircraft_model.turn_rate
        if turn_rate <= 0 or aircraft.aircraft_model.climb_rate <= 0:
            raise ValueError(
                f"{aircraft.id} cannot follow a route without maneuver rates"
            )
        if self.vector_heading is not None:
            altitude = (
                self.assigned_altitude
                if self.assigned_altitude is not None
                else self.strip.flight_plan.altitude
            )
            aircraft.update_heading(self.vector_heading)
            aircraft.update_altitude(altitude / 100)
            aircraft._advance_position(delta_time)
            return
        turn_radius = aircraft.speed / (3600 * math.radians(turn_rate))
        capture_radius = max(0.15, turn_radius * 1.25)
        target = self.route[self.next_index]
        distance = _distance(aircraft.lat, aircraft.lon, target)
        while self.next_index < len(self.route) - 1 and distance <= capture_radius:
            self.next_index += 1
            target = self.route[self.next_index]
            distance = _distance(aircraft.lat, aircraft.lon, target)

        remaining = distance
        for start, end in zip(
            self.route[self.next_index :], self.route[self.next_index + 1 :]
        ):
            remaining += _distance(start.latitude, start.longitude, end)

        destination = self.route[-1]
        field_elevation = destination.elevation
        if field_elevation is None:
            raise ValueError(f"Missing destination elevation for {aircraft.id}")
        filed_altitude = self.strip.flight_plan.altitude
        if self.assigned_altitude is not None:
            aircraft.update_heading(_bearing(aircraft.lat, aircraft.lon, target))
            aircraft.update_altitude(self.assigned_altitude / 100)
            aircraft._advance_position(delta_time)
            return
        descent_seconds = (
            max(0, max(aircraft.altitude * 100, filed_altitude) - field_elevation)
            / aircraft.aircraft_model.climb_rate
        )
        if remaining <= descent_seconds * aircraft.speed / 3600 + 8:
            self.approach = True

        stall_speed = aircraft.aircraft_model.stall_speed
        landing_speed = min(
            aircraft.speed, 1.3 * stall_speed if stall_speed is not None else 40
        )
        braking = aircraft.aircraft_model.air_braking_rate
        if braking <= 0:
            raise ValueError(f"{aircraft.id} cannot slow down for landing")
        braking_distance = max(0, aircraft.speed**2 - landing_speed**2) / (
            2 * braking * 3600
        )
        if remaining <= braking_distance + 8:
            self.approach = True
            aircraft.update_speed(landing_speed)

        if self.approach:
            descent_gradient = min(
                300,
                aircraft.aircraft_model.climb_rate
                * 3600
                / max(aircraft.speed, 1)
                * 0.8,
            )
            target_altitude = min(
                aircraft.altitude * 100, field_elevation + remaining * descent_gradient
            )
        else:
            target_altitude = filed_altitude
        aircraft.update_altitude(target_altitude / 100)

        if (
            self.next_index == len(self.route) - 1
            and distance <= 0.15
            and aircraft.altitude * 100 <= field_elevation + 100
            and aircraft.speed <= landing_speed + 1
        ):
            aircraft.lat, aircraft.lon = destination.latitude, destination.longitude
            aircraft.altitude = field_elevation / 100
            aircraft.speed = 0
            aircraft.target_heading = None
            aircraft.target_altitude = None
            aircraft.target_speed = None
            aircraft.landed = True
            self.strip.active = False
            return
        aircraft.update_heading(_bearing(aircraft.lat, aircraft.lon, target))
        aircraft._advance_position(delta_time)
