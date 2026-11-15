import math
import unittest
from itertools import pairwise
from types import SimpleNamespace
from unittest.mock import Mock, patch

import arcade

from constants import DISPLAY_RADIUS, FULL_ROTATION_TIME_SECONDS
from radar import RadarDisplay, RadarReturnManager, RadarSweep, RadarViewport


class RadarSweepTests(unittest.TestCase):
    def test_sector_has_smooth_fade_over_requested_angle(self):
        display = SimpleNamespace(center_x=600, center_y=450)
        shapes = Mock()
        with (
            patch("arcade.shape_list.ShapeElementList", return_value=shapes),
            patch("arcade.shape_list.create_triangles_filled_with_colors") as create,
        ):
            self.assertIs(RadarDisplay.create_sweep_sector(display), shapes)
        vertices, colors = create.call_args.args
        outer_edges = [
            (vertices[index + 19], colors[index + 19])
            for index in range(0, len(vertices), 24)
        ]
        outer_edges.append((vertices[-4], colors[-4]))
        angles = [math.degrees(math.atan2(x, y)) for (x, y), _ in outer_edges]
        opacity = [color[3] for _, color in outer_edges]
        self.assertAlmostEqual(angles[0], -18)
        self.assertAlmostEqual(angles[-1], 0)
        self.assertEqual((opacity[0], opacity[-1]), (0, 180))
        self.assertTrue(all(a < b for a, b in pairwise(opacity)))
        self.assertTrue(
            all(
                math.isclose(math.hypot(x, y), DISPLAY_RADIUS)
                for (x, y), _ in outer_edges
            )
        )

    def test_sweep_speed_is_independent_of_frame_rate(self):
        for fps in (30, 60, 120):
            with self.subTest(fps=fps):
                sweep = RadarSweep()
                for _ in range(fps):
                    sweep.update(1 / fps)
                self.assertAlmostEqual(
                    sweep.angle, 2 * math.pi / FULL_ROTATION_TIME_SECONDS
                )

    def test_draw_uses_sector_rotation_and_transformed_leading_line(self):
        viewport = RadarViewport()
        viewport.zoom_by(1)
        viewport.pan(1, 0)
        display = SimpleNamespace(
            center_x=600,
            center_y=450,
            sweep=SimpleNamespace(angle=math.pi / 2),
            map_camera=Mock(),
            default_camera=Mock(),
            sweep_sector=Mock(),
            transform_position=lambda x, y: viewport.transform(
                x, y, 600, 450, DISPLAY_RADIUS
            ),
        )
        with patch("arcade.draw_line") as line:
            RadarDisplay.draw_sweep(display)
        display.map_camera.use.assert_called_once()
        display.default_camera.use.assert_called_once()
        display.sweep_sector.draw.assert_called_once()
        self.assertAlmostEqual(display.sweep_sector.angle, 90)
        start_x, start_y, end_x, end_y, color, width = line.call_args.args
        self.assertAlmostEqual(start_x, 580)
        self.assertAlmostEqual(start_y, 450)
        self.assertAlmostEqual(end_x, 1020)
        self.assertAlmostEqual(end_y, 450)
        self.assertEqual((color, width), (arcade.color.ORANGE, 2))


