import csv
import json
import pickle
import queue
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import arcade
import numpy as np

from simulator.display.gis_overlays import (
    DEFAULT_VISIBLE,
    LAYER_KEYS,
    LAYERS,
    GISOverlays,
    OverlayLoader,
)
from simulator.display.radar import RadarDisplay, RadarViewport


class OverlayLoaderTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / "GIS_CSV").mkdir()
        (self.root / "GIS_JSON").mkdir()
        self.loader = OverlayLoader(0, 0, root=self.root)
        self.stop = threading.Event()

    def test_points_use_decimal_xy_and_filter_range(self):
        path = self.root / "GIS_CSV" / "Airports.csv"
        with path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=["IDENT", "X", "Y"])
            writer.writeheader()
            writer.writerows(
                [
                    {"IDENT": "CENTER", "X": "0", "Y": "0"},
                    {"IDENT": "OUTSIDE", "X": "10", "Y": "0"},
                    {"IDENT": "NOCOORD", "X": "", "Y": ""},
                ]
            )
        lines, labels = self.loader.load(0, self.stop)
        self.assertEqual(len(lines), 4)
        self.assertEqual(labels, [(0, 0, "CENTER")])

    def test_map_worker_loads_a_layer_from_the_reorganized_package(self):
        path = self.root / "GIS_CSV" / "Airports.csv"
        with path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=["IDENT", "X", "Y"])
            writer.writeheader()
            writer.writerow({"IDENT": "CENTER", "X": "0", "Y": "0"})
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "simulator.display.gis_overlays",
                "0",
                "0",
                "0",
                "100",
                str(self.root),
            ],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            check=True,
            timeout=30,
        )
        _, labels = pickle.loads(result.stdout)
        self.assertEqual(labels, [(0, 0, "CENTER")])

    def test_clips_crossing_lines_even_when_both_endpoints_are_outside(self):
        lines = self.loader.geometry_lines(
            {
                "type": "MultiLineString",
                "coordinates": [[[-3, 0], [3, 0]], [[-3, 3], [3, 3]]],
            }
        )
        self.assertEqual(len(lines), 2)
        np.testing.assert_allclose(lines, [(-1, 0), (1, 0)], atol=1e-6)

    def test_remote_antimeridian_crossing_does_not_draw_across_scope(self):
        lines = self.loader.geometry_lines(
            {
                "type": "LineString",
                "coordinates": [[179, 0], [-179, 0]],
            }
        )
        self.assertEqual(lines, [])

    def test_projection_matches_radar_coordinates(self):
        display = SimpleNamespace(
            atc_facility=SimpleNamespace(location={"lat": 32.65, "lon": -114.6}),
            calculate_range_and_bearing=lambda lat, lon: (
                RadarDisplay.calculate_range_and_bearing(display, lat, lon)
            ),
            display_type=RadarDisplay.ARTS_IIE,
            ARTS_IIE=RadarDisplay.ARTS_IIE,
            center_x=600,
            center_y=450,
            radar_viewport=RadarViewport(),
        )
        display.transform_position = lambda x, y: RadarDisplay.transform_position(
            display, x, y
        )
        loader = OverlayLoader(32.65, -114.6)
        for lat, lon in ((32.65, -114.6), (33.0, -114.1), (32.0, -115.2)):
            x, y = loader.project([[lon, lat]])[0]
            radar_x, radar_y = RadarDisplay.convert_to_display_coordinates(
                display, lat, lon
            )
            np.testing.assert_allclose(
                [600 + x * 400, 450 + y * 400], [radar_x, radar_y]
            )

    def test_state_csv_polygon_and_companion_route_geometry(self):
        state = self.root / "GIS_CSV" / "us-state-boundaries.csv"
        geometry = {"type": "Polygon", "coordinates": [[[-3, 0], [3, 0], [-3, 0]]]}
        with state.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=["St Asgeojson"], delimiter=";")
            writer.writeheader()
            writer.writerow({"St Asgeojson": json.dumps(geometry)})
        state_lines, _ = self.loader.load(4, self.stop)
        self.assertEqual(len(state_lines), 4)

        route = self.root / "GIS_JSON" / "ATS_Route.geojson"
        feature = {
            "type": "Feature",
            "properties": {"IDENT": "V66"},
            "geometry": {
                "type": "LineString",
                "coordinates": [[-3, 0], [3, 0]],
            },
        }
        route.write_text(
            '{"type":"FeatureCollection","features":[\n'
            + json.dumps(feature)
            + "\n]}\n",
            encoding="utf-8",
        )
        route_lines, _ = self.loader.load(8, self.stop)
        self.assertEqual(len(route_lines), 2)

    def test_ats_overlays_show_only_their_own_route_type(self):
        path = self.root / "GIS_JSON" / "ATS_Route.geojson"
        geometry = {"type": "LineString", "coordinates": [[-0.1, 0], [0.1, 0]]}
        features = [
            {
                "type": "Feature",
                "properties": {"IDENT": identifier},
                "geometry": geometry,
            }
            for identifier in (
                "V23",
                "V100",
                "Q100",
                "J100",
                "T201",
                "VT688",
                "V66A",
                "UT306",
                "UQ2",
                "UJ10",
            )
        ]
        path.write_text(
            json.dumps({"type": "FeatureCollection", "features": features}),
            encoding="utf-8",
        )
        expected = self.loader.geometry_lines(geometry)
        for index, count in ((8, 2), (12, 1), (13, 1), (14, 1)):
            with self.subTest(layer=LAYERS[index][0]):
                lines, labels = self.loader.load(index, self.stop)
                self.assertEqual(lines, expected * count)
                self.assertEqual(labels, [])

    def test_ats_overlay_accepts_valid_data_without_v_routes(self):
        path = self.root / "GIS_JSON" / "ATS_Route.geojson"
        path.write_text(
            json.dumps(
                {"features": [{"properties": {"IDENT": "Q100"}, "geometry": None}]}
            ),
            encoding="utf-8",
        )
        self.assertEqual(self.loader.load(8, self.stop), ([], []))

    def test_ats_overlay_reports_missing_identifier(self):
        path = self.root / "GIS_JSON" / "ATS_Route.geojson"
        path.write_text(
            json.dumps({"features": [{"properties": {}, "geometry": None}]}),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "Missing ATS route identifier"):
            self.loader.load(8, self.stop)

    def test_invalid_geojson_is_reported(self):
        path = self.root / "GIS_JSON" / "ATS_Route.geojson"
        path.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "No readable features"):
            self.loader.load(8, self.stop)

    def test_loader_can_be_cancelled(self):
        path = self.root / "GIS_CSV" / "Airports.csv"
        path.write_text("IDENT,X,Y\nCENTER,0,0\n", encoding="utf-8")
        self.stop.set()
        self.assertIsNone(self.loader.load(0, self.stop))


