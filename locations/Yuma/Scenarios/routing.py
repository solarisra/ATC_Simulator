"""Build fictional Yuma routes from the available navigation data."""

import heapq
import json
import math
import re
from functools import lru_cache
from itertools import pairwise
from pathlib import Path

from shapely.geometry import LineString, box, shape
from shapely.ops import unary_union
from shapely.prepared import prep

from simulator.core.atc import FlightPlan
from simulator.navigation.flight_navigation import ROOT
from simulator.navigation.navmath import NavigationalCoordinateSystem


def _distance(first, second):
    return float(
        NavigationalCoordinateSystem.calculate_distance(
            first.latitude, first.longitude, second.latitude, second.longitude
        )
    )


class NoSafeRouteError(ValueError):
    def __init__(self, airport):
        self.airport = airport
        super().__init__(f"No route avoiding Mexico from BZA to {airport}")


class YumaRouter:
    def __init__(self, navigation):
        self.navigation = navigation
        path = Path(ROOT) / "GIS_JSON" / "us-state-boundaries.geojson"
        with path.open(encoding="utf-8") as file:
            features = json.load(file)["features"]
        states = unary_union(
            [
                shape(feature["geometry"])
                for feature in features
                if feature["properties"]["stusab"] in ("CA", "AZ")
            ]
        )
        self.mexico = prep(box(-119, 25, -108, 32.72).difference(states))
        self.anchor = navigation.point("BZA")
        self.anchor_id = navigation.points["BZA"][0]
        self.legs = {}
        graph = {}
        for airway, segments in navigation.airways.items():
            if not re.fullmatch(r"[A-Z0-9]{3,5}", airway):
                continue
            for start, neighbors in segments.items():
                if not self._usable(start):
                    continue
                for end, length in neighbors:
                    if not self._usable(end):
                        continue
                    if not self._safe(
                        navigation.point_ids[start], navigation.point_ids[end]
                    ):
                        continue
                    graph.setdefault(start, []).append((end, length, airway))
        self.graph = graph
        self.distances = {self.anchor_id: 0.0}
        self.previous = {}
        pending = [(0.0, self.anchor_id)]
        while pending:
            distance, current = heapq.heappop(pending)
            if distance != self.distances[current]:
                continue
            for neighbor, length, airway in graph.get(current, ()):
                new_distance = distance + length
                if new_distance < self.distances.get(neighbor, math.inf):
                    self.distances[neighbor] = new_distance
                    self.previous[neighbor] = (current, airway)
                    heapq.heappush(pending, (new_distance, neighbor))

    def _usable(self, identifier):
        point = self.navigation.point_ids[identifier]
        return (
            re.fullmatch(r"[A-Z0-9]{3,5}", point.name) is not None
            and point.name != "KRNM"
            and len(self.navigation.points[point.name]) == 1
        )

    def _safe(self, first, second):
        return not self.mexico.intersects(
            LineString(
                [
                    (first.longitude, first.latitude),
                    (second.longitude, second.latitude),
                ]
            )
        )

    def airport_leg(self, airport_name):
        """Return BZA-to-airport tokens, distance, and whether direct was required."""
        if airport_name not in self.legs:
            self.legs[airport_name] = self._airport_leg(airport_name)
        return self.legs[airport_name]

    def _airport_leg(self, airport_name):
        airport = self.navigation.airport(airport_name)
        direct_distance = _distance(self.anchor, airport)
        if direct_distance <= 15 and self._safe(self.anchor, airport):
            return (), direct_distance, False
        choices = []
        for identifier, distance in self.distances.items():
            if identifier == self.anchor_id:
                continue
            point = self.navigation.point_ids[identifier]
            if abs(point.latitude - airport.latitude) > 1.2:
                continue
            if abs(point.longitude - airport.longitude) > 1.5:
                continue
            connection = _distance(point, airport)
            if connection <= 65 and self._safe(point, airport):
                choices.append((distance + connection * 1.5, identifier, connection))
        for _, current, _ in sorted(choices):
            edges = []
            while current != self.anchor_id:
                parent, airway = self.previous[current]
                edges.append((parent, current, airway))
                current = parent
            edges.reverse()
            tokens = []
            last_airway = None
            for start, _, airway in edges:
                if airway != last_airway:
                    if last_airway is not None:
                        tokens.append(self.navigation.point_ids[start].name)
                    tokens.append(airway)
                last_airway = airway
            tokens.append(self.navigation.point_ids[edges[-1][1]].name)
            route = self.navigation.resolve(
                FlightPlan(
                    "ROUTER",
                    "KNYL",
                    airport_name,
                    " ".join(("BZA", *tokens)),
                    10000,
                    100,
                )
            )
            if all(self._safe(a, b) for a, b in pairwise(route)):
                distance = sum(_distance(a, b) for a, b in pairwise(route[1:]))
                return tuple(tokens), distance, False
        if self._safe(self.anchor, airport):
            return (), direct_distance, True
        raise NoSafeRouteError(airport_name)

    def flight(self, origin, destination):
        origin_tokens, origin_distance, origin_direct = self.airport_leg(origin)
        dest_tokens, dest_distance, dest_direct = self.airport_leg(destination)

        tokens = [*reversed(origin_tokens), "BZA", *dest_tokens]
        # A leading/trailing DCT marks the direct airport-to-network connection.
        tokens = ["DCT", *tokens, "DCT"]
        return (
            " ".join(tokens),
            origin_distance + dest_distance,
            (origin_direct or dest_direct),
        )


@lru_cache(maxsize=2)
def yuma_router(navigation):
    return YumaRouter(navigation)