class RadarReturnTests(unittest.TestCase):
    def test_return_fades_with_elapsed_time_and_expires_after_five_sweeps(self):
        manager = RadarReturnManager()
        manager.add_return(10, 20)
        lifetime = 5 * FULL_ROTATION_TIME_SECONDS

        manager.update(lifetime / 4)
        self.assertAlmostEqual(manager.radar_returns[0][2], 0.75)
        manager.update(lifetime / 4)
        self.assertAlmostEqual(manager.radar_returns[0][2], 0.5)
        self.assertEqual(manager.radar_returns[0][:2], [10, 20])
        manager.update(lifetime / 2)
        self.assertEqual(manager.radar_returns, [])

    def test_return_uses_sweep_color_and_current_opacity(self):
        manager = RadarReturnManager()
        manager.add_return(10, 20)
        manager.update(5 * FULL_ROTATION_TIME_SECONDS / 2)

        with patch("arcade.draw_circle_filled") as draw:
            manager.draw()

        draw.assert_called_once_with(10, 20, 2, (*arcade.color.ORANGE[:3], 127))

    def test_return_lifetime_is_independent_of_update_rate(self):
        for fps in (30, 60, 120):
            with self.subTest(fps=fps):
                manager = RadarReturnManager()
                manager.add_return(10, 20)
                for _ in range(19 * fps):
                    manager.update(1 / fps)
                self.assertAlmostEqual(manager.radar_returns[0][2], 1 - 19 / 24)
                for _ in range(5 * fps + 1):
                    manager.update(1 / fps)
                self.assertEqual(manager.radar_returns, [])


