import csv
import json
import logging
import math
import pickle
import queue
import re
import subprocess
import sys
import threading
from pathlib import Path

import arcade
import numpy as np
import pyglet

from simulator.core.constants import (
    DISPLAY_RADIUS,
    MAX_DISTANCE_MILES,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
)

ROOT = Path(__file__).resolve().parents[2]
LAYERS = (
    ("Airports", "Airports.csv", "points", (100, 145, 130)),
    ("Waypoints", "Designated_Point.csv", "points", (95, 125, 115)),
    ("Navaids", "NAVAID_System.csv", "points", (120, 160, 140)),
    ("Holds (fixes)", "Holding_Pattern.csv", "points", (130, 130, 100)),
    ("State borders", "us-state-boundaries.csv", "states", (90, 100, 110)),
    ("Airspace", "Airspace_Boundary.geojson", "geometry", (115, 100, 100)),
    ("Class airspace", "Class_Airspace.geojson", "geometry", (110, 100, 120)),
    ("Special use", "Special_Use_Airspace.geojson", "geometry", (125, 105, 90)),
    ("ATS routes", "ATS_Route.geojson", "geometry", (85, 110, 125)),
    ("Route airspace", "Route_Airspace.geojson", "geometry", (95, 105, 120)),
    ("Radial bearings", "Radial_Bearing.geojson", "geometry", (100, 110, 105)),
    ("Pending runways", "Pending_Runway.geojson", "geometry", (115, 115, 115)),
)
LAYER_KEYS = tuple(getattr(arcade.key, f"F{i}") for i in range(1, 13))
DEFAULT_VISIBLE = {0, 2, 4, 5, 7, 8}


def read_features(path, stop):
    decoder = json.JSONDecoder()
    with path.open(encoding="utf-8-sig") as file:
        buffer = ""
        while True:
            chunk = file.read(65536)
            if not chunk:
                raise ValueError(f"No features array in {path}")
            buffer += chunk
            match = re.search(r'"features"\s*:\s*\[', buffer)
            if match:
                position = match.end()
                break
            if len(buffer) > 16 * 1024 * 1024:
                raise ValueError(f"GeoJSON header is too large in {path}")

        while not stop.is_set():
            while True:
                while position < len(buffer) and buffer[position].isspace():
                    position += 1
                if position < len(buffer):
                    break
                buffer = file.read(65536)
                position = 0
                if not buffer:
                    raise ValueError(f"Unterminated features array in {path}")
            if buffer[position] == "]":
                return
            if buffer[position] == ",":
                position += 1
                continue
            while True:
                try:
                    feature, end = decoder.raw_decode(buffer, position)
                    break
                except json.JSONDecodeError as error:
                    remainder = buffer[position:]
                    if len(remainder) > 16 * 1024 * 1024:
                        raise ValueError(
                            f"Invalid or oversized feature in {path}"
                        ) from error
                    chunk = file.read(65536)
                    if not chunk:
                        raise ValueError(f"Invalid feature in {path}") from error
                    buffer = remainder + chunk
                    position = 0
            yield feature
            position = end
            if position > 65536:
                buffer = buffer[position:]
                position = 0


