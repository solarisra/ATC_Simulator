import runpy
import unittest
from collections import Counter
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch

import arcade

from Locations.Yuma.Scenarios.yuma import create_yuma_scenario
from simulator.core.aircraft_models import boeing_767_freighter
from simulator.core.atc import FlightPlan, FlightStrip
from simulator.core.constants import SCREEN_WIDTH
from simulator.display.flight_strips import (
    CHECKINS_TOP,
    LIST_TOP,
    PANEL_WIDTH,
    STRIP_COLUMNS,
    STRIP_HEIGHT,
    STRIP_LEFT,
    STRIP_SHIFT,
    VISIBLE_STRIPS,
    FlightStripPanel,
    terminal_strip_fields,
)
from simulator.display.radar import RadarDisplay, RadarViewport


def make_panel(count):
    aircraft = [
        SimpleNamespace(
            id=f"A{i}",
            callsign=f"TEST{i}",
            aircraft_model=SimpleNamespace(
                aircraft_type="C172", max_takeoff_weight=1049
            ),
            flight_rules="VFR",
            squawk="1200",
            target_altitude=None,
        )
        for i in range(count)
    ]
    strips = [
        FlightStrip(
            item.id, item, FlightPlan(item.id, "KNYL", "KIPL", "DCT", 5500, 110)
        )
        for item in aircraft
    ]
    aircraft_list = SimpleNamespace(aircraft_list=aircraft)
    with patch("simulator.display.flight_strips.arcade.Text"):
        panel = FlightStripPanel(strips, aircraft_list)
    return panel, aircraft, strips