class SecondaryRadarTests(unittest.TestCase):
    def test_snapshot_updates_position_and_data_once_per_second(self):
        aircraft = SimpleNamespace(
            id="A1",
            lat=32.0,
            lon=-114.0,
            callsign="TEST",
            squawk="1200",
            heading=90,
            altitude=50,
            aircraft_model=SimpleNamespace(aircraft_type="C172"),
            speed=120,
            landed=True,
            distance=0,
            scratchpad="",
        )
        display = SimpleNamespace(
            aircraft_list=SimpleNamespace(aircraft_list=[aircraft]),
            sweep=RadarSweep(),
            radar_return_manager=RadarReturnManager(),
            display_type=RadarDisplay.ARTS_IIE,
            ARTS_IIE=RadarDisplay.ARTS_IIE,
            center_x=600,
            center_y=450,
            secondary_update_elapsed=0,
            emergency_flash_elapsed=0,
            secondary_radar_returns=[],
            calculate_range_and_bearing=lambda lat, lon: (10, 0),
        )
        display.capture_secondary_radar_returns = lambda: (
            RadarDisplay.capture_secondary_radar_returns(display)
        )
        display.capture_secondary_radar_returns()
        original = display.secondary_radar_returns[0]
        aircraft.lat = 33.0
        aircraft.altitude = 70

        RadarDisplay.on_update(display, 0.5)
        self.assertEqual(display.secondary_radar_returns[0], original)
        RadarDisplay.on_update(display, 0.5)
        updated = display.secondary_radar_returns[0]
        self.assertEqual(updated.latitude, 33.0)
        self.assertEqual(updated.altitude, 70)

    def test_altitude_trends_follow_aircraft_ids_and_new_contacts_start_level(self):
        def aircraft(identifier, altitude):
            return SimpleNamespace(
                id=identifier,
                lat=32,
                lon=-114,
                callsign=identifier,
                squawk="1200",
                heading=90,
                altitude=altitude,
                speed=100,
                scratchpad="",
                aircraft_model=SimpleNamespace(aircraft_type="C172"),
            )

        first, second = aircraft("A1", 50), aircraft("A2", 80)
        aircraft_list = SimpleNamespace(aircraft_list=[first, second])
        display = SimpleNamespace(
            aircraft_list=aircraft_list, secondary_radar_returns=[]
        )
        RadarDisplay.capture_secondary_radar_returns(display)
        first.altitude += 0.01
        second.altitude -= 0.01
        aircraft_list.aircraft_list = [second, first, aircraft("A3", 50)]
        RadarDisplay.capture_secondary_radar_returns(display)
        self.assertEqual(
            {
                snapshot.aircraft_id: snapshot.altitude_trend
                for snapshot in display.secondary_radar_returns
            },
            {"A1": 1, "A2": -1, "A3": 0},
        )

    def test_arts_secondary_overlay_contains_aircraft_information(self):
        aircraft = SimpleNamespace(
            id="A1",
            lat=32.0,
            lon=-114.0,
            callsign="TEST",
            squawk="1200",
            heading=90,
            altitude=50,
            aircraft_model=SimpleNamespace(aircraft_type="C172"),
            speed=120,
            scratchpad="",
        )
        display = SimpleNamespace(
            aircraft_list=SimpleNamespace(aircraft_list=[aircraft]),
            secondary_radar_returns=[],
        )
        RadarDisplay.capture_secondary_radar_returns(display)
        snapshot = display.secondary_radar_returns[0]

        with (
            patch("arcade.draw_circle_filled"),
            patch("arcade.draw_line") as draw_line,
            patch("arcade.draw_text") as draw_text,
        ):
            RadarDisplay.draw_secondary_return(
                snapshot, 100, 200, 15.5, text_size=(50, 30)
            )

        self.assertEqual(draw_text.call_args.args[0], "TEST\n050  12\nC172\n ")
        draw_line.assert_called_once_with(100, 200, 85, 200, arcade.color.WHITE, 1)

    def test_data_block_reserves_empty_scratchpad_line(self):
        snapshot = SimpleNamespace(
            callsign="N123",
            heading=0,
            altitude=5,
            speed=125,
            aircraft_type="C172",
            altitude_trend=0,
            squawk="1200",
            scratchpad="",
        )
        text, _, _ = RadarDisplay.secondary_return_layout(snapshot, 0, 0, 10)
        self.assertEqual(text, "N123\n005  13\nC172\n ")

    def test_data_block_label_is_reused_and_updates_with_aircraft_data(self):
        snapshot = SimpleNamespace(
            aircraft_id="A1",
            callsign="TEST",
            heading=0,
            altitude=50,
            speed=120,
            aircraft_type="C172",
            altitude_trend=0,
            squawk="1200",
            scratchpad="",
        )
        display = SimpleNamespace(
            data_block_labels={},
            emergency_flash_elapsed=0,
            secondary_return_layout=RadarDisplay.secondary_return_layout,
        )

        def make_label(text, *args, **kwargs):
            return SimpleNamespace(text=text, content_width=50, content_height=45)

        with patch("arcade.Text", side_effect=make_label) as create_text:
            cached = RadarDisplay.get_data_block_label(display, snapshot, 10)
            self.assertEqual(cached.label.text, "TEST\n050  12\nC172\n ")
            self.assertEqual((cached.width, cached.height), (50, 45))
            self.assertIs(
                RadarDisplay.get_data_block_label(display, snapshot, 10), cached
            )
            create_text.assert_called_once()
            snapshot.altitude = 60
            updated = RadarDisplay.get_data_block_label(display, snapshot, 10)
            self.assertEqual(updated.label.text, "TEST\n060  12\nC172\n ")
            self.assertEqual(create_text.call_count, 2)

    def test_emergency_flashes_only_em_and_keeps_layout_stable(self):
        snapshot = SimpleNamespace(
            aircraft_id="A1",
            callsign="TEST",
            heading=0,
            altitude=50,
            speed=120,
            aircraft_type="C172",
            altitude_trend=0,
            squawk="7700",
            scratchpad="ABC",
        )
        display = Mock(
            data_block_labels={},
            emergency_flash_elapsed=0,
            secondary_return_layout=RadarDisplay.secondary_return_layout,
        )

        class FakeLabel:
            def __init__(self, text, *args, **kwargs):
                self.text = text

            @property
            def content_width(self):
                return max(map(len, self.text.splitlines()))

            @property
            def content_height(self):
                return len(self.text.splitlines())

        with patch("arcade.Text", side_effect=FakeLabel):
            cached = RadarDisplay.get_data_block_label(display, snapshot, 10)
            self.assertEqual(cached.label.text, "TEST EM\n050  12\nC172\nABC")
            dimensions = cached.width, cached.height
            display.emergency_flash_elapsed = 0.5
            self.assertIs(
                RadarDisplay.get_data_block_label(display, snapshot, 10), cached
            )
            self.assertEqual(cached.label.text, "TEST\n050  12\nC172\nABC")
            self.assertEqual((cached.width, cached.height), dimensions)
            display.emergency_flash_elapsed = 0
            RadarDisplay.get_data_block_label(display, snapshot, 10)
            self.assertIn("TEST EM\n", cached.label.text)
            for squawk in ("1200", "7500", "7600"):
                snapshot.squawk = squawk
                label = RadarDisplay.get_data_block_label(display, snapshot, 10)
                self.assertEqual(label.label.text, "TEST\n050  12\nC172\nABC")

    def test_scratchpad_edit_save_cancel_clear_and_limits(self):
        aircraft = [
            SimpleNamespace(
                id=identifier,
                lat=32,
                lon=-114,
                callsign=identifier,
                squawk="1200",
                heading=90,
                altitude=50,
                speed=100,
                scratchpad="",
                aircraft_model=SimpleNamespace(aircraft_type="C172"),
            )
            for identifier in ("A1", "A2")
        ]
        display = Mock(
            aircraft_list=SimpleNamespace(aircraft_list=aircraft),
            secondary_radar_returns=[],
            selected_aircraft_id="A1",
            scratchpad_edit_id=None,
            scratchpad_edit_text="",
            scratchpad_edit_error="",
        )
        RadarDisplay.capture_secondary_radar_returns(display)
        RadarDisplay.on_key_press(display, arcade.key.S, 0)
        for key in (arcade.key.A, arcade.key.B, ord("1"), ord("-"), ord("/")):
            RadarDisplay.on_key_press(display, key, 0)
        self.assertEqual(display.scratchpad_edit_text, "AB1-/")
        self.assertEqual(aircraft[0].scratchpad, "")
        RadarDisplay.on_key_press(display, arcade.key.BACKSPACE, 0)
        RadarDisplay.on_key_press(display, arcade.key.ENTER, 0)
        self.assertEqual(aircraft[0].scratchpad, "AB1-")
        self.assertEqual(display.secondary_radar_returns[0].scratchpad, "AB1-")
        self.assertEqual(display.secondary_radar_returns[1].scratchpad, "")
        RadarDisplay.capture_secondary_radar_returns(display)
        self.assertEqual(display.secondary_radar_returns[0].scratchpad, "AB1-")

        RadarDisplay.on_key_press(display, arcade.key.S, 0)
        for _ in range(12):
            RadarDisplay.on_key_press(display, arcade.key.X, 0)
        self.assertEqual(len(display.scratchpad_edit_text), 16)
        RadarDisplay.on_key_press(display, arcade.key.Y, 0)
        self.assertEqual(display.scratchpad_edit_error, "MAX 16 CHARACTERS")
        self.assertEqual(len(display.scratchpad_edit_text), 16)
        RadarDisplay.on_key_press(display, arcade.key.ESCAPE, 0)
        self.assertEqual(aircraft[0].scratchpad, "AB1-")

        RadarDisplay.on_key_press(display, arcade.key.S, 0)
        for _ in range(4):
            RadarDisplay.on_key_press(display, arcade.key.BACKSPACE, 0)
        RadarDisplay.on_key_press(display, arcade.key.NUM_ENTER, 0)
        self.assertEqual(aircraft[0].scratchpad, "")
        self.assertEqual(display.secondary_radar_returns[0].scratchpad, "")
        RadarDisplay.on_key_press(display, arcade.key.S, 0)
        RadarDisplay.on_key_press(display, arcade.key.X, 0)
        display.secondary_return_layouts = []
        RadarDisplay.on_mouse_press(display, 0, 0, arcade.MOUSE_BUTTON_LEFT, 0)
        self.assertIsNone(display.scratchpad_edit_id)
        self.assertEqual(aircraft[0].scratchpad, "")

    def test_selected_aircraft_details_show_extra_data(self):
        snapshot = SimpleNamespace(
            aircraft_id="A1",
            callsign="TEST",
            heading=90,
            squawk="1200",
            speed=125,
            latitude=32,
            longitude=-114,
        )
        text = unittest.mock.Mock()
        text.text = ""
        display = SimpleNamespace(
            selected_aircraft_id="A1",
            secondary_radar_returns=[snapshot],
            scratchpad_edit_id=None,
            calculate_range_and_bearing=lambda lat, lon: (15.5, 0),
            selected_details_text=text,
        )
        RadarDisplay.draw_selected_aircraft_details(display)
        self.assertEqual(
            text.text, "SELECTED TEST\nHDG 090\nSQK 1200\nSPD 125 KT\nRNG 15.5 NM"
        )
        text.draw.assert_called_once()
        display.selected_aircraft_id = None
        RadarDisplay.draw_selected_aircraft_details(display)
        text.draw.assert_called_once()

    def test_select_individual_contact_and_move_its_data_block(self):
        aircraft = [
            SimpleNamespace(
                id=identifier,
                lat=latitude,
                lon=0,
                callsign="TEST",
                squawk="1200",
                heading=90,
                altitude=50,
                aircraft_model=SimpleNamespace(aircraft_type="C172"),
                speed=120,
                scratchpad="",
            )
            for identifier, latitude in (("A1", 100), ("A2", 300))
        ]
        display = SimpleNamespace(
            aircraft_list=SimpleNamespace(aircraft_list=aircraft),
            display_type=RadarDisplay.ARTS_IIE,
            ARTS_IIE=RadarDisplay.ARTS_IIE,
            selected_aircraft_id=None,
            scratchpad_edit_id=None,
            emergency_flash_elapsed=0,
            data_block_directions={},
            secondary_return_layouts=[],
            secondary_radar_returns=[],
            data_block_overlap_warned=False,
            data_block_labels={},
            width=1200,
            height=900,
            calculate_range_and_bearing=lambda lat, lon: (10, 0),
            convert_to_display_coordinates=lambda lat, lon: (lat, 100),
            is_visible_scope_position=lambda x, y: True,
            secondary_return_layout=RadarDisplay.secondary_return_layout,
        )
        RadarDisplay.capture_secondary_radar_returns(display)
        with patch(
            "arcade.Text",
            return_value=SimpleNamespace(content_width=50, content_height=60),
        ):
            display.secondary_return_layouts = RadarDisplay.layout_secondary_returns(
                display
            )
        RadarDisplay.on_mouse_press(display, 100, 100, arcade.MOUSE_BUTTON_LEFT, 0)
        self.assertEqual(display.selected_aircraft_id, "A1")
        RadarDisplay.on_key_press(display, arcade.key.NUM_1, 0)
        self.assertEqual(display.data_block_directions, {"A1": (-1, -1)})
        RadarDisplay.capture_secondary_radar_returns(display)
        with patch(
            "arcade.Text",
            return_value=SimpleNamespace(content_width=50, content_height=60),
        ):
            display.secondary_return_layouts = RadarDisplay.layout_secondary_returns(
                display
            )
        RadarDisplay.on_mouse_press(display, 300, 100, arcade.MOUSE_BUTTON_LEFT, 0)
        RadarDisplay.on_key_press(display, arcade.key.NUM_RIGHT, 0)
        self.assertEqual(display.data_block_directions, {"A1": (-1, -1), "A2": (1, 0)})

        with patch(
            "arcade.Text",
            return_value=SimpleNamespace(content_width=50, content_height=60),
        ):
            display.secondary_return_layouts = RadarDisplay.layout_secondary_returns(
                display
            )
        RadarDisplay.on_mouse_press(display, 340, 100, arcade.MOUSE_BUTTON_LEFT, 0)
        self.assertEqual(display.selected_aircraft_id, "A2")
        RadarDisplay.on_mouse_press(display, 500, 300, arcade.MOUSE_BUTTON_LEFT, 0)
        self.assertIsNone(display.selected_aircraft_id)
        RadarDisplay.on_key_press(display, arcade.key.NUM_8, 0)
        self.assertEqual(display.data_block_directions["A2"], (1, 0))

    def test_numpad_positions_block_in_each_requested_direction(self):
        snapshot = SimpleNamespace(
            callsign="TEST",
            squawk="1200",
            heading=90,
            altitude=50,
            aircraft_type="C172",
            speed=120,
            altitude_trend=0,
            scratchpad="",
        )
        for key, direction in (
            (arcade.key.NUM_1, (-1, -1)),
            (arcade.key.NUM_2, (0, -1)),
            (arcade.key.NUM_3, (1, -1)),
            (arcade.key.NUM_4, (-1, 0)),
            (arcade.key.NUM_6, (1, 0)),
            (arcade.key.NUM_7, (-1, 1)),
            (arcade.key.NUM_8, (0, 1)),
            (arcade.key.NUM_9, (1, 1)),
        ):
            with self.subTest(key=key):
                display = SimpleNamespace(
                    selected_aircraft_id="A1",
                    data_block_directions={},
                    scratchpad_edit_id=None,
                )
                RadarDisplay.on_key_press(display, key, 0)
                self.assertEqual(display.data_block_directions["A1"], direction)
                _, x, y = RadarDisplay.secondary_return_layout(
                    snapshot, 100, 100, 10, direction
                )
                self.assertEqual(int(x > 100) - int(x < 100), direction[0])
                self.assertEqual(int(y > 100) - int(y < 100), direction[1])

    def test_overlapping_manual_blocks_are_separated_and_preferences_remain(self):
        aircraft = [
            SimpleNamespace(
                id=identifier,
                lat=latitude,
                lon=0,
                callsign=identifier,
                squawk="1200",
                heading=90,
                altitude=50,
                aircraft_model=SimpleNamespace(aircraft_type="C172"),
                speed=120,
                scratchpad="",
            )
            for identifier, latitude in (("A1", 500), ("A2", 500), ("A3", 500))
        ]
        display = SimpleNamespace(
            aircraft_list=SimpleNamespace(aircraft_list=aircraft),
            selected_aircraft_id="A1",
            scratchpad_edit_id=None,
            emergency_flash_elapsed=0,
            data_block_directions={"A1": (1, 0), "A2": (1, 0)},
            data_block_overlap_warned=False,
            data_block_labels={},
            secondary_radar_returns=[],
            width=1200,
            height=900,
            calculate_range_and_bearing=lambda lat, lon: (10, 0),
            convert_to_display_coordinates=lambda lat, lon: (lat, 450),
            is_visible_scope_position=lambda x, y: True,
            secondary_return_layout=RadarDisplay.secondary_return_layout,
        )
        RadarDisplay.capture_secondary_radar_returns(display)
        with patch(
            "arcade.Text",
            return_value=SimpleNamespace(content_width=80, content_height=60),
        ):
            layouts = RadarDisplay.layout_secondary_returns(display)
        self.assertEqual(len(layouts), 3)
        self.assertEqual((layouts[0].text_x, layouts[0].text_y), (540, 450))
        for i, first in enumerate(layouts):
            for second in layouts[i + 1 :]:
                self.assertTrue(
                    abs(first.text_x - second.text_x)
                    >= (first.width + second.width) / 2 + 4
                    or abs(first.text_y - second.text_y)
                    >= (first.height + second.height) / 2 + 4
                )
        self.assertEqual(display.data_block_directions, {"A1": (1, 0), "A2": (1, 0)})
        display.secondary_return_layouts = layouts
        display.display_type = display.ARTS_IIE = RadarDisplay.ARTS_IIE
        displaced = next(
            layout for layout in layouts if layout.snapshot.aircraft_id == "A2"
        )
        RadarDisplay.on_mouse_press(
            display,
            displaced.text_x,
            displaced.text_y,
            arcade.MOUSE_BUTTON_LEFT,
            0,
        )
        self.assertEqual(display.selected_aircraft_id, "A2")
        aircraft[1].lat = 700
        aircraft[2].lat = 900
        RadarDisplay.capture_secondary_radar_returns(display)
        with patch(
            "arcade.Text",
            return_value=SimpleNamespace(content_width=80, content_height=60),
        ):
            layouts = RadarDisplay.layout_secondary_returns(display)
        restored = next(
            layout for layout in layouts if layout.snapshot.aircraft_id == "A2"
        )
        self.assertEqual((restored.text_x, restored.text_y), (740, 450))
        aircraft[1].lat = 1199
        RadarDisplay.capture_secondary_radar_returns(display)
        with patch(
            "arcade.Text",
            return_value=SimpleNamespace(content_width=80, content_height=60),
        ):
            layouts = RadarDisplay.layout_secondary_returns(display)
        edge = next(layout for layout in layouts if layout.snapshot.aircraft_id == "A2")
        self.assertLessEqual(edge.text_x + edge.width / 2, display.width)


