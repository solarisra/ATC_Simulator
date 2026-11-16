import math
import unittest
from itertools import pairwise
from types import SimpleNamespace
from unittest.mock import Mock, patch

import arcade

from Locations.Yuma.Scenarios.yuma import create_yuma_scenario
from simulator.core.aircraft_models import boeing_767_freighter, cessna_172
from simulator.core.atc import (
    ATCFacility,
    RadarControlState,
    TrackingPosition,
    TrackOwnership,
)
from simulator.core.constants import DISPLAY_RADIUS, FULL_ROTATION_TIME_SECONDS
from simulator.display.radar import (
    RadarDisplay,
    RadarReturnManager,
    RadarSweep,
    RadarViewport,
    leader_line_end,
)
from simulator.radio.voice_commands import handle_transmission


def enter_coordination(display, text="NONE"):
    for character in text.lower():
        RadarDisplay.on_key_press(display, ord(character), 0)
    RadarDisplay.on_key_press(display, arcade.key.ENTER, 0)
    RadarDisplay.on_key_press(display, arcade.key.Y, 0)


def coordination_display(owner=TrackingPosition.YUMA):
    track = TrackOwnership()
    track.owner = owner
    track.communications_owner = owner
    aircraft = SimpleNamespace(
        id="A1",
        lat=32,
        lon=-114,
        callsign="TEST",
        squawk="1200",
        heading=90,
        altitude=50,
        speed=100,
        scratchpad="",
        aircraft_model=cessna_172,
        track=track,
        landed=False,
        update_position=lambda delta_time: None,
    )
    display = Mock(
        aircraft_list=SimpleNamespace(aircraft_list=[aircraft]),
        atc_facility=ATCFacility.get_atc_facility_by_name("KNYL"),
        secondary_radar_returns=[],
        selected_aircraft_id="A1",
        scratchpad_edit_id=None,
        handoff_choice_id=None,
        handoff_message="",
        sweep=RadarSweep(),
        radar_return_manager=RadarReturnManager(),
        display_type=RadarDisplay.STARS,
        ARTS_IIE=RadarDisplay.ARTS_IIE,
        secondary_update_elapsed=0,
        emergency_flash_elapsed=0,
        calculate_range_and_bearing=lambda lat, lon: (10, 0),
    )
    display.capture_secondary_radar_returns = lambda: (
        RadarDisplay.capture_secondary_radar_returns(display)
    )
    display.capture_secondary_radar_returns()
    return display, aircraft


def clearance_display():
    aircraft_list, facility, strips = create_yuma_scenario()
    aircraft = next(strip.aircraft for strip in strips if strip.aircraft.id == "A3")
    aircraft.track.offer(TrackingPosition.YUMA)
    aircraft.track.accept(TrackingPosition.YUMA)
    aircraft.track.transfer_communications()
    aircraft.track.confirm_identification()
    display = SimpleNamespace(
        aircraft_list=aircraft_list,
        atc_facility=facility,
        selected_aircraft_id=aircraft.id,
        clearance_draft=None,
        coordination_draft=None,
        scratchpad_edit_id=None,
        handoff_choice_id=None,
        handoff_message="",
    )
    return display, aircraft