class OverlayLoader:
    def __init__(self, latitude, longitude, radius_nm=MAX_DISTANCE_MILES, root=ROOT):
        self.latitude = latitude
        self.longitude = longitude
        self.radius_nm = radius_nm
        self.root = Path(root)

    def project(self, coordinates):
        coords = np.asarray(coordinates, dtype=float)
        lon = np.radians(coords[:, 0] - self.longitude)
        lat = np.radians(coords[:, 1])
        lat0 = math.radians(self.latitude)
        dlat = lat - lat0
        a = np.clip(
            np.sin(dlat / 2) ** 2 + math.cos(lat0) * np.cos(lat) * np.sin(lon / 2) ** 2,
            0,
            1,
        )
        distance = 3440.065 * 2 * np.arctan2(np.sqrt(a), np.sqrt(np.maximum(0, 1 - a)))
        bearing = np.arctan2(
            np.sin(lon) * np.cos(lat),
            math.cos(lat0) * np.sin(lat) - math.sin(lat0) * np.cos(lat) * np.cos(lon),
        )
        return (
            np.column_stack((distance * np.sin(bearing), distance * np.cos(bearing)))
            / self.radius_nm
        )

    @staticmethod
    def clip_segments(points, segment_mask=None):
        start, end = points[:-1], points[1:]
        delta = end - start
        a = np.sum(delta * delta, axis=1)
        b = 2 * np.sum(start * delta, axis=1)
        c = np.sum(start * start, axis=1) - 1
        discriminant = b * b - 4 * a * c
        valid = (a > 0) & (discriminant >= 0)
        if segment_mask is not None:
            valid &= segment_mask
        if not np.any(valid):
            return []
        start, delta, a, b, discriminant = (
            value[valid] for value in (start, delta, a, b, discriminant)
        )
        root = np.sqrt(discriminant)
        first = np.maximum(0, (-b - root) / (2 * a))
        last = np.minimum(1, (-b + root) / (2 * a))
        valid = first <= last
        ends = np.stack(
            (
                start[valid] + delta[valid] * first[valid, None],
                start[valid] + delta[valid] * last[valid, None],
            ),
            axis=1,
        )
        return [tuple(point) for point in ends.reshape(-1, 2)]

    def geometry_lines(self, geometry):
        if not geometry:
            return []
        kind = geometry["type"]
        coordinates = geometry["coordinates"]
        if kind == "LineString":
            paths = [coordinates]
        elif kind in ("MultiLineString", "Polygon"):
            paths = coordinates
        elif kind == "MultiPolygon":
            paths = (ring for polygon in coordinates for ring in polygon)
        elif kind in ("Point", "MultiPoint"):
            return []
        else:
            raise ValueError(f"Unsupported GIS geometry type: {kind}")

        result = []
        for path in paths:
            if len(path) < 2:
                continue
            coords = np.asarray(path, dtype=float)
            # A conservative geographic bounding box avoids projecting distant features.
            lat_margin = self.radius_nm / 60 + 1
            lon_margin = min(
                180, lat_margin / max(0.01, math.cos(math.radians(self.latitude)))
            )
            relative_lon = (coords[:, 0] - self.longitude + 180) % 360 - 180
            if (
                np.max(coords[:, 1]) < self.latitude - lat_margin
                or np.min(coords[:, 1]) > self.latitude + lat_margin
                or np.max(relative_lon) < -lon_margin
                or np.min(relative_lon) > lon_margin
            ):
                continue
            continuous = np.abs(np.diff(relative_lon)) <= 180
            result.extend(self.clip_segments(self.project(coords), continuous))
        return result

    def load(self, index, stop):
        _, filename, kind, _ = LAYERS[index]
        lines, labels = [], []
        if kind == "points":
            with (self.root / "GIS_CSV" / filename).open(
                encoding="utf-8-sig", newline=""
            ) as file:
                for row in csv.DictReader(file):
                    if stop.is_set():
                        return None
                    if not row["X"] or not row["Y"]:
                        continue
                    x, y = self.project([[float(row["X"]), float(row["Y"])]])[0]
                    if x * x + y * y > 1:
                        continue
                    size = 0.006
                    lines.extend(
                        self.clip_segments(np.array(((x - size, y), (x + size, y))))
                    )
                    lines.extend(
                        self.clip_segments(np.array(((x, y - size), (x, y + size))))
                    )
                    label = (
                        row.get("NAME", "").split("*")[0]
                        if index == 3
                        else row.get("IDENT", "")
                    )
                    if label:
                        labels.append((x, y, label))
        elif kind == "states":
            csv.field_size_limit(2**31 - 1)
            with (self.root / "GIS_CSV" / filename).open(
                encoding="utf-8-sig", newline=""
            ) as file:
                for row in csv.DictReader(file, delimiter=";"):
                    if stop.is_set():
                        return None
                    lines.extend(self.geometry_lines(json.loads(row["St Asgeojson"])))
        else:
            path = self.root / "GIS_JSON" / filename
            count = 0
            for feature in read_features(path, stop):
                lines.extend(self.geometry_lines(feature.get("geometry")))
                count += 1
            if stop.is_set():
                return None
            if not count:
                raise ValueError(f"No readable features in {path}")
        return lines, labels