class RadarViewportTests(unittest.TestCase):
    def test_zoom_pan_and_reset_are_bounded_by_coverage(self):
        viewport = RadarViewport()
        viewport.pan(1, 0)
        self.assertEqual(viewport.pan_x, 0)
        viewport.zoom_by(4)
        viewport.pan(1, 1)
        x, y = viewport.transform(700, 500, 600, 450, 400)
        self.assertAlmostEqual(x, 600 + 100 * viewport.zoom - 20)
        self.assertAlmostEqual(y, 450 + 50 * viewport.zoom - 20)
        for _ in range(100):
            viewport.pan(1, 1)
        self.assertAlmostEqual(
            (viewport.pan_x**2 + viewport.pan_y**2) ** 0.5,
            400 * (1 - 1 / viewport.zoom),
        )
        viewport.zoom_by(-100)
        self.assertEqual((viewport.zoom, viewport.pan_x, viewport.pan_y), (1, 0, 0))
        viewport.zoom_by(100)
        viewport.zoom_by(100)
        self.assertEqual(viewport.zoom, 8)
        viewport.reset()
        self.assertEqual((viewport.zoom, viewport.pan_x, viewport.pan_y), (1, 0, 0))

    def test_existing_primary_return_moves_with_view_without_changing_detection(self):
        manager = RadarReturnManager()
        manager.add_return(700, 500)
        viewport = RadarViewport()
        viewport.zoom_by(1)
        self.assertAlmostEqual(viewport.zoom, 1.1)
        viewport.pan(1, 0)
        with patch("arcade.draw_circle_filled") as draw:
            manager.draw(lambda x, y: viewport.transform(x, y, 600, 450, 400))
        draw.assert_called_once()
        x, y, radius, color = draw.call_args.args
        self.assertAlmostEqual(x, 690)
        self.assertAlmostEqual(y, 505)
        self.assertEqual((radius, color), (2, (*arcade.color.ORANGE[:3], 255)))
        self.assertEqual(manager.radar_returns[0][:2], [700, 500])

    def test_offscreen_secondary_contacts_do_not_leave_data_blocks(self):
        snapshot = SimpleNamespace(aircraft_id="A1", latitude=0, longitude=0)
        display = SimpleNamespace(
            secondary_radar_returns=[snapshot],
            calculate_range_and_bearing=lambda lat, lon: (10, 0),
            convert_to_display_coordinates=lambda lat, lon: (1100, 450),
            is_visible_scope_position=lambda x, y: False,
            data_block_directions={},
            selected_aircraft_id=None,
            data_block_overlap_warned=False,
            data_block_labels={},
        )
        self.assertEqual(RadarDisplay.layout_secondary_returns(display), [])


if __name__ == "__main__":
    unittest.main()