class OverlayControlTests(unittest.TestCase):
    def test_only_v_routes_are_enabled_by_default(self):
        route_indices = {
            index
            for index, layer in enumerate(LAYERS)
            if layer[1] == "ATS_Route.geojson"
        }
        self.assertEqual(
            {LAYERS[index][0] for index in route_indices},
            {"V routes", "T routes", "Q routes", "J routes"},
        )
        self.assertEqual(route_indices & DEFAULT_VISIBLE, {8})

    def test_shifted_route_shortcuts_and_original_shortcuts(self):
        display = SimpleNamespace(
            gis_overlays=SimpleNamespace(toggle=mock.Mock()),
            selected_aircraft_id=None,
            scratchpad_edit_id=None,
            handoff_choice_id=None,
            data_block_directions={},
        )
        for key, index in (
            (arcade.key.F9, 12),
            (arcade.key.F10, 13),
            (arcade.key.F11, 14),
        ):
            with self.subTest(key=key):
                RadarDisplay.on_key_press(display, key, arcade.key.MOD_SHIFT)
                display.gis_overlays.toggle.assert_called_with(index)
                RadarDisplay.on_key_press(display, key, 0)
                display.gis_overlays.toggle.assert_called_with(LAYER_KEYS.index(key))

    def test_key_toggles_overlay_without_changing_aircraft_placement(self):
        display = SimpleNamespace(
            gis_overlays=SimpleNamespace(toggle=mock.Mock()),
            selected_aircraft_id="A1",
            scratchpad_edit_id=None,
            handoff_choice_id=None,
            data_block_directions={},
        )
        RadarDisplay.on_key_press(display, arcade.key.F7, 0)
        display.gis_overlays.toggle.assert_called_once_with(6)
        self.assertEqual(display.data_block_directions, {})

    def test_toggle_only_loads_a_layer_once(self):
        overlays = SimpleNamespace(
            visible=set(),
            status=["off"],
            requests=SimpleNamespace(put=mock.Mock()),
        )
        overlays._request = lambda index: GISOverlays._request(overlays, index)
        GISOverlays.toggle(overlays, 0)
        GISOverlays.toggle(overlays, 0)
        GISOverlays.toggle(overlays, 0)
        overlays.requests.put.assert_called_once_with(0)
        self.assertEqual(overlays.visible, {0})

    def test_loader_error_is_shown_in_layer_status(self):
        results = queue.Queue()
        results.put((0, None))
        overlays = SimpleNamespace(results=results, status=["loading"])
        GISOverlays.update(overlays)
        self.assertEqual(overlays.status, ["error"])

    def test_map_labels_follow_view_without_scaling_and_reappear(self):
        label = SimpleNamespace(visible=True, position=(0, 0))
        batch = mock.Mock()
        overlays = SimpleNamespace(
            visible={0},
            status=["ready"],
            label_views={},
            data={0: {400: (None, batch, [(800, 450, label)])}},
        )
        GISOverlays.draw_labels(
            overlays, 400, lambda x, y: (x + 300, y), lambda x, y: x <= 1000, (1, 0, 0)
        )
        self.assertFalse(label.visible)
        GISOverlays.draw_labels(
            overlays,
            400,
            lambda x, y: (x - 100, y),
            lambda x, y: x <= 1000,
            (2, 100, 0),
        )
        self.assertTrue(label.visible)
        self.assertEqual(label.position, (704, 453))
        self.assertEqual(batch.draw.call_count, 2)


if __name__ == "__main__":
    unittest.main()