class GISOverlays:
    def __init__(self, latitude, longitude):
        self.loader = OverlayLoader(latitude, longitude)
        self.visible = set(DEFAULT_VISIBLE)
        self.status = ["off"] * len(LAYERS)
        self.data = {}
        self.label_views = {}
        self.requests = queue.Queue()
        self.results = queue.Queue()
        self.stop = threading.Event()
        self.process_lock = threading.Lock()
        self.process = None
        self.worker = threading.Thread(target=self._load_layers, daemon=True)
        self.worker.start()
        self.legend_batch = pyglet.graphics.Batch()
        self.legend = [
            arcade.Text(
                "", 10, SCREEN_HEIGHT - 20 - i * 17, color, 9, batch=self.legend_batch
            )
            for i, (_, _, _, color) in enumerate(LAYERS)
        ]
        for index in sorted(self.visible):
            self._request(index)

    def _request(self, index):
        if self.status[index] in ("off", "error"):
            self.status[index] = "loading"
            self.requests.put(index)

    def _load_layers(self):
        while not self.stop.is_set():
            index = self.requests.get()
            if index is None:
                break
            try:
                with self.process_lock:
                    if self.stop.is_set():
                        return
                    self.process = subprocess.Popen(
                        [
                            sys.executable,
                            "-m",
                            "simulator.display.gis_overlays",
                            str(index),
                            str(self.loader.latitude),
                            str(self.loader.longitude),
                            str(self.loader.radius_nm),
                            str(self.loader.root),
                        ],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        cwd=ROOT,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                    process = self.process
                output, error = process.communicate()
                with self.process_lock:
                    self.process = None
                if self.stop.is_set():
                    return
                if process.returncode:
                    raise RuntimeError(error.decode("utf-8", errors="replace"))
                result = pickle.loads(output)
            except Exception:
                logging.getLogger(__name__).exception(
                    "Failed to load GIS layer %s", LAYERS[index][0]
                )
                self.results.put((index, None))
            else:
                if result is not None:
                    self.results.put((index, result))

    def close(self):
        self.stop.set()
        with self.process_lock:
            if self.process is not None and self.process.poll() is None:
                self.process.terminate()
        self.requests.put(None)

    def toggle(self, index):
        if index in self.visible:
            self.visible.remove(index)
        else:
            self.visible.add(index)
            self._request(index)

    def update(self):
        while True:
            try:
                index, result = self.results.get_nowait()
            except queue.Empty:
                break
            if result is None:
                self.status[index] = "error"
                continue
            points, labels = result
            self.data[index] = {}
            for radius in (DISPLAY_RADIUS, min(SCREEN_WIDTH, SCREEN_HEIGHT) / 2):
                pixels = [
                    (SCREEN_WIDTH / 2 + x * radius, SCREEN_HEIGHT / 2 + y * radius)
                    for x, y in points
                ]
                text = []
                text_batch = pyglet.graphics.Batch()
                for x, y, label in labels:
                    px, py = (
                        SCREEN_WIDTH / 2 + x * radius,
                        SCREEN_HEIGHT / 2 + y * radius,
                    )
                    text.append(
                        (
                            px,
                            py,
                            arcade.Text(
                                label,
                                px + 4,
                                py + 3,
                                LAYERS[index][3],
                                8,
                                batch=text_batch,
                            ),
                        )
                    )
                shapes = arcade.shape_list.ShapeElementList()
                if pixels:
                    shapes.append(
                        arcade.shape_list.create_lines(pixels, (*LAYERS[index][3], 255))
                    )
                self.data[index][radius] = (shapes, text_batch, text)
                self.label_views.pop((index, radius), None)
            self.status[index] = "ready"

    def draw_map(self, radius):
        for index in sorted(self.visible):
            if self.status[index] != "ready":
                continue
            shapes, _, _ = self.data[index][radius]
            shapes.draw()

    def draw_labels(self, radius, transform, is_visible, view_key):
        for index in sorted(self.visible):
            if self.status[index] != "ready":
                continue
            _, text_batch, labels = self.data[index][radius]
            if self.label_views.get((index, radius)) != view_key:
                occupied = set()
                for x, y, label in labels:
                    px, py = transform(x, y)
                    cell = (int(px / 65), int(py / 14))
                    label.visible = is_visible(px, py) and cell not in occupied
                    if label.visible:
                        occupied.add(cell)
                        label.position = (px + 4, py + 3)
                self.label_views[(index, radius)] = view_key
            text_batch.draw()

    def draw_legend(self):
        for index, label in enumerate(self.legend):
            state = self.status[index] if index in self.visible else "off"
            text = f"F{index + 1} {LAYERS[index][0]}: {state}"
            if label.text != text:
                label.text = text
        self.legend_batch.draw()


if __name__ == "__main__":
    layer_index = int(sys.argv[1])
    loader = OverlayLoader(
        float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4]), sys.argv[5]
    )
    pickle.dump(loader.load(layer_index, threading.Event()), sys.stdout.buffer)