class FlightStripTests(unittest.TestCase):
    def test_heavy_marker_is_drawn_on_strip(self):
        panel, aircraft, _ = make_panel(1)
        aircraft[0].callsign = "AAL381"
        aircraft[0].aircraft_model = boeing_767_freighter
        with (
            patch("arcade.draw_rect_filled"),
            patch("arcade.draw_line"),
            patch.object(panel, "draw_field") as fields,
        ):
            panel.draw(aircraft[0].id)
        self.assertIn("AAL381H", [call.args[0] for call in fields.call_args_list])
        self.assertIn("AAL381H", panel.footer.text)
        self.assertEqual(aircraft[0].callsign, "AAL381")

    def test_departure_strip_displays_scheduled_utc(self):
        panel, aircraft, _ = make_panel(1)
        panel.airport_code = "KNYL"
        aircraft[0].departure = SimpleNamespace(
            state="waiting", scheduled_utc=datetime(2026, 11, 16, 0, 3, 25, tzinfo=UTC)
        )
        with (
            patch("arcade.draw_rect_filled"),
            patch("arcade.draw_line"),
            patch.object(panel, "draw_field") as fields,
        ):
            panel.draw(aircraft[0].id)
        self.assertIn("0003Z", [call.args[0] for call in fields.call_args_list])
        self.assertIn("00:03:25 UTC", panel.footer.text)

    def test_departure_checkins_have_separate_area_above_strips(self):
        with patch("simulator.display.flight_strips.arcade.Text") as text_factory:
            FlightStripPanel([], SimpleNamespace(aircraft_list=[]))
        checkin_args = text_factory.call_args_list[2]
        self.assertGreaterEqual(checkin_args.args[1], SCREEN_WIDTH)
        self.assertLessEqual(
            checkin_args.args[1] + checkin_args.kwargs["width"],
            SCREEN_WIDTH + PANEL_WIDTH,
        )
        self.assertEqual(checkin_args.args[2], CHECKINS_TOP)
        panel, aircraft, _ = make_panel(1)
        panel.checkins = Mock()
        messages = [
            "LIFE12: YUMA DEPARTURE, 600 FT, CLIMBING 2500 FT",
            "N380CJ: YUMA DEPARTURE, 1200 FT, CLIMBING 17000 FT",
            "REACH47: YUMA DEPARTURE, 600 FT, CLIMBING 16000 FT",
        ]
        with (
            patch("arcade.draw_rect_filled"),
            patch("arcade.draw_line"),
            patch.object(panel, "draw_field"),
        ):
            panel.draw(aircraft[0].id, messages)
        self.assertEqual(
            panel.checkins.text, "DEPARTURE CHECK-INS\n" + "\n".join(messages)
        )
        panel.checkins.draw.assert_called_once()
        self.assertIsNone(panel.select_at(CHECKINS_TOP - 1))

    def test_terminal_fields_differ_for_arrivals_and_departures(self):
        _, _, strips = make_panel(1)
        strip = strips[0]
        strip.assigned_altitude = "6000"
        strip.fix_time = "BZA/1230"
        strip.remarks = "CLEARED DIRECT"
        kind, block7, block8, block9 = terminal_strip_fields(strip, "KNYL")
        self.assertEqual((kind, block7, block8), ("DEPARTURE", "55", "NYL"))
        self.assertEqual(block9, ("DCT IPL", "A 60", "FIX BZA/1230", "CLEARED DIRECT"))

        kind, block7, block8, block9 = terminal_strip_fields(strip, "KIPL")
        self.assertEqual((kind, block7, block8), ("ARRIVAL", "--", "--"))
        self.assertEqual(block9, ("A 60", "FIX BZA/1230", "CLEARED DIRECT", "TO IPL"))
        self.assertEqual(
            terminal_strip_fields(strip, "KPHX")[:3], ("OVERFLIGHT", "--", "ENR")
        )
        self.assertEqual(terminal_strip_fields(strip, None)[0], "UNKNOWN")

    def test_enroute_indicator_is_drawn_in_field_eight(self):
        panel, aircraft, strips = make_panel(1)
        panel.airport_code = "KPHX"
        with (
            patch("arcade.draw_rect_filled"),
            patch("arcade.draw_line"),
            patch.object(panel, "draw_field") as fields,
        ):
            panel.draw(aircraft[0].id)
        self.assertIn(
            ("ENR", STRIP_LEFT + STRIP_COLUMNS[2] + 4),
            [(call.args[0], call.args[1]) for call in fields.call_args_list],
        )
        self.assertEqual(strips[0].flight_plan.origin, "KNYL")

    def test_long_fields_fit_grid_and_full_details_remain_visible(self):
        panel, aircraft, strips = make_panel(1)

        class Text:
            text = ""
            position = (0, 0)

            @property
            def content_width(self):
                return len(self.text) * 7

            def draw(self):
                pass

        panel.text = Text()
        panel.draw_field("BZA MOHAK ARLIN4 KSDL", 0, 0, 118)
        self.assertLessEqual(panel.text.content_width, 118)
        self.assertTrue(panel.text.text.endswith("..."))
        strips[0].flight_plan.route = "BZA MOHAK ARLIN4 KSDL"
        strips[0].remarks = "CLEARED DIRECT TO DESTINATION"
        with patch("arcade.draw_rect_filled"), patch("arcade.draw_line"):
            panel.draw(aircraft[0].id)
        self.assertIn("ROUTE BZA MOHAK ARLIN4 SDL IPL", panel.footer.text)
        self.assertIn("CLEARED DIRECT TO DESTINATION", panel.footer.text)

    def test_strip_airport_labels_do_not_change_fixes_or_filed_plan(self):
        panel, aircraft, strips = make_panel(1)
        strip = strips[0]
        strip.flight_plan.route = "KUMBA KIPL IPL KXYZ"
        _, _, origin, block9 = terminal_strip_fields(strip, "KNYL")
        self.assertEqual(origin, "NYL")
        self.assertEqual(block9[0], "KUMBA IPL IPL KXYZ IPL")
        with (
            patch("arcade.draw_rect_filled"),
            patch("arcade.draw_line"),
            patch.object(panel, "draw_field"),
        ):
            panel.draw(aircraft[0].id)
        self.assertIn("PLAN NYL > IPL", panel.footer.text)
        self.assertIn("ROUTE KUMBA IPL IPL KXYZ IPL", panel.footer.text)
        self.assertEqual(strip.flight_plan.origin, "KNYL")
        self.assertEqual(strip.flight_plan.destination, "KIPL")
        self.assertEqual(strip.flight_plan.route, "KUMBA KIPL IPL KXYZ")

    def test_strip_does_not_duplicate_destination_already_in_route(self):
        panel, aircraft, strips = make_panel(1)
        strip = strips[0]
        strip.flight_plan.route = "BZA KIPL"
        self.assertEqual(terminal_strip_fields(strip, "KNYL")[3][0], "BZA IPL")
        with (
            patch("arcade.draw_rect_filled"),
            patch("arcade.draw_line"),
            patch.object(panel, "draw_field"),
        ):
            panel.draw(aircraft[0].id)
        self.assertIn("ROUTE BZA IPL\n", panel.footer.text)

    def test_hover_describes_terminal_fields_for_each_flight_type(self):
        panel, _, strips = make_panel(3)
        panel.airport_code = "KNYL"
        strips[1].flight_plan.origin = "KNJK"
        strips[1].flight_plan.destination = "KNYL"
        strips[2].flight_plan.origin = "KNJK"
        strips[2].flight_plan.destination = "KIPL"

        def hover(strip_index, column, from_top):
            return panel.tooltip_at(
                STRIP_LEFT + column,
                LIST_TOP - strip_index * STRIP_HEIGHT - 2 - from_top,
            )

        self.assertIn("Field 1", hover(0, 5, 5))
        self.assertIn("Field 2A", hover(0, 60, 25))
        self.assertIn("Field 3", hover(0, 5, 42))
        self.assertIn("beacon", hover(0, STRIP_COLUMNS[1] + 5, 5).lower())
        self.assertIn("departure time", hover(0, STRIP_COLUMNS[1] + 5, 30))
        self.assertIn("Previous fix", hover(1, STRIP_COLUMNS[1] + 5, 30))
        self.assertIn("coordination indicator", hover(2, STRIP_COLUMNS[1] + 5, 55))
        self.assertIn("Departure airport", hover(0, STRIP_COLUMNS[2] + 5, 5))
        self.assertIn("Estimated arrival", hover(1, STRIP_COLUMNS[2] + 5, 5))
        self.assertIn("ENR", hover(2, STRIP_COLUMNS[2] + 5, 5))
        self.assertIn("8B", hover(0, STRIP_COLUMNS[2] + 5, 55))
        self.assertIn("Filed route", hover(0, STRIP_COLUMNS[3] + 5, 5))
        self.assertIn("Assigned altitude", hover(1, STRIP_COLUMNS[3] + 5, 5))
        self.assertIn("runway or pad", hover(0, STRIP_COLUMNS[4] + 5, 5))
        self.assertIn("Field 18", hover(0, STRIP_COLUMNS[4] + 75, 65))

    def test_hover_tracks_scrolling_and_clears_outside_the_strip(self):
        panel, aircraft, strips = make_panel(VISIBLE_STRIPS + 1)
        panel.airport_code = "KNYL"
        strips[1].flight_plan.origin = "KNJK"
        strips[1].flight_plan.destination = "KNYL"
        x, y = STRIP_LEFT + STRIP_COLUMNS[1] + 5, LIST_TOP - 32
        display = SimpleNamespace(
            strip_panel=panel, selected_aircraft_id=aircraft[0].id
        )
        RadarDisplay.on_mouse_motion(display, x, y, 0, 0)
        self.assertIn("departure time", panel.tooltip_at(*panel.hover_position))
        panel.scroll(-1)
        self.assertIn("Previous fix", panel.tooltip_at(*panel.hover_position))
        self.assertEqual(display.selected_aircraft_id, aircraft[0].id)
        self.assertIsNone(panel.tooltip_at(STRIP_LEFT - 1, y))
        self.assertIsNone(panel.tooltip_at(x, LIST_TOP - 1))
        self.assertIsNone(panel.tooltip_at(x, LIST_TOP - STRIP_HEIGHT + 1))
        RadarDisplay.on_mouse_leave(display, 0, 0)
        self.assertIsNone(panel.hover_position)

    def test_startup_has_a_fictional_plan_for_each_sample_aircraft(self):
        aircraft_list, facility, strips = create_yuma_scenario()
        aircraft = aircraft_list.aircraft_list
        self.assertEqual(len(strips), len(aircraft))
        self.assertEqual({s.aircraft.id for s in strips}, {a.id for a in aircraft})
        self.assertTrue(
            all(s.flight_plan.origin and s.flight_plan.route for s in strips)
        )
        routes = [strip.flight_plan.route for strip in strips]
        self.assertTrue(all(route.strip() != "DCT" for route in routes))
        self.assertTrue(all("I-8" not in route for route in routes))
        self.assertEqual(len(set(routes)), len(routes))
        self.assertTrue(
            any(" V66 " in f" {strip.flight_plan.route} " for strip in strips)
        )
        self.assertTrue(
            any(
                "KUMBA" in strip.flight_plan.route
                for strip in strips
                if strip.aircraft.flight_rules == "VFR"
            )
        )
        kinds = Counter(
            (terminal_strip_fields(strip, "KNYL")[0], strip.aircraft.flight_rules)
            for strip in strips
        )
        self.assertEqual(len(strips), 10)
        self.assertEqual(kinds["OVERFLIGHT", "IFR"], 3)
        self.assertEqual(kinds["OVERFLIGHT", "VFR"], 1)
        self.assertEqual(
            sum(count for (kind, _), count in kinds.items() if kind == "ARRIVAL"), 3
        )
        self.assertEqual(
            sum(count for (kind, _), count in kinds.items() if kind == "DEPARTURE"), 3
        )
        areas = {s.aircraft.id: s.operation_area for s in strips}
        self.assertEqual([areas[i] for i in ("A1", "A3", "A10", "A16")], [""] * 4)
        self.assertEqual(areas["A7"], "35")
        self.assertEqual([areas[i] for i in ("A9", "A12")], ["P1", "P2"])
        self.assertEqual(
            [areas[i] for i in ("A8", "A11", "A15")],
            ["03L", "03R", "03L"],
        )
        self.assertEqual(facility.active_runways, ("03L", "03R", "35"))

    def test_sample_runways_skip_overflights_without_consuming_the_rotation(self):
        create_strips = runpy.run_path("main.py")["create_sample_strips"]
        _, aircraft, _ = make_panel(4)
        aircraft = aircraft[1:]
        plans = {
            "A1": ("KNJK", "KIPL", "DCT", 5000, 100),
            "A2": ("KNYL", "KIPL", "DCT", 5000, 100),
            "A3": ("KNJK", "KNYL", "DCT", 5000, 100),
        }
        facility = SimpleNamespace(
            airport_code="KNYL",
            active_runways=("03L", "03R", "35"),
            helicopter_pads=("P1", "P2", "P3", "P5"),
        )
        with patch.dict(create_strips.__globals__["SAMPLE_PLANS"], plans):
            strips = create_strips(SimpleNamespace(aircraft_list=aircraft), facility)
        self.assertEqual([s.operation_area for s in strips], ["", "03L", "03R"])

    def test_scenario_construction_creates_independent_guided_aircraft(self):
        aircraft_list, facility, strips = create_yuma_scenario()
        other_aircraft, other_facility, other_strips = create_yuma_scenario()
        self.assertIsNot(facility, other_facility)
        self.assertIsNot(
            aircraft_list.aircraft_list[0], other_aircraft.aircraft_list[0]
        )
        self.assertIsNot(strips[0].flight_plan, other_strips[0].flight_plan)
        self.assertEqual(facility.aircraft_list, aircraft_list.aircraft_list)
        for strip in strips:
            self.assertIs(strip.aircraft.flight_guidance.strip, strip)

    def test_sample_helicopters_rotate_among_permitted_scenario_pads(self):
        create_strips = runpy.run_path("main.py")["create_sample_strips"]
        aircraft = [
            SimpleNamespace(id=identifier, squawk="1200")
            for identifier in ("A9", "A12", "A17", "A18", "A20", "A21")
        ]
        facility = SimpleNamespace(
            airport_code="KNYL",
            active_runways=("03L", "03R", "35"),
            helicopter_pads=("P1", "P2", "P3", "P5"),
        )
        strips = create_strips(SimpleNamespace(aircraft_list=aircraft), facility)
        self.assertEqual(
            [strip.operation_area for strip in strips],
            ["P1", "P2", "P3", "P5", "P1", "P2"],
        )
        self.assertIn("TRAINING NOT SIMULATED", strips[4].remarks)
        self.assertIn("SEARCH NOT SIMULATED", strips[5].remarks)

    def test_runway_edit_only_accepts_active_runways_or_unspecified_pad(self):
        panel, aircraft, strips = make_panel(1)
        panel.active_runways = ("03L", "03R", "35")
        panel.helicopter_pads = ("P1", "P2", "P3", "P5")
        strips[0].operation_area = "35"
        panel.on_key_press(arcade.key.KEY_5, aircraft[0].id)
        for _ in range(2):
            panel.on_key_press(arcade.key.BACKSPACE, aircraft[0].id)
        for char in "21R":
            panel.on_key_press(
                ord(char.lower()) if char.isalpha() else ord(char), aircraft[0].id
            )
        panel.on_key_press(arcade.key.ENTER, aircraft[0].id)
        self.assertIn("03L", panel.error)
        self.assertEqual(strips[0].operation_area, "35")
        for _ in range(3):
            panel.on_key_press(arcade.key.BACKSPACE, aircraft[0].id)
        for char in "03R":
            panel.on_key_press(
                ord(char.lower()) if char.isalpha() else ord(char), aircraft[0].id
            )
        panel.on_key_press(arcade.key.ENTER, aircraft[0].id)
        self.assertEqual(strips[0].operation_area, "03R")
        self.assertEqual(strips[0].flight_plan.route, "DCT")
        with (
            patch("arcade.draw_rect_filled"),
            patch("arcade.draw_line"),
            patch.object(panel, "draw_field") as draw_field,
        ):
            panel.draw(aircraft[0].id)
        self.assertIn("03R", [call.args[0] for call in draw_field.call_args_list])
        panel.on_key_press(arcade.key.KEY_5, aircraft[0].id)
        for _ in range(3):
            panel.on_key_press(arcade.key.BACKSPACE, aircraft[0].id)
        for char in "pad":
            panel.on_key_press(ord(char), aircraft[0].id)
        panel.on_key_press(arcade.key.ENTER, aircraft[0].id)
        self.assertEqual(strips[0].operation_area, "PAD")
        panel.on_key_press(arcade.key.KEY_5, aircraft[0].id)
        for _ in range(3):
            panel.on_key_press(arcade.key.BACKSPACE, aircraft[0].id)
        for char in "p4":
            panel.on_key_press(ord(char), aircraft[0].id)
        panel.on_key_press(arcade.key.ENTER, aircraft[0].id)
        self.assertIn("P5", panel.error)
        self.assertEqual(strips[0].operation_area, "PAD")
        panel.on_key_press(arcade.key.BACKSPACE, aircraft[0].id)
        panel.on_key_press(arcade.key.KEY_5, aircraft[0].id)
        panel.on_key_press(arcade.key.ENTER, aircraft[0].id)
        self.assertEqual(strips[0].operation_area, "P5")

    def test_scroll_selection_and_active_removal(self):
        panel, aircraft, strips = make_panel(VISIBLE_STRIPS + 3)
        self.assertEqual(len(panel.visible_strips()), VISIBLE_STRIPS)
        panel.scroll(-100)
        self.assertEqual(panel.offset, 3)
        self.assertEqual(panel.select_at(LIST_TOP - 1), aircraft[3].id)
        self.assertEqual(panel.select_at(LIST_TOP - STRIP_HEIGHT - 1), aircraft[4].id)
        strips[3].active = False
        panel.aircraft_list.aircraft_list.remove(aircraft[4])
        self.assertNotIn(strips[3], panel.active_strips())
        self.assertNotIn(strips[4], panel.active_strips())
        self.assertEqual(len(panel.visible_strips()), VISIBLE_STRIPS)
        self.assertEqual(panel.offset, 1)
        panel.scroll(100)
        self.assertEqual(panel.offset, 0)

    def test_edit_annotations_without_changing_plan_or_commanding_aircraft(self):
        panel, aircraft, strips = make_panel(1)
        strip = strips[0]
        for selector, text in (
            (arcade.key.KEY_1, "6000"),
            (arcade.key.KEY_2, "BZA/1230"),
            (arcade.key.KEY_3, "CLEARED DIRECT"),
        ):
            self.assertTrue(panel.on_key_press(selector, aircraft[0].id))
            for char in text:
                panel.on_key_press(
                    ord(char.lower()) if char.isalpha() else ord(char), aircraft[0].id
                )
            panel.on_key_press(arcade.key.ENTER, aircraft[0].id)
        self.assertEqual(strip.assigned_altitude, "6000")
        self.assertEqual(strip.fix_time, "BZA/1230")
        self.assertEqual(strip.remarks, "CLEARED DIRECT")
        self.assertEqual(strip.flight_plan.altitude, 5500)
        self.assertIsNone(aircraft[0].target_altitude)

    def test_invalid_altitude_cancel_and_removed_strip(self):
        panel, aircraft, strips = make_panel(1)
        panel.on_key_press(arcade.key.KEY_1, aircraft[0].id)
        panel.on_key_press(arcade.key.A, aircraft[0].id)
        panel.on_key_press(arcade.key.ENTER, aircraft[0].id)
        self.assertEqual(panel.error, "ALTITUDE MUST BE FEET IN DIGITS")
        self.assertEqual(strips[0].assigned_altitude, "")
        panel.on_key_press(arcade.key.ESCAPE, aircraft[0].id)
        self.assertIsNone(panel.edit_strip)
        panel.on_key_press(arcade.key.KEY_2, aircraft[0].id)
        strips[0].active = False
        panel.on_key_press(arcade.key.ENTER, aircraft[0].id)
        self.assertEqual(panel.error, "STRIP NO LONGER ACTIVE")
        self.assertEqual(strips[0].fix_time, "")

    def test_strip_beacon_edit_validation_and_radar_independence(self):
        panel, aircraft, strips = make_panel(1)
        strip = strips[0]
        self.assertEqual(strip.beacon_code, "1200")
        panel.on_key_press(arcade.key.KEY_4, aircraft[0].id)
        for _ in range(4):
            panel.on_key_press(arcade.key.BACKSPACE, aircraft[0].id)
        for char in "1280":
            panel.on_key_press(ord(char), aircraft[0].id)
        panel.on_key_press(arcade.key.ENTER, aircraft[0].id)
        self.assertIn("OCTAL", panel.error)
        self.assertEqual(strip.beacon_code, "1200")
        for _ in range(4):
            panel.on_key_press(arcade.key.BACKSPACE, aircraft[0].id)
        for char in "123":
            panel.on_key_press(ord(char), aircraft[0].id)
        panel.on_key_press(arcade.key.ENTER, aircraft[0].id)
        self.assertIn("OCTAL", panel.error)
        for _ in range(3):
            panel.on_key_press(arcade.key.BACKSPACE, aircraft[0].id)
        for char in "0777":
            panel.on_key_press(ord(char), aircraft[0].id)
        panel.on_key_press(arcade.key.ENTER, aircraft[0].id)
        self.assertEqual(strip.beacon_code, "0777")
        self.assertEqual(aircraft[0].squawk, "1200")
        with (
            patch("arcade.draw_rect_filled"),
            patch("arcade.draw_line"),
            patch.object(panel, "draw_field") as draw_field,
        ):
            panel.draw(aircraft[0].id)
        self.assertIn("0777", [call.args[0] for call in draw_field.call_args_list])
        self.assertNotIn("1200", [call.args[0] for call in draw_field.call_args_list])

        panel.on_key_press(arcade.key.KEY_4, aircraft[0].id)
        for _ in range(4):
            panel.on_key_press(arcade.key.BACKSPACE, aircraft[0].id)
        panel.on_key_press(arcade.key.ENTER, aircraft[0].id)
        self.assertEqual(strip.beacon_code, "")
        self.assertEqual(aircraft[0].squawk, "1200")

    def test_drag_reorders_both_directions_and_preserves_selection(self):
        panel, aircraft, _ = make_panel(4)
        display = SimpleNamespace(
            strip_panel=panel,
            scratchpad_edit_id=None,
            handoff_choice_id=None,
            handoff_message="",
            selected_aircraft_id=None,
        )
        display.on_mouse_motion = lambda x, y, dx, dy: RadarDisplay.on_mouse_motion(
            display, x, y, dx, dy
        )
        x = STRIP_LEFT + 10
        start = LIST_TOP - 10
        target = LIST_TOP - 2 * STRIP_HEIGHT - 60
        RadarDisplay.on_mouse_press(display, x, start, arcade.MOUSE_BUTTON_LEFT, 0)
        RadarDisplay.on_mouse_drag(
            display, x, target, 0, target - start, arcade.MOUSE_BUTTON_LEFT, 0
        )
        RadarDisplay.on_mouse_release(display, x, target, arcade.MOUSE_BUTTON_LEFT, 0)
        self.assertEqual(
            [s.aircraft.id for s in panel.strips], ["A1", "A2", "A0", "A3"]
        )
        self.assertEqual(display.selected_aircraft_id, aircraft[0].id)

        start = LIST_TOP - 3 * STRIP_HEIGHT - 10
        target = LIST_TOP - 10
        RadarDisplay.on_mouse_press(display, x, start, arcade.MOUSE_BUTTON_LEFT, 0)
        RadarDisplay.on_mouse_drag(
            display, x, target, 0, target - start, arcade.MOUSE_BUTTON_LEFT, 0
        )
        RadarDisplay.on_mouse_release(display, x, target, arcade.MOUSE_BUTTON_LEFT, 0)
        self.assertEqual(
            [s.aircraft.id for s in panel.strips], ["A3", "A1", "A2", "A0"]
        )

    def test_horizontal_drag_offsets_and_restores_a_strip(self):
        panel, aircraft, strips = make_panel(2)
        display = SimpleNamespace(
            strip_panel=panel,
            scratchpad_edit_id=None,
            handoff_choice_id=None,
            handoff_message="",
            selected_aircraft_id=None,
        )
        display.on_mouse_motion = lambda x, y, dx, dy: RadarDisplay.on_mouse_motion(
            display, x, y, dx, dy
        )
        x, y = STRIP_LEFT + 10, LIST_TOP - 10
        RadarDisplay.on_mouse_press(display, x, y, arcade.MOUSE_BUTTON_LEFT, 0)
        RadarDisplay.on_mouse_drag(
            display, x + STRIP_SHIFT, y, STRIP_SHIFT, 0, arcade.MOUSE_BUTTON_LEFT, 0
        )
        with (
            patch("arcade.draw_rect_filled"),
            patch("arcade.draw_line"),
            patch.object(panel, "draw_field") as fields,
        ):
            panel.draw(aircraft[0].id)
        self.assertIn(
            (aircraft[0].callsign, STRIP_LEFT + STRIP_SHIFT + 4),
            [(call.args[0], call.args[1]) for call in fields.call_args_list],
        )
        RadarDisplay.on_mouse_release(
            display, x + STRIP_SHIFT, y, arcade.MOUSE_BUTTON_LEFT, 0
        )
        self.assertTrue(strips[0].offset_right)
        self.assertFalse(strips[1].offset_right)
        self.assertEqual([strip.aircraft.id for strip in panel.strips], ["A0", "A1"])
        self.assertEqual(display.selected_aircraft_id, aircraft[0].id)
        self.assertIsNone(panel.select_at(y, x))
        self.assertIsNone(panel.tooltip_at(x, y))
        self.assertEqual(panel.select_at(y, x + STRIP_SHIFT), aircraft[0].id)
        self.assertIn("Field 1", panel.tooltip_at(x + STRIP_SHIFT, y))
        far_right = STRIP_LEFT + STRIP_SHIFT + STRIP_COLUMNS[-1] - 1
        self.assertEqual(panel.select_at(y, far_right), aircraft[0].id)
        self.assertIn("Field", panel.tooltip_at(far_right, y))

        RadarDisplay.on_mouse_press(
            display, x + STRIP_SHIFT, y, arcade.MOUSE_BUTTON_LEFT, 0
        )
        RadarDisplay.on_mouse_drag(
            display, x, y, -STRIP_SHIFT, 0, arcade.MOUSE_BUTTON_LEFT, 0
        )
        RadarDisplay.on_mouse_release(display, x, y, arcade.MOUSE_BUTTON_LEFT, 0)
        self.assertFalse(strips[0].offset_right)

    def test_offset_drag_cancellation_and_reordering_shifted_strips(self):
        panel, _, strips = make_panel(3)
        x, y = STRIP_LEFT + 10, LIST_TOP - 10
        panel.start_drag(x, y)
        panel.move_drag(x + STRIP_SHIFT / 4, y)
        panel.finish_drag(x + STRIP_SHIFT / 4, y)
        self.assertFalse(strips[0].offset_right)
        panel.start_drag(x, y)
        panel.move_drag(x + STRIP_SHIFT, y)
        panel.cancel_drag()
        panel.finish_drag(x + STRIP_SHIFT, y)
        self.assertFalse(strips[0].offset_right)
        panel.start_drag(x, y)
        panel.move_drag(x + STRIP_SHIFT, y)
        panel.finish_drag(SCREEN_WIDTH - 1, y)
        self.assertFalse(strips[0].offset_right)
        panel.start_drag(x, y)
        panel.move_drag(x + STRIP_SHIFT, y)
        panel.finish_drag(x + STRIP_SHIFT, y)
        shifted = strips[0]
        self.assertTrue(shifted.offset_right)
        target_y = LIST_TOP - 2 * STRIP_HEIGHT - 60
        panel.start_drag(x + STRIP_SHIFT, y)
        panel.move_drag(x + STRIP_SHIFT, target_y)
        panel.finish_drag(x + STRIP_SHIFT, target_y)
        self.assertIs(panel.strips[-1], shifted)
        self.assertTrue(shifted.offset_right)

    def test_drag_scroll_cancellation_and_inactive_strips(self):
        panel, _, strips = make_panel(VISIBLE_STRIPS + 3)
        source, inactive = strips[0], strips[2]
        inactive.active = False
        x = STRIP_LEFT + 10
        start = LIST_TOP - 10
        panel.start_drag(x, start)
        panel.move_drag(x, start - 10)
        panel.scroll(-100)
        target = LIST_TOP - (VISIBLE_STRIPS - 1) * STRIP_HEIGHT - 60
        panel.move_drag(x, target)
        panel.finish_drag(x, target)
        self.assertEqual(panel.active_strips()[-1], source)
        self.assertIn(inactive, panel.strips)
        before = list(panel.strips)
        panel.start_drag(x, LIST_TOP - 10)
        panel.move_drag(x, LIST_TOP - 100)
        panel.finish_drag(SCREEN_WIDTH - 10, LIST_TOP - 100)
        self.assertEqual(panel.strips, before)
        panel.start_drag(x, LIST_TOP - 10)
        panel.move_drag(x, LIST_TOP - 100)
        RadarDisplay.on_key_press(
            SimpleNamespace(strip_panel=panel), arcade.key.ESCAPE, 0
        )
        panel.finish_drag(x, LIST_TOP - 100)
        self.assertEqual(panel.strips, before)
        panel.start_drag(x, LIST_TOP - 10)
        removed = panel.drag_strip
        panel.move_drag(x, LIST_TOP - 100)
        removed.active = False
        panel.finish_drag(x, LIST_TOP - 100)
        self.assertEqual(panel.error, "STRIP NO LONGER ACTIVE")
        self.assertEqual(panel.strips, before)

    def test_panel_mouse_actions_do_not_zoom_radar(self):
        panel, aircraft, _ = make_panel(VISIBLE_STRIPS + 1)
        display = SimpleNamespace(
            strip_panel=panel,
            radar_viewport=RadarViewport(),
            scratchpad_edit_id=None,
            handoff_choice_id=None,
            handoff_message="",
            selected_aircraft_id=None,
        )
        RadarDisplay.on_mouse_press(
            display, SCREEN_WIDTH + 10, LIST_TOP - 1, arcade.MOUSE_BUTTON_LEFT, 0
        )
        self.assertEqual(display.selected_aircraft_id, aircraft[0].id)
        RadarDisplay.on_mouse_scroll(display, SCREEN_WIDTH + 10, 300, 0, -1)
        self.assertEqual(panel.offset, 1)
        self.assertEqual(display.radar_viewport.zoom, 1)
        RadarDisplay.on_mouse_scroll(display, SCREEN_WIDTH - 10, 300, 0, 1)
        self.assertGreater(display.radar_viewport.zoom, 1)

    def test_stars_visibility_excludes_panel(self):
        display = SimpleNamespace(
            display_type=RadarDisplay.STARS, STARS=RadarDisplay.STARS
        )
        self.assertTrue(
            RadarDisplay.is_visible_scope_position(display, SCREEN_WIDTH, 450)
        )
        self.assertFalse(
            RadarDisplay.is_visible_scope_position(display, SCREEN_WIDTH + 1, 450)
        )

    def test_data_block_placement_does_not_use_panel_space(self):
        snapshot = SimpleNamespace(
            aircraft_id="A1", latitude=0, longitude=0, heading=90
        )
        display = SimpleNamespace(
            width=1640,
            height=900,
            ui_scale=1.0,
            display_type=RadarDisplay.STARS,
            secondary_radar_returns=[snapshot],
            data_block_labels={},
            data_block_directions={"A1": (1, 0)},
            data_block_overlap_warned=False,
            selected_aircraft_id="A1",
            calculate_range_and_bearing=lambda lat, lon: (10, 0),
            convert_to_display_coordinates=lambda lat, lon: (1190, 450),
            is_visible_scope_position=lambda x, y: True,
            secondary_return_layout=lambda snapshot, x, y, distance, direction: (
                "",
                x + 40,
                y,
            ),
        )
        with patch.object(
            RadarDisplay,
            "get_data_block_label",
            return_value=SimpleNamespace(width=80, height=60),
        ):
            layout = RadarDisplay.layout_secondary_returns(display)[0]
        self.assertLessEqual(layout.text_x + layout.width / 2, SCREEN_WIDTH)


if __name__ == "__main__":
    unittest.main()