def type_clearance(display, text):
    RadarDisplay.on_key_press(display, arcade.key.G, 0)
    for character in text.lower():
        RadarDisplay.on_key_press(display, ord(character), 0)
    RadarDisplay.on_key_press(display, arcade.key.ENTER, 0)


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
            ui_camera=Mock(),
            sweep_sector=Mock(),
            transform_position=lambda x, y: viewport.transform(
                x, y, 600, 450, DISPLAY_RADIUS
            ),
        )
        with patch("arcade.draw_line") as line:
            RadarDisplay.draw_sweep(display)
        display.map_camera.use.assert_called_once()
        display.ui_camera.use.assert_called_once()
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
    def test_ident_flashes_data_block_with_return_but_handoff_only_flashes_return(self):
        display, _ = coordination_display()
        snapshot = display.secondary_radar_returns[0]
        for ident, handoff, visible, drawn in (
            (True, None, False, False),
            (True, None, True, True),
            (True, TrackingPosition.LOS_ANGELES, False, False),
            (True, TrackingPosition.LOS_ANGELES, True, True),
            (False, TrackingPosition.LOS_ANGELES, False, True),
            (False, None, False, True),
        ):
            with self.subTest(ident=ident, handoff=handoff, visible=visible):
                label = Mock()
                with (
                    patch("arcade.draw_circle_filled") as circle,
                    patch("arcade.draw_circle_outline") as selection,
                    patch("arcade.draw_line") as line,
                ):
                    RadarDisplay.draw_secondary_return(
                        snapshot._replace(ident=ident, handoff_target=handoff),
                        100,
                        200,
                        10,
                        selected=True,
                        text_size=(50, 30),
                        label=label,
                        flash_visible=visible,
                    )
                self.assertEqual(label.draw.called, drawn)
                self.assertEqual(line.called, drawn)
                self.assertEqual(circle.called, visible or not (ident or handoff))
                selection.assert_called_once()

    def test_heavy_marker_is_in_snapshot_not_aircraft_identity(self):
        display, aircraft = coordination_display()
        aircraft.callsign = "AAL381"
        aircraft.aircraft_model = boeing_767_freighter
        display.capture_secondary_radar_returns()
        self.assertEqual(display.secondary_radar_returns[0].callsign, "AAL381H")
        self.assertEqual(aircraft.callsign, "AAL381")

    def test_snapshot_updates_position_and_data_once_per_second(self):
        aircraft = SimpleNamespace(
            id="A1",
            lat=32.0,
            lon=-114.0,
            callsign="TEST",
            squawk="1200",
            heading=90,
            altitude=50,
            aircraft_model=cessna_172,
            speed=120,
            landed=False,
            update_position=lambda delta_time: None,
            distance=0,
            scratchpad="",
            track=TrackOwnership(),
        )
        display = SimpleNamespace(
            aircraft_list=SimpleNamespace(aircraft_list=[aircraft]),
            atc_facility=ATCFacility("Test", {"lat": 0, "lon": 0}),
            sweep=RadarSweep(),
            radar_return_manager=RadarReturnManager(),
            display_type=RadarDisplay.ARTS_IIE,
            ARTS_IIE=RadarDisplay.ARTS_IIE,
            center_x=600,
            center_y=450,
            secondary_update_elapsed=0,
            emergency_flash_elapsed=0,
            selected_aircraft_id=None,
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
                landed=False,
                scratchpad="",
                track=TrackOwnership(),
                aircraft_model=cessna_172,
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
            aircraft_model=cessna_172,
            speed=120,
            landed=False,
            scratchpad="",
            track=TrackOwnership(),
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
            patch("arcade.Text") as text,
        ):
            RadarDisplay.draw_secondary_return(
                snapshot, 100, 200, 15.5, text_size=(50, 30)
            )

        self.assertEqual(text.call_args.args[0], "TEST Y\n050  12\nC172 1200\n ")
        text.return_value.draw.assert_called_once()
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
            tracking_owner=TrackingPosition.YUMA,
            handoff_target=None,
            ident=False,
        )
        text, _, _ = RadarDisplay.secondary_return_layout(snapshot, 0, 0, 10)
        self.assertEqual(text, "N123 Y\n005  13\nC172 1200\n ")

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
            tracking_owner=TrackingPosition.YUMA,
            handoff_target=None,
            ident=False,
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
            self.assertEqual(cached.label.text, "TEST Y\n050  12\nC172 1200\n ")
            self.assertEqual((cached.width, cached.height), (50, 45))
            self.assertIs(
                RadarDisplay.get_data_block_label(display, snapshot, 10), cached
            )
            create_text.assert_called_once()
            snapshot.altitude = 60
            updated = RadarDisplay.get_data_block_label(display, snapshot, 10)
            self.assertEqual(updated.label.text, "TEST Y\n060  12\nC172 1200\n ")
            self.assertEqual(create_text.call_count, 2)
            snapshot.squawk = "0421"
            updated = RadarDisplay.get_data_block_label(display, snapshot, 10)
            self.assertEqual(updated.label.text, "TEST Y\n060  12\nC172 0421\n ")
            self.assertEqual(create_text.call_count, 3)

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
            tracking_owner=TrackingPosition.YUMA,
            handoff_target=None,
            ident=False,
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
            self.assertEqual(cached.label.text, "TEST Y EM\n050  12\nC172 7700\nABC")
            dimensions = cached.width, cached.height
            display.emergency_flash_elapsed = 0.5
            self.assertIs(
                RadarDisplay.get_data_block_label(display, snapshot, 10), cached
            )
            self.assertEqual(cached.label.text, "TEST Y\n050  12\nC172 7700\nABC")
            self.assertEqual((cached.width, cached.height), dimensions)
            display.emergency_flash_elapsed = 0
            RadarDisplay.get_data_block_label(display, snapshot, 10)
            self.assertIn("TEST Y EM\n", cached.label.text)
            for squawk in ("1200", "7500", "7600"):
                snapshot.squawk = squawk
                label = RadarDisplay.get_data_block_label(display, snapshot, 10)
                self.assertEqual(
                    label.label.text, f"TEST Y\n050  12\nC172 {squawk}\nABC"
                )

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
                landed=False,
                scratchpad="",
                track=TrackOwnership(),
                aircraft_model=cessna_172,
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
            handoff_choice_id=None,
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

    def test_selected_track_handoff_workflow_and_snapshot_updates(self):
        aircraft = SimpleNamespace(
            id="A1",
            lat=32,
            lon=-114,
            callsign="TEST",
            squawk="1200",
            heading=90,
            altitude=50,
            speed=100,
            scratchpad="KEEP",
            aircraft_model=cessna_172,
            track=TrackOwnership(),
            landed=False,
            update_position=lambda delta_time: None,
        )
        display = Mock(
            aircraft_list=SimpleNamespace(aircraft_list=[aircraft]),
            atc_facility=ATCFacility.get_atc_facility_by_name("KNYL"),
            secondary_radar_returns=[],
            selected_aircraft_id="A1",
            scratchpad_edit_id=None,
            handoff_choice_id=None,
            handoff_message="",
            sweep=RadarSweep(),
            radar_return_manager=RadarReturnManager(),
            display_type=RadarDisplay.STARS,
            ARTS_IIE=RadarDisplay.ARTS_IIE,
            secondary_update_elapsed=0,
            emergency_flash_elapsed=0,
            calculate_range_and_bearing=lambda lat, lon: (10, 0),
        )
        display.capture_secondary_radar_returns = lambda: (
            RadarDisplay.capture_secondary_radar_returns(display)
        )
        display.capture_secondary_radar_returns()
        RadarDisplay.on_key_press(display, arcade.key.H, 0)
        RadarDisplay.on_key_press(display, arcade.key.L, 0)
        RadarDisplay.on_key_press(display, arcade.key.ENTER, 0)
        self.assertIn("ENTER INFORMATION", display.handoff_message)
        self.assertIsNone(aircraft.track.handoff_target)
        enter_coordination(display)
        snapshot = display.secondary_radar_returns[0]
        self.assertEqual((snapshot.tracking_owner, snapshot.handoff_target), ("Y", "L"))
        self.assertIn(
            "TEST Y>L", RadarDisplay.secondary_return_layout(snapshot, 0, 0, 10)[0]
        )
        RadarDisplay.on_key_press(display, arcade.key.A, 0)
        self.assertEqual(aircraft.track.owner, TrackingPosition.YUMA)
        self.assertIn("NO INCOMING", display.handoff_message)
        RadarDisplay.on_update(display, 2.9)
        self.assertEqual(aircraft.track.owner, TrackingPosition.YUMA)
        RadarDisplay.on_update(display, 0.1)
        self.assertEqual(aircraft.track.owner, TrackingPosition.LOS_ANGELES)
        self.assertEqual(display.secondary_radar_returns[0].tracking_owner, "L")
        self.assertEqual(display.secondary_radar_returns[0].scratchpad, "KEEP")
        self.assertIn("RADAR CONTACT", display.handoff_message)
        self.assertEqual(aircraft.track.communications_owner, TrackingPosition.YUMA)
        RadarDisplay.on_key_press(display, arcade.key.C, 0)
        RadarDisplay.on_key_press(display, arcade.key.Y, 0)
        self.assertEqual(
            aircraft.track.communications_owner, TrackingPosition.LOS_ANGELES
        )

        RadarDisplay.on_key_press(display, arcade.key.I, 0)
        enter_coordination(display)
        self.assertEqual(display.secondary_radar_returns[0].handoff_target, "Y")
        RadarDisplay.on_update(display, 5)
        self.assertEqual(aircraft.track.owner, TrackingPosition.LOS_ANGELES)
        RadarDisplay.on_key_press(display, arcade.key.X, 0)
        self.assertIsNone(display.secondary_radar_returns[0].handoff_target)
        RadarDisplay.on_key_press(display, arcade.key.I, 0)
        enter_coordination(display)
        RadarDisplay.on_key_press(display, arcade.key.A, 0)
        self.assertEqual(aircraft.track.owner, TrackingPosition.LOS_ANGELES)
        RadarDisplay.on_key_press(display, arcade.key.Y, 0)
        self.assertEqual(display.secondary_radar_returns[0].tracking_owner, "Y")
        self.assertIsNone(display.secondary_radar_returns[0].handoff_target)
        self.assertTrue(aircraft.track.identification_confirmation_due)
        self.assertEqual(
            aircraft.track.communications_owner, TrackingPosition.LOS_ANGELES
        )
        RadarDisplay.on_key_press(display, arcade.key.C, 0)
        RadarDisplay.on_key_press(display, arcade.key.Y, 0)
        RadarDisplay.on_key_press(display, arcade.key.V, 0)
        self.assertFalse(aircraft.track.identification_confirmation_due)

        RadarDisplay.on_key_press(display, arcade.key.H, 0)
        RadarDisplay.on_key_press(display, arcade.key.A, 0)
        enter_coordination(display)
        self.assertEqual(display.secondary_radar_returns[0].handoff_target, "A")
        RadarDisplay.on_key_press(display, arcade.key.X, 0)
        self.assertEqual(aircraft.track.owner, TrackingPosition.YUMA)
        self.assertIsNone(display.secondary_radar_returns[0].handoff_target)
        RadarDisplay.on_key_press(display, arcade.key.H, 0)
        RadarDisplay.on_key_press(display, arcade.key.A, 0)
        enter_coordination(display)
        RadarDisplay.on_update(display, 3)
        self.assertEqual(display.secondary_radar_returns[0].tracking_owner, "A")
        RadarDisplay.on_key_press(display, arcade.key.C, 0)
        RadarDisplay.on_key_press(display, arcade.key.Y, 0)
        RadarDisplay.on_key_press(display, arcade.key.I, 0)
        enter_coordination(display)
        RadarDisplay.on_key_press(display, arcade.key.A, 0)
        RadarDisplay.on_key_press(display, arcade.key.Y, 0)
        self.assertEqual(display.secondary_radar_returns[0].tracking_owner, "Y")

    def test_sector_number_offers_handoff_without_transferring_communications(self):
        for digits, label, target in (
            ((arcade.key.KEY_9,), "ZLA SECTOR 9", TrackingPosition.LOS_ANGELES),
            (
                (arcade.key.KEY_1, arcade.key.KEY_0),
                "ZLA SECTOR 10",
                TrackingPosition.LOS_ANGELES,
            ),
            (
                (arcade.key.NUM_3, arcade.key.NUM_1),
                "ZLA SECTOR 31",
                TrackingPosition.LOS_ANGELES,
            ),
            (
                (arcade.key.KEY_4, arcade.key.KEY_2),
                "ZAB SECTOR 42",
                TrackingPosition.ALBUQUERQUE,
            ),
        ):
            with self.subTest(sector=label):
                display, aircraft = coordination_display()
                aircraft.radio_channel = "enroute_low"
                RadarDisplay.on_key_press(display, arcade.key.H, 0)
                for digit in digits:
                    RadarDisplay.on_key_press(display, digit, 0)
                self.assertIsNone(aircraft.track.handoff_target)
                RadarDisplay.on_key_press(display, arcade.key.ENTER, 0)
                self.assertEqual(aircraft.track.handoff_target, target)
                self.assertEqual(aircraft.track.handoff_information, label)
                self.assertIsNone(aircraft.track.pending_radio_channel)
                self.assertEqual(
                    display.secondary_radar_returns[0].handoff_target, target
                )
                self.assertIn(label, display.handoff_message)
                RadarDisplay.on_update(display, 3)
                self.assertEqual(aircraft.track.owner, target)
                self.assertEqual(
                    aircraft.track.communications_owner, TrackingPosition.YUMA
                )
                self.assertEqual(aircraft.radio_channel, "enroute_low")

    def test_sector_entry_handles_invalid_input_cancel_and_control_limit(self):
        display, aircraft = coordination_display()
        RadarDisplay.on_key_press(display, arcade.key.H, 0)
        RadarDisplay.on_key_press(display, arcade.key.KEY_9, 0)
        RadarDisplay.on_key_press(display, arcade.key.KEY_9, 0)
        RadarDisplay.on_key_press(display, arcade.key.ENTER, 0)
        self.assertIn("UNKNOWN SECTOR", display.handoff_message)
        self.assertIsNone(aircraft.track.handoff_target)
        RadarDisplay.on_key_press(display, arcade.key.BACKSPACE, 0)
        RadarDisplay.on_key_press(display, arcade.key.ESCAPE, 0)
        self.assertIsNone(display.handoff_choice_id)
        self.assertEqual(display.handoff_sector_text, "")
        aircraft.altitude = 231
        RadarDisplay.on_key_press(display, arcade.key.H, 0)
        RadarDisplay.on_key_press(display, arcade.key.KEY_4, 0)
        RadarDisplay.on_key_press(display, arcade.key.KEY_2, 0)
        RadarDisplay.on_key_press(display, arcade.key.ENTER, 0)
        self.assertIn("HANDOFF TO L REQUIRED", display.handoff_message)
        self.assertIsNone(aircraft.track.handoff_target)

    def test_yuma_upper_limit_requires_manual_la_handoff(self):
        aircraft = SimpleNamespace(
            id="A1",
            lat=32,
            lon=-114,
            callsign="TEST",
            squawk="1200",
            heading=90,
            altitude=230,
            speed=100,
            scratchpad="",
            aircraft_model=cessna_172,
            track=TrackOwnership(),
            landed=True,
        )
        display = Mock(
            aircraft_list=SimpleNamespace(aircraft_list=[aircraft]),
            atc_facility=ATCFacility.get_atc_facility_by_name("KNYL"),
            secondary_radar_returns=[],
            selected_aircraft_id="A1",
            scratchpad_edit_id=None,
            handoff_choice_id=None,
            handoff_message="",
            sweep=RadarSweep(),
            radar_return_manager=RadarReturnManager(),
            display_type=RadarDisplay.STARS,
            ARTS_IIE=RadarDisplay.ARTS_IIE,
            secondary_update_elapsed=0,
            emergency_flash_elapsed=0,
            calculate_range_and_bearing=lambda lat, lon: (10, 0),
        )
        display.capture_secondary_radar_returns = lambda: (
            RadarDisplay.capture_secondary_radar_returns(display)
        )
        display.capture_secondary_radar_returns()
        self.assertEqual(RadarDisplay.control_limit_warning(display), "")
        RadarDisplay.on_key_press(display, arcade.key.H, 0)
        RadarDisplay.on_key_press(display, arcade.key.A, 0)
        enter_coordination(display)
        self.assertEqual(aircraft.track.handoff_target, TrackingPosition.ALBUQUERQUE)

        aircraft.landed = False
        aircraft.update_position = lambda delta: setattr(aircraft, "altitude", 230.01)
        RadarDisplay.on_update(display, 3)
        aircraft.landed = True
        self.assertEqual(aircraft.altitude, 230.01)
        self.assertEqual(aircraft.track.owner, TrackingPosition.YUMA)
        self.assertIsNone(aircraft.track.handoff_target)
        self.assertIsNone(display.secondary_radar_returns[0].handoff_target)
        self.assertIn("HANDOFF TO L REQUIRED", display.handoff_message)
        self.assertIn("TEST", RadarDisplay.control_limit_warning(display))
        RadarDisplay.on_key_press(display, arcade.key.H, 0)
        RadarDisplay.on_key_press(display, arcade.key.A, 0)
        self.assertIsNone(aircraft.track.handoff_target)
        self.assertIn("HANDOFF TO L REQUIRED", display.handoff_message)

        RadarDisplay.on_key_press(display, arcade.key.H, 0)
        RadarDisplay.on_key_press(display, arcade.key.L, 0)
        enter_coordination(display)
        RadarDisplay.on_update(display, 2.9)
        self.assertIn("TEST", RadarDisplay.control_limit_warning(display))
        RadarDisplay.on_update(display, 0.1)
        self.assertEqual(aircraft.track.owner, TrackingPosition.LOS_ANGELES)
        self.assertEqual(RadarDisplay.control_limit_warning(display), "")
        RadarDisplay.on_key_press(display, arcade.key.C, 0)
        RadarDisplay.on_key_press(display, arcade.key.Y, 0)
        RadarDisplay.on_key_press(display, arcade.key.I, 0)
        self.assertIsNone(aircraft.track.handoff_target)
        self.assertIn("YUMA CANNOT ACCEPT", display.handoff_message)

        aircraft.altitude = 230
        RadarDisplay.on_key_press(display, arcade.key.I, 0)
        enter_coordination(display)
        self.assertEqual(aircraft.track.handoff_target, TrackingPosition.YUMA)
        aircraft.altitude = 231
        RadarDisplay.on_key_press(display, arcade.key.A, 0)
        self.assertEqual(aircraft.track.owner, TrackingPosition.LOS_ANGELES)
        self.assertIn("YUMA CANNOT ACCEPT", display.handoff_message)
        aircraft.altitude = 230
        RadarDisplay.on_key_press(display, arcade.key.A, 0)
        aircraft.altitude = 231
        RadarDisplay.on_key_press(display, arcade.key.Y, 0)
        self.assertEqual(aircraft.track.owner, TrackingPosition.LOS_ANGELES)
        self.assertIn("YUMA CANNOT ACCEPT", display.handoff_message)
        aircraft.altitude = 230
        RadarDisplay.on_key_press(display, arcade.key.Y, 0)
        self.assertEqual(aircraft.track.owner, TrackingPosition.YUMA)

    def test_control_limit_warning_includes_all_overdue_tracks(self):
        aircraft = [
            SimpleNamespace(
                callsign=name,
                altitude=altitude,
                track=TrackOwnership(),
                aircraft_model=cessna_172,
            )
            for name, altitude in (("ONE", 231), ("TWO", 240), ("LEVEL", 230))
        ]
        display = SimpleNamespace(
            aircraft_list=SimpleNamespace(aircraft_list=aircraft),
            atc_facility=ATCFacility.get_atc_facility_by_name("KNYL"),
        )
        warning = RadarDisplay.control_limit_warning(display)
        self.assertIn("ONE", warning)
        self.assertIn("TWO", warning)
        self.assertNotIn("LEVEL", warning)

    def test_outgoing_point_out_and_traffic_coordination(self):
        display, aircraft = coordination_display()
        RadarDisplay.on_key_press(display, arcade.key.P, 0)
        RadarDisplay.on_key_press(display, arcade.key.L, 0)
        enter_coordination(display, "MAINTAIN 5000")
        point_out = aircraft.track.coordination
        self.assertEqual(point_out.information, "MAINTAIN 5000")
        self.assertFalse(point_out.approved)
        RadarDisplay.on_update(display, 3)
        self.assertTrue(point_out.approved)
        self.assertEqual(aircraft.track.owner, TrackingPosition.YUMA)
        self.assertEqual(aircraft.track.communications_owner, TrackingPosition.YUMA)
        RadarDisplay.on_key_press(display, arcade.key.D, 0)
        self.assertIsNone(aircraft.track.coordination)
        self.assertIs(aircraft.track.coordination_history[-1], point_out)

        RadarDisplay.on_key_press(display, arcade.key.T, 0)
        RadarDisplay.on_key_press(display, arcade.key.A, 0)
        for key in "none":
            RadarDisplay.on_key_press(display, ord(key), 0)
        RadarDisplay.on_key_press(display, arcade.key.ENTER, 0)
        self.assertIn("REQUIRES RESTRICTIONS", display.handoff_message)
        self.assertIsNone(aircraft.track.coordination)
        for _ in range(4):
            RadarDisplay.on_key_press(display, arcade.key.BACKSPACE, 0)
        enter_coordination(display, "ABC MAINTAIN 5000")
        traffic = aircraft.track.coordination
        RadarDisplay.on_update(display, 3)
        self.assertTrue(traffic.approved)
        self.assertIn("TRAFFIC OBSERVED", display.handoff_message)
        self.assertEqual(aircraft.track.owner, TrackingPosition.YUMA)
        self.assertEqual(aircraft.track.communications_owner, TrackingPosition.YUMA)

    def test_incoming_point_out_and_traffic_need_acknowledgment(self):
        display, aircraft = coordination_display(TrackingPosition.LOS_ANGELES)
        RadarDisplay.on_key_press(display, arcade.key.P, 0)
        enter_coordination(display, "MAINTAIN 6000")
        RadarDisplay.on_update(display, 10)
        self.assertFalse(aircraft.track.coordination.approved)
        RadarDisplay.on_key_press(display, arcade.key.A, 0)
        self.assertFalse(aircraft.track.coordination.approved)
        RadarDisplay.on_key_press(display, arcade.key.Y, 0)
        self.assertTrue(aircraft.track.coordination.approved)
        self.assertEqual(aircraft.track.owner, TrackingPosition.LOS_ANGELES)
        self.assertEqual(
            aircraft.track.communications_owner, TrackingPosition.LOS_ANGELES
        )
        RadarDisplay.on_key_press(display, arcade.key.D, 0)
        RadarDisplay.on_key_press(display, arcade.key.T, 0)
        enter_coordination(display, "ABC MAINTAIN 6000")
        RadarDisplay.on_key_press(display, arcade.key.X, 0)
        self.assertIsNone(aircraft.track.coordination)
        self.assertFalse(aircraft.track.coordination_history[-1].approved)
        RadarDisplay.on_key_press(display, arcade.key.T, 0)
        enter_coordination(display, "ABC MAINTAIN 6000")
        RadarDisplay.on_key_press(display, arcade.key.A, 0)
        RadarDisplay.on_key_press(display, arcade.key.Y, 0)
        self.assertTrue(aircraft.track.coordination.approved)
        self.assertEqual(display.handoff_message, "TRAFFIC OBSERVED")

    def test_selected_aircraft_details_show_extra_data(self):
        snapshot = SimpleNamespace(
            aircraft_id="A1",
            callsign="TEST",
            heading=90,
            squawk="1200",
            speed=125,
            latitude=32,
            longitude=-114,
            tracking_owner=TrackingPosition.YUMA,
            handoff_target=None,
        )
        text = unittest.mock.Mock()
        text.text = ""
        display = SimpleNamespace(
            aircraft_list=SimpleNamespace(
                aircraft_list=[SimpleNamespace(id="A1", track=TrackOwnership())]
            ),
            selected_aircraft_id="A1",
            atc_facility=ATCFacility.get_atc_facility_by_name("KNYL"),
            secondary_radar_returns=[snapshot],
            scratchpad_edit_id=None,
            handoff_choice_id=None,
            coordination_draft=None,
            handoff_message="",
            calculate_range_and_bearing=lambda lat, lon: (15.5, 0),
            selected_details_text=text,
        )
        RadarDisplay.draw_selected_aircraft_details(display)
        self.assertEqual(
            text.text,
            "SELECTED TEST\nHDG 080\nSQK 1200\nSPD 125 KT\nRNG 15.5 NM\nTRACK Y\nCOMMS Y",
        )
        text.draw.assert_called_once()
        display.selected_aircraft_id = None
        RadarDisplay.draw_selected_aircraft_details(display)
        text.draw.assert_called_once()

    def test_coordination_position_uses_local_airport_identifier(self):
        display, _ = coordination_display()
        display.coordination_draft = SimpleNamespace(
            aircraft_id="A1", stage="offer", kind="HANDOFF", target="L", text="NONE"
        )
        display.selected_details_text = Mock()
        RadarDisplay.draw_selected_aircraft_details(display)
        self.assertIn("10.0 NM FROM NYL", display.selected_details_text.text)
        self.assertIn("POSITION 350/", display.selected_details_text.text)
        self.assertNotIn("KNYL", display.selected_details_text.text)

    def test_controller_clearances_control_guidance_and_read_back(self):
        display, aircraft = clearance_display()
        guidance = aircraft.flight_guidance
        original_route = guidance.strip.flight_plan.route
        initial_fix = guidance.route[guidance.next_index].name
        type_clearance(display, "HDG 360")
        self.assertIsNone(display.clearance_draft)
        self.assertAlmostEqual(guidance.vector_heading, 10 + 14 / 60)
        self.assertIn("HEADING 360", display.handoff_message)
        aircraft.update_position(10)
        self.assertEqual(guidance.route[guidance.next_index].name, initial_fix)
        type_clearance(display, "ALT 6000")
        aircraft.update_position(20)
        self.assertEqual(guidance.assigned_altitude, 6000)
        self.assertIn("MAINTAIN 6000 FT", display.handoff_message)
        later = guidance.route[guidance.next_index + 1].name
        type_clearance(display, f"DCT {later}")
        self.assertIsNone(guidance.vector_heading)
        self.assertEqual(guidance.route[guidance.next_index].name, later)
        self.assertEqual(guidance.strip.flight_plan.route, original_route)
        type_clearance(display, "HDG 180")
        type_clearance(display, "RESUME")
        self.assertIsNone(guidance.vector_heading)
        self.assertEqual(guidance.route[guidance.next_index].name, later)
        type_clearance(display, "ALT CLR")
        self.assertIsNone(guidance.assigned_altitude)

    def test_clearances_reject_invalid_or_uncontrolled_aircraft(self):
        display, aircraft = clearance_display()
        guidance = aircraft.flight_guidance
        type_clearance(display, "HDG 361")
        self.assertIsNone(guidance.vector_heading)
        self.assertIn("001 TO 360", display.handoff_message)
        RadarDisplay.on_key_press(display, arcade.key.ESCAPE, 0)
        type_clearance(display, "DCT NOTAFIX")
        self.assertIn("REMAINING ROUTE", display.handoff_message)
        RadarDisplay.on_key_press(display, arcade.key.ESCAPE, 0)
        type_clearance(display, "ALT 24000")
        self.assertIn("CONTROL LIMIT", display.handoff_message)
        RadarDisplay.on_key_press(display, arcade.key.ESCAPE, 0)
        aircraft.track.communications_owner = TrackingPosition.LOS_ANGELES
        RadarDisplay.on_key_press(display, arcade.key.G, 0)
        self.assertIn("OWN TRACK AND COMMUNICATIONS", display.handoff_message)
        self.assertIsNone(guidance.vector_heading)
        aircraft.track.communications_owner = TrackingPosition.YUMA
        aircraft.track.offer(TrackingPosition.LOS_ANGELES, "NONE")
        RadarDisplay.on_key_press(display, arcade.key.G, 0)
        self.assertIn("PENDING HANDOFF", display.handoff_message)
        self.assertIsNone(guidance.vector_heading)
        aircraft.track.cancel()
        RadarDisplay.on_key_press(display, arcade.key.G, 0)
        for character in "hdg 090":
            RadarDisplay.on_key_press(display, ord(character), 0)
        aircraft.track.communications_owner = TrackingPosition.LOS_ANGELES
        RadarDisplay.on_key_press(display, arcade.key.ENTER, 0)
        self.assertIn("OWN TRACK AND COMMUNICATIONS", display.handoff_message)
        self.assertIsNone(guidance.vector_heading)

    def test_clearances_remain_available_after_handoff_until_comms_transfer(self):
        display, aircraft = clearance_display()
        display.secondary_radar_returns = []
        RadarDisplay.on_key_press(display, arcade.key.H, 0)
        RadarDisplay.on_key_press(display, arcade.key.KEY_9, 0)
        RadarDisplay.on_key_press(display, arcade.key.ENTER, 0)
        self.assertEqual(aircraft.track.handoff_information, "ZLA SECTOR 9")
        aircraft.track.advance(3)
        type_clearance(display, "HDG 270")
        self.assertIn("HEADING 270", display.handoff_message)
        self.assertAlmostEqual(aircraft.flight_guidance.vector_heading, 280 + 14 / 60)
        reply = handle_transmission(
            "Devil 279 contact Los Angeles Center 291.7",
            display.aircraft_list.aircraft_list,
            display.atc_facility,
            {"enroute_high"},
        )
        self.assertEqual(reply.channel, "enroute_high")
        self.assertEqual(aircraft.radio_channel, "zla9_high")
        self.assertEqual(
            aircraft.track.communications_owner, TrackingPosition.LOS_ANGELES
        )
        RadarDisplay.on_key_press(display, arcade.key.G, 0)
        self.assertIn("OWN TRACK AND COMMUNICATIONS", display.handoff_message)

    def test_ground_departure_cannot_begin_clearance_edit(self):
        display, _ = clearance_display()
        display.selected_aircraft_id = "A8"
        RadarDisplay.on_key_press(display, arcade.key.G, 0)
        self.assertIsNone(display.clearance_draft)
        self.assertIn("NOT AIRBORNE", display.handoff_message)

    def test_leader_lines_remain_visible_for_wide_blocks_in_all_directions(self):
        snapshot = SimpleNamespace(
            aircraft_id="A1",
            latitude=0,
            longitude=0,
            heading=0,
            callsign="TEST",
            squawk="1200",
            altitude=50,
            speed=120,
            aircraft_type="C172",
            altitude_trend=0,
            scratchpad="W" * 16,
            tracking_owner=TrackingPosition.YUMA,
            handoff_target=None,
            ident=False,
            radar_control_state=RadarControlState.UNCONTROLLED,
        )
        display = Mock(
            secondary_radar_returns=[snapshot],
            display_type=RadarDisplay.STARS,
            data_block_labels={},
            selected_aircraft_id=None,
            data_block_overlap_warned=False,
            width=1200,
            height=900,
            ui_scale=1.0,
            calculate_range_and_bearing=lambda lat, lon: (10, 0),
            convert_to_display_coordinates=lambda lat, lon: (500, 450),
            is_visible_scope_position=lambda x, y: True,
            secondary_return_layout=RadarDisplay.secondary_return_layout,
        )
        for direction in (
            (0, 1),
            (1, 1),
            (1, 0),
            (1, -1),
            (0, -1),
            (-1, -1),
            (-1, 0),
            (-1, 1),
        ):
            with self.subTest(direction=direction):
                display.data_block_directions = {"A1": direction}
                with patch.object(
                    RadarDisplay,
                    "get_data_block_label",
                    return_value=SimpleNamespace(width=128, height=68),
                ):
                    layout = RadarDisplay.layout_secondary_returns(display)[0]
                with (
                    patch("arcade.draw_circle_filled"),
                    patch("arcade.draw_line") as line,
                    patch("arcade.Text"),
                ):
                    RadarDisplay.draw_secondary_return(
                        snapshot,
                        layout.x,
                        layout.y,
                        layout.distance,
                        text_position=(layout.text_x, layout.text_y),
                        text_size=(layout.width, layout.height),
                    )
                x1, y1, x2, y2 = line.call_args.args[:4]
                self.assertGreaterEqual(math.hypot(x2 - x1, y2 - y1), 12 - 1e-8)
                self.assertEqual(
                    int(layout.text_x > x1) - int(layout.text_x < x1), direction[0]
                )
                self.assertEqual(
                    int(layout.text_y > y1) - int(layout.text_y < y1), direction[1]
                )

    def test_crowded_blocks_preserve_leader_lines_even_if_they_overlap(self):
        snapshots = [
            SimpleNamespace(aircraft_id=identifier, latitude=0, longitude=0, heading=90)
            for identifier in ("A1", "A2")
        ]
        display = Mock(
            secondary_radar_returns=snapshots,
            display_type=RadarDisplay.STARS,
            data_block_labels={},
            selected_aircraft_id=None,
            data_block_directions={"A1": (1, 0), "A2": (1, 0)},
            data_block_overlap_warned=False,
            width=400,
            height=160,
            ui_scale=1.0,
            calculate_range_and_bearing=lambda lat, lon: (10, 0),
            convert_to_display_coordinates=lambda lat, lon: (50, 80),
            is_visible_scope_position=lambda x, y: True,
            secondary_return_layout=lambda snapshot, x, y, distance, direction: (
                "",
                x + 40,
                y,
            ),
        )
        with (
            patch.object(
                RadarDisplay,
                "get_data_block_label",
                return_value=SimpleNamespace(width=200, height=120),
            ),
            self.assertLogs("simulator.display.radar", level="WARNING"),
        ):
            layouts = RadarDisplay.layout_secondary_returns(display)
        self.assertTrue(display.data_block_overlap_warned)
        for layout in layouts:
            end_x, end_y = leader_line_end(
                layout.x,
                layout.y,
                layout.text_x,
                layout.text_y,
                layout.width,
                layout.height,
            )
            self.assertGreaterEqual(
                math.hypot(end_x - layout.x, end_y - layout.y), 12 - 1e-8
            )

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
                aircraft_model=cessna_172,
                speed=120,
                landed=False,
                scratchpad="",
                track=TrackOwnership(),
            )
            for identifier, latitude in (("A1", 100), ("A2", 300))
        ]
        display = SimpleNamespace(
            aircraft_list=SimpleNamespace(aircraft_list=aircraft),
            display_type=RadarDisplay.STARS,
            ARTS_IIE=RadarDisplay.ARTS_IIE,
            selected_aircraft_id=None,
            scratchpad_edit_id=None,
            handoff_choice_id=None,
            handoff_message="",
            emergency_flash_elapsed=0,
            data_block_directions={},
            secondary_return_layouts=[],
            secondary_radar_returns=[],
            data_block_overlap_warned=False,
            data_block_labels={},
            width=1200,
            height=900,
            ui_scale=1.0,
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
            tracking_owner=TrackingPosition.YUMA,
            handoff_target=None,
            ident=False,
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
                    handoff_choice_id=None,
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
                aircraft_model=cessna_172,
                speed=120,
                landed=False,
                scratchpad="",
                track=TrackOwnership(),
            )
            for identifier, latitude in (("A1", 500), ("A2", 500), ("A3", 500))
        ]
        display = SimpleNamespace(
            aircraft_list=SimpleNamespace(aircraft_list=aircraft),
            display_type=RadarDisplay.STARS,
            selected_aircraft_id="A1",
            scratchpad_edit_id=None,
            handoff_choice_id=None,
            handoff_message="",
            emergency_flash_elapsed=0,
            data_block_directions={"A1": (1, 0), "A2": (1, 0)},
            data_block_overlap_warned=False,
            data_block_labels={},
            secondary_radar_returns=[],
            width=1200,
            height=900,
            ui_scale=1.0,
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
        self.assertEqual((layouts[0].text_x, layouts[0].text_y), (552, 450))
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
        display.ARTS_IIE = RadarDisplay.ARTS_IIE
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
        self.assertEqual((restored.text_x, restored.text_y), (752, 450))
        aircraft[1].lat = 1199
        RadarDisplay.capture_secondary_radar_returns(display)
        with patch(
            "arcade.Text",
            return_value=SimpleNamespace(content_width=80, content_height=60),
        ):
            layouts = RadarDisplay.layout_secondary_returns(display)
        edge = next(layout for layout in layouts if layout.snapshot.aircraft_id == "A2")
        self.assertLessEqual(edge.text_x + edge.width / 2, display.width)
        end_x, end_y = leader_line_end(
            edge.x, edge.y, edge.text_x, edge.text_y, edge.width, edge.height
        )
        self.assertGreaterEqual(math.hypot(end_x - edge.x, end_y - edge.y), 12 - 1e-8)


class RadarViewportTests(unittest.TestCase):
    def test_degree_markings_are_cached_per_scope_shape(self):
        display = SimpleNamespace(
            degree_markings={},
            atc_facility=ATCFacility.get_atc_facility_by_name("KNYL"),
        )
        with (
            patch("simulator.display.radar.pyglet.graphics.Batch") as batch,
            patch("arcade.Text") as text,
        ):
            RadarDisplay.draw_degree_markings(display, 600, 450, 424)
            first = text.call_args_list[0].args
            self.assertAlmostEqual(
                first[1], 600 + 424 * math.sin(math.radians(10 + 14 / 60))
            )
            self.assertAlmostEqual(
                first[2], 450 + 424 * math.cos(math.radians(10 + 14 / 60))
            )
            RadarDisplay.draw_degree_markings(display, 600, 450, 424)
            self.assertEqual(text.call_count, 24)
            self.assertEqual(batch.return_value.draw.call_count, 2)
            RadarDisplay.draw_degree_markings(display, 600, 450, 1200, 900)
            self.assertEqual(text.call_count, 48)
            self.assertEqual(batch.call_count, 2)

    def test_arts_masks_secondary_returns_before_drawing_border_and_legend(self):
        events = []
        snapshot = SimpleNamespace(aircraft_id="A1")
        layout = SimpleNamespace(
            snapshot=snapshot,
            x=995,
            y=450,
            distance=99,
            text_x=900,
            text_y=450,
            width=100,
            height=60,
        )
        overlays = Mock()
        overlays.draw_legend.side_effect = lambda: events.append("legend")
        mask = Mock()
        mask.draw.side_effect = lambda: events.append("mask")
        display = SimpleNamespace(
            gis_overlays=overlays,
            clear=Mock(),
            display_type=RadarDisplay.ARTS_IIE,
            ARTS_IIE=RadarDisplay.ARTS_IIE,
            STARS=RadarDisplay.STARS,
            map_camera=Mock(),
            ui_camera=Mock(),
            radar_viewport=SimpleNamespace(
                zoom=1, pan_x=0, pan_y=0, camera_position=Mock(return_value=(600, 450))
            ),
            is_visible_scope_position=Mock(return_value=True),
            transform_position=Mock(),
            draw_sweep=Mock(),
            radar_return_manager=Mock(),
            scope_mask=mask,
            draw_arts_iie=Mock(side_effect=lambda: events.append("border")),
            layout_secondary_returns=Mock(return_value=[layout]),
            draw_secondary_return=Mock(
                side_effect=lambda *args, **kwargs: events.append("return")
            ),
            data_block_labels={"A1": SimpleNamespace(label=Mock())},
            selected_aircraft_id=None,
            emergency_flash_elapsed=0,
            draw_selected_aircraft_details=Mock(),
            atc_facility=Mock(),
            aircraft_list=SimpleNamespace(aircraft_list=[]),
            strip_panel=Mock(),
            departure_checkins=[],
            communications_panel=Mock(),
        )
        RadarDisplay.on_draw(display)
        self.assertEqual(events, ["return", "mask", "border", "legend"])

    def test_arts_data_blocks_stay_inside_circular_scope_near_edges(self):
        snapshot = SimpleNamespace(
            aircraft_id="A1",
            latitude=0,
            longitude=0,
            heading=0,
            callsign="TEST",
            squawk="1200",
            altitude=50,
            speed=120,
            aircraft_type="C172",
            altitude_trend=0,
            scratchpad="",
            tracking_owner=TrackingPosition.YUMA,
            handoff_target=None,
            ident=False,
        )
        for dx, dy in (
            (1, 0),
            (1, 1),
            (0, 1),
            (-1, 1),
            (-1, 0),
            (-1, -1),
            (0, -1),
            (1, -1),
        ):
            with self.subTest(direction=(dx, dy)):
                length = math.hypot(dx, dy)
                x = 600 + (DISPLAY_RADIUS - 5) * dx / length
                y = 450 + (DISPLAY_RADIUS - 5) * dy / length
                display = SimpleNamespace(
                    secondary_radar_returns=[snapshot],
                    calculate_range_and_bearing=lambda lat, lon: (99, 0),
                    convert_to_display_coordinates=lambda lat, lon, x=x, y=y: (x, y),
                    is_visible_scope_position=lambda x, y: (
                        math.hypot(x - 600, y - 450) <= DISPLAY_RADIUS
                    ),
                    secondary_return_layout=RadarDisplay.secondary_return_layout,
                    data_block_directions={"A1": (dx, dy)},
                    selected_aircraft_id=None,
                    data_block_overlap_warned=False,
                    data_block_labels={},
                    display_type=RadarDisplay.ARTS_IIE,
                    width=1200,
                    height=900,
                    ui_scale=1.0,
                )
                with patch.object(
                    RadarDisplay,
                    "get_data_block_label",
                    return_value=SimpleNamespace(width=100, height=60),
                ):
                    layout = RadarDisplay.layout_secondary_returns(display)[0]
                for corner_x in (layout.text_x - 50, layout.text_x + 50):
                    for corner_y in (layout.text_y - 30, layout.text_y + 30):
                        self.assertLessEqual(
                            math.hypot(corner_x - 600, corner_y - 450),
                            DISPLAY_RADIUS + 1e-8,
                        )
                end_x, end_y = leader_line_end(
                    layout.x, layout.y, layout.text_x, layout.text_y, 100, 60
                )
                self.assertGreaterEqual(
                    math.hypot(end_x - layout.x, end_y - layout.y), 12 - 1e-8
                )

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

    def test_radar_blocks_do_not_extend_into_communications_panel(self):
        snapshot = SimpleNamespace(aircraft_id="A1", latitude=0, longitude=0)
        display = SimpleNamespace(
            secondary_radar_returns=[snapshot],
            display_type=RadarDisplay.STARS,
            calculate_range_and_bearing=lambda lat, lon: (10, 0),
            convert_to_display_coordinates=lambda lat, lon: (500, 890),
            is_visible_scope_position=lambda x, y: True,
            secondary_return_layout=lambda *args: ("", 500, 950),
            data_block_directions={},
            selected_aircraft_id=None,
            data_block_overlap_warned=False,
            data_block_labels={},
            width=1640,
            height=1020,
            ui_scale=1.0,
        )
        with patch.object(
            RadarDisplay,
            "get_data_block_label",
            return_value=SimpleNamespace(width=100, height=40),
        ):
            layouts = RadarDisplay.layout_secondary_returns(display)
        self.assertEqual(len(layouts), 1)
        self.assertLessEqual(layouts[0].text_y + layouts[0].height / 2, 900)


if __name__ == "__main__":
    unittest.main()
