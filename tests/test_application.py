import queue
import runpy
import subprocess
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import arcade

from locations.Yuma.Scenarios.generator import (
    OPERATIONS,
    GeneratorSettings,
    generate_yuma_scenario,
)
from locations.Yuma.Scenarios.yuma import create_yuma_scenario
from simulator.app.application import (
    FAA_7110_65,
    ITEM_HEIGHT,
    LOCATIONS,
    MENU_BOTTOM,
    MENU_ITEM_WIDTH,
    MENU_THEMES,
    MENU_WIDTH,
    THEME_CHECK_INTERVAL,
    YUMA_ACTIVE_RADIOS,
    ApplicationWindow,
    LocationChoice,
    ScenarioChoice,
    SectorChoice,
)
from simulator.app.menu_theme import system_theme
from simulator.core.atc import ATCFacility, TrackingPosition
from simulator.core.constants import SCREEN_HEIGHT, SCREEN_WIDTH
from simulator.display.flight_strips import PANEL_WIDTH
from simulator.display.radar import DEFAULT_RANGE_RING_BRIGHTNESS, RadarDisplay
from simulator.radio.communications import CommunicationsPanel, RadioState


def make_application():
    app = ApplicationWindow.__new__(ApplicationWindow)
    app.scenario_loaded = False
    app.map_preview = False
    app.paused = False
    app.selected_location = LOCATIONS[0]
    app.selected_sector = None
    app.pending_scenario = None
    app.pending_location = None
    app.pending_generated_settings = None
    app.generator_dialog = None
    app.generator_settings = None
    app.scenario_utc = None
    app.saves_dialog = None
    app.pending_saved_scenario = None
    app.open_menu = None
    app.submenu_location = None
    app.submenu_option = None
    app.menu_hover = None
    app.pubs_root = None
    app.pubs_directory = None
    app.pubs_items = ()
    app.pubs_page = 0
    app.pubs_results = queue.Queue()
    app.confirm_replace = False
    app.menu_message = ""
    app.menu_theme = "Dark"
    app.theme_error = None
    app.theme_check_elapsed = 0
    app.theme_check_pending = False
    app.theme_results = queue.Queue()
    app.gis_overlays = SimpleNamespace(visible={0}, status=["ready"])
    app.voice_audio = None
    app.voice_message = ""
    app.display_type = RadarDisplay.ARTS_IIE
    app.range_ring_brightness = DEFAULT_RANGE_RING_BRIGHTNESS
    app.ui_camera = Mock()
    app.ui_offset_x = app.ui_offset_y = 0
    app.ui_scale = app.ui_scale_x = app.ui_scale_y = 1.0
    app.map_camera = Mock()
    app._scaled_ui_camera = app.ui_camera
    with patch("simulator.radio.communications.arcade.Text"):
        app.communications_panel = CommunicationsPanel()
    app.atc_facility = ATCFacility.get_atc_facility_by_name("KNYL")
    app.set_caption = Mock()
    return app


def add_test_scenario(app, create=create_yuma_scenario):
    scenario = ScenarioChoice("Test scenario", create, YUMA_ACTIVE_RADIOS)
    app.available_scenarios = lambda: (scenario,)
    return scenario


class ApplicationTests(unittest.TestCase):
    def test_scenario_menu_actions_do_not_require_mouse_coordinates(self):
        app = make_application()
        scenario = add_test_scenario(app)
        with (
            patch.object(app, "request_scenario") as request,
            patch.object(app, "open_generator") as generator,
            patch.object(app, "open_saves") as saves,
            patch.object(app, "retry_maps") as retry,
        ):
            for index in range(5):
                app.select_scenario_menu_entry(index)
        request.assert_called_once_with(scenario)
        generator.assert_called_once_with()
        self.assertEqual(
            [call.args for call in saves.call_args_list], [("load",), ("save",)]
        )
        retry.assert_called_once_with()
        with self.assertRaises(IndexError):
            app.select_scenario_menu_entry(-1)

    def test_option_menu_actions_do_not_require_mouse_coordinates(self):
        app = make_application()
        with patch.object(app, "enable_voice") as enable:
            app.select_option_menu_entry("audio", 0)
        enable.assert_called_once_with()
        app.select_option_menu_entry("range_rings", 4)
        self.assertEqual(app.range_ring_brightness, 40)
        app.select_option_menu_entry("display", 1)
        self.assertIn("FDAD", app.menu_message)
        app.scenario_loaded = True
        with patch.object(app, "select_yuma_runways") as runways:
            app.select_option_menu_entry("runways", 1)
        runways.assert_called_once_with(1)
        with self.assertRaises(IndexError):
            app.select_option_menu_entry("range_rings", 11)
        with self.assertRaises(ValueError):
            app.select_option_menu_entry("invalid", 0)

    def test_resize_scales_and_translates_menu_input(self):
        app = make_application()
        app.on_resize(2000, 1100)
        self.assertGreater(app.ui_scale, 1)
        self.assertGreater(app.ui_offset_x, 0)
        x = app.ui_offset_x + 10 * app.ui_scale_x
        y = app.ui_offset_y + (MENU_BOTTOM + 5) * app.ui_scale_y
        app.on_mouse_press(x, y, arcade.MOUSE_BUTTON_LEFT, 0)
        self.assertEqual(app.open_menu, "location")
        app.on_mouse_press(1, y, arcade.MOUSE_BUTTON_LEFT, 0)
        self.assertEqual(app.open_menu, "location")
        with patch.object(app, "select_location") as select:
            app.on_mouse_press(
                x,
                app.ui_offset_y + (MENU_BOTTOM - 5) * app.ui_scale_y,
                arcade.MOUSE_BUTTON_LEFT,
                0,
            )
        select.assert_called_once_with(LOCATIONS[0])

    def test_resize_maps_drag_and_release_coordinates_once(self):
        app = make_application()
        app.on_resize(2000, 1100)
        app.map_preview = True
        x = app.ui_offset_x + 300 * app.ui_scale_x
        y = app.ui_offset_y + 400 * app.ui_scale_y
        with (
            patch.object(RadarDisplay, "on_mouse_drag") as drag,
            patch.object(RadarDisplay, "on_mouse_release") as release,
        ):
            app.on_mouse_drag(
                x,
                y,
                10 * app.ui_scale_x,
                -5 * app.ui_scale_y,
                arcade.MOUSE_BUTTON_LEFT,
                0,
            )
            app.on_mouse_release(x, y, arcade.MOUSE_BUTTON_LEFT, 0)
        args = drag.call_args.args
        self.assertAlmostEqual(args[0], 300)
        self.assertAlmostEqual(args[1], 400)
        self.assertAlmostEqual(args[2], 10)
        self.assertAlmostEqual(args[3], -5)
        self.assertEqual(args[4:], (arcade.MOUSE_BUTTON_LEFT, 0))
        release.assert_called_once_with(300, 400, arcade.MOUSE_BUTTON_LEFT, 0)

    def test_theme_results_update_menu_and_report_errors(self):
        app = make_application()
        app.theme_check_pending = True
        app.theme_results.put(("Light", None))
        app.update_menu_theme(0)
        self.assertEqual(app.menu_theme, "Light")
        self.assertFalse(app.theme_check_pending)

        app.theme_check_pending = True
        app.theme_results.put((None, "theme unavailable"))
        with self.assertLogs("simulator.app.application", level="WARNING") as logs:
            app.update_menu_theme(0)
        self.assertIn("theme unavailable", logs.output[0])
        self.assertEqual(app.menu_theme, "Light")
        app.theme_results.put(("Dark", None))
        app.update_menu_theme(0)
        self.assertIsNone(app.theme_error)
        self.assertEqual(app.menu_theme, "Dark")

    def test_theme_detection_runs_in_background_and_reports_failure(self):
        app = make_application()
        with patch("simulator.app.application.threading.Thread") as thread:
            app.update_menu_theme(THEME_CHECK_INTERVAL)
            thread.return_value.start.assert_called_once()
            app.update_menu_theme(THEME_CHECK_INTERVAL)
            thread.assert_called_once()
        with patch(
            "simulator.app.application.system_theme", side_effect=OSError("unavailable")
        ):
            app._detect_menu_theme(app.theme_results)
        self.assertEqual(app.theme_results.get_nowait(), (None, "unavailable"))

    def test_menu_hover_and_light_theme_are_drawn(self):
        app = make_application()
        app.menu_theme = "Light"
        app._ctx = Mock()
        app.startup_text = Mock()
        app.menu_text = Mock()
        app.clear = Mock()
        app.open_menu = "scenario"
        app.on_mouse_motion(MENU_WIDTH + 10, MENU_BOTTOM - ITEM_HEIGHT, 0, 0)
        self.assertEqual(app.menu_hover, ("item", 0))
        with (
            patch("simulator.app.application.arcade.draw_rect_filled") as draw,
            patch("simulator.app.application.arcade.draw_rect_outline"),
        ):
            app.on_draw()
        colors = [call.args[1] for call in draw.call_args_list]
        self.assertIn(MENU_THEMES["Light"]["bar"], colors)
        self.assertIn(MENU_THEMES["Light"]["highlight"], colors)
        self.assertEqual(app.menu_text.color, MENU_THEMES["Light"]["text"])

    def test_menu_centers_location_and_voice_status_is_on_radar(self):
        app = make_application()
        app._ctx = Mock()
        app.startup_text = Mock()
        app.menu_text = Mock()
        app.clear = Mock()
        drawn = []
        app.menu_text.draw.side_effect = lambda: drawn.append(
            (
                app.menu_text.text,
                app.menu_text.x,
                app.menu_text.y,
                app.menu_text.anchor_x,
                app.menu_text.color,
            )
        )
        with patch("simulator.app.application.arcade.draw_rect_filled"):
            for (
                theme,
                location,
                sector,
                voice_status,
                expected_location,
                expected_voice,
            ) in (
                ("Dark", None, None, None, "No location selected", "VOICE OFF"),
                ("Light", LOCATIONS[0], None, "VOICE READY", "Yuma (KNYL)", "VOICE ON"),
                (
                    "Dark",
                    LOCATIONS[0],
                    None,
                    "VOICE LOADING",
                    "Yuma (KNYL)",
                    "VOICE LOADING",
                ),
                (
                    "Dark",
                    LOCATIONS[1],
                    LOCATIONS[1].sectors[0],
                    "VOICE ERROR",
                    "Cascade Approach / Medford",
                    "VOICE ERROR",
                ),
            ):
                with self.subTest(location=expected_location, voice=expected_voice):
                    app.menu_theme = theme
                    app.selected_location = location
                    app.selected_sector = sector
                    app.communications_panel.voice_status = voice_status
                    app.menu_message = "MAP ERROR: example"
                    drawn.clear()
                    app.on_draw()
                    self.assertIn(
                        (
                            expected_location,
                            (SCREEN_WIDTH + PANEL_WIDTH) / 2,
                            MENU_BOTTOM + 7,
                            "center",
                            MENU_THEMES[theme]["text"],
                        ),
                        drawn,
                    )
                    self.assertIn(
                        (
                            expected_voice,
                            SCREEN_WIDTH - 10,
                            10,
                            "right",
                            arcade.color.WHITE,
                        ),
                        drawn,
                    )
                    self.assertIn(
                        (
                            "MAP ERROR: example",
                            10,
                            SCREEN_HEIGHT - 20,
                            "left",
                            MENU_THEMES[theme]["text"],
                        ),
                        drawn,
                    )

    def test_system_theme_detects_linux_preference_and_legacy_gtk_theme(self):
        dark = subprocess.CompletedProcess([], 0, "'prefer-dark'\n", "")
        default = subprocess.CompletedProcess([], 0, "'default'\n", "")
        gtk = subprocess.CompletedProcess([], 0, "'Adwaita-dark'\n", "")
        with (
            patch("simulator.app.menu_theme.sys.platform", "linux"),
            patch(
                "simulator.app.menu_theme.subprocess.run",
                side_effect=[dark, default, gtk],
            ),
        ):
            self.assertEqual(system_theme(), "Dark")
            self.assertEqual(system_theme(), "Dark")

    def test_system_theme_reports_missing_or_invalid_appearance(self):
        with (
            patch("simulator.app.menu_theme.sys.platform", "win32"),
            patch("simulator.app.menu_theme.darkdetect.theme", return_value=None),
            self.assertRaises(ValueError),
        ):
            system_theme()

    def test_main_opens_menu_without_constructing_a_scenario(self):
        with (
            patch("sys.argv", ["main.py"]),
            patch("simulator.app.application.ApplicationWindow") as window,
            patch("simulator.app.application.generate_yuma_scenario") as scenario,
            patch("arcade.run") as run,
        ):
            runpy.run_path("main.py", run_name="__main__")
        window.return_value.setup.assert_called_once()
        window.return_value.enable_voice.assert_not_called()
        scenario.assert_not_called()
        run.assert_called_once()

    def test_startup_has_no_location_or_map(self):
        with (
            patch.object(RadarDisplay, "__init__", return_value=None) as radar_init,
            patch.object(ApplicationWindow, "set_size"),
            patch.object(ApplicationWindow, "on_resize"),
            patch.object(ApplicationWindow, "width", 1640),
            patch.object(ApplicationWindow, "height", 1048),
            patch("simulator.app.application.arcade.Camera2D"),
            patch("simulator.app.application.arcade.Text"),
            patch.object(ATCFacility, "get_atc_facility_by_name") as get_facility,
        ):
            app = ApplicationWindow()
        self.assertIsNone(app.selected_location)
        self.assertIsNone(radar_init.call_args.args[1])
        get_facility.assert_not_called()
        app.gis_overlays = None
        app.voice_audio = None
        app.ui_offset_x = app.ui_offset_y = 0
        app.ui_scale_x = app.ui_scale_y = 1.0
        self.assertEqual(app.available_scenarios(), ())
        self.assertEqual(app.menu_entries("scenario"), ("Select a location first",))
        self.assertTrue(
            all(not entry.startswith("*") for entry in app.menu_entries("location"))
        )
        self.assertEqual(app.loading_message(), "")
        app.on_mouse_press(
            MENU_WIDTH + 10, MENU_BOTTOM + 5, arcade.MOUSE_BUTTON_LEFT, 0
        )
        app.on_mouse_press(
            MENU_WIDTH + 10, MENU_BOTTOM - 5, arcade.MOUSE_BUTTON_LEFT, 0
        )
        self.assertIsNone(app.selected_location)
        self.assertFalse(app.scenario_loaded)
        app.retry_maps()

    def test_select_yuma_and_filter_scenarios(self):
        app = make_application()
        app.selected_location = None
        app.atc_facility = None
        app.gis_overlays = None
        new_overlays = Mock(visible={0}, status=["ready"])
        with (
            patch(
                "simulator.app.application.GISOverlays", return_value=new_overlays
            ) as gis,
            patch("simulator.app.application.FlightStripPanel"),
            patch("simulator.radio.communications.arcade.Text"),
        ):
            app.on_mouse_press(10, MENU_BOTTOM + 5, arcade.MOUSE_BUTTON_LEFT, 0)
            app.on_mouse_press(10, MENU_BOTTOM - 5, arcade.MOUSE_BUTTON_LEFT, 0)
        self.assertIs(app.selected_location, LOCATIONS[0])
        self.assertEqual(app.atc_facility.airport_code, "KNYL")
        self.assertEqual(
            app.menu_entries("scenario"),
            (
                "Generate Yuma...",
                "Load saved scenario...",
                "Save scenario...",
                "Retry failed maps",
            ),
        )
        gis.assert_called_once_with(32.6566, -114.6056, 10 + 14 / 60)
        new_overlays.toggle.assert_not_called()

    def test_select_medford_as_first_location(self):
        app = make_application()
        app.selected_location = None
        app.atc_facility = None
        app.gis_overlays = None
        with (
            patch(
                "simulator.app.application.GISOverlays",
                return_value=Mock(visible={0}, status=["ready"]),
            ) as gis,
            patch("simulator.app.application.FlightStripPanel"),
            patch("simulator.radio.communications.arcade.Text"),
        ):
            app.select_location(LOCATIONS[1])
        gis.assert_called_once_with(42.3749647, -122.8732875, 13 + 15 / 60)
        self.assertIs(app.selected_location, LOCATIONS[1])
        self.assertEqual(app.atc_facility.airport_code, "KMFR")
        self.assertEqual(app.selected_sector.label, "Medford")
        self.assertTrue(app.map_preview)

    def test_sector_submenu_selects_sector_and_filters_scenarios(self):
        app = make_application()
        north = ScenarioChoice("North scenario", Mock())
        south = ScenarioChoice("South scenario", Mock(side_effect=create_yuma_scenario))
        facility = LocationChoice(
            "Test facility",
            "KNYL",
            sectors=(
                SectorChoice("North", (north,)),
                SectorChoice("South", (south,)),
            ),
        )

        def activate(location, sector):
            app.selected_location = location
            app.selected_sector = sector

        with (
            patch("simulator.app.application.LOCATIONS", (LOCATIONS[0], facility)),
            patch.object(app, "activate_location", side_effect=activate),
        ):
            app.on_mouse_press(10, MENU_BOTTOM + 5, arcade.MOUSE_BUTTON_LEFT, 0)
            app.on_mouse_motion(10, MENU_BOTTOM - ITEM_HEIGHT - 5, 0, 0)
            self.assertEqual(app.submenu_location, 1)
            self.assertIs(app.selected_location, LOCATIONS[0])
            app.on_mouse_motion(
                MENU_ITEM_WIDTH + 10, MENU_BOTTOM - 2 * ITEM_HEIGHT - 5, 0, 0
            )
            self.assertEqual(app.menu_hover, ("sector", 1))
            app.on_mouse_press(
                MENU_ITEM_WIDTH + 10,
                MENU_BOTTOM - 2 * ITEM_HEIGHT - 5,
                arcade.MOUSE_BUTTON_LEFT,
                0,
            )
            self.assertIs(app.selected_location, facility)
            self.assertEqual(app.selected_sector.label, "South")
            self.assertEqual(app.available_scenarios(), (south,))
            self.assertEqual(
                app.menu_entries("scenario"), ("South scenario", "Retry failed maps")
            )
            with self.assertRaises(ValueError):
                app.request_scenario(north)
            with patch("simulator.app.application.FlightStripPanel"):
                app.request_scenario(south)
            south.create.assert_called_once()
            north.create.assert_not_called()
            self.assertTrue(app.scenario_loaded)

    def test_location_with_no_scenarios_is_clear_and_retry_remains_available(self):
        app = make_application()
        with patch.object(app, "activate_location") as activate:
            location = LocationChoice("Empty facility", "KMFR")
            app.select_location(location)
        activate.assert_called_once_with(location, None)
        app.selected_location = location
        self.assertEqual(
            app.menu_entries("scenario"),
            ("No scenarios available", "Retry failed maps"),
        )
        app.on_mouse_press(
            MENU_WIDTH + 10, MENU_BOTTOM + 5, arcade.MOUSE_BUTTON_LEFT, 0
        )
        app.on_mouse_press(
            MENU_WIDTH + 10, MENU_BOTTOM - 5, arcade.MOUSE_BUTTON_LEFT, 0
        )
        self.assertFalse(app.scenario_loaded)

    def test_select_medford_replaces_map_radios_and_empty_traffic(self):
        app = make_application()
        old_overlays = Mock(visible={0}, status=["ready"])
        app.gis_overlays = old_overlays
        app.voice_audio = Mock(ready=True)
        app.communications_panel.voice_status = "VOICE LOADING"
        app.communications_panel.keyboard_ptt = True
        new_overlays = Mock(visible={0}, status=["ready"])
        with (
            patch(
                "simulator.app.application.GISOverlays", return_value=new_overlays
            ) as gis,
            patch("simulator.app.application.FlightStripPanel"),
            patch("simulator.radio.communications.arcade.Text"),
        ):
            app.select_location(LOCATIONS[1])
        gis.assert_called_once_with(42.3749647, -122.8732875, 13 + 15 / 60)
        old_overlays.close.assert_called_once()
        app.voice_audio.discard_transmissions.assert_called_once()
        self.assertFalse(app.communications_panel.mic_hot)
        self.assertEqual(app.communications_panel.voice_status, "VOICE READY")
        self.assertIs(app.selected_location, LOCATIONS[1])
        self.assertEqual(app.selected_sector.label, "Medford")
        self.assertEqual(app.atc_facility.airport_code, "KMFR")
        self.assertEqual(app.atc_facility.active_runways, ("32",))
        self.assertEqual(app.aircraft_list.aircraft_list, [])
        self.assertTrue(app.map_preview)
        self.assertEqual(app.available_scenarios(), ())
        self.assertNotIn(
            "KNYL", " ".join(line.label for line in app.communications_panel.lines)
        )

    def test_location_switch_confirms_and_cancel_preserves_scenario(self):
        app = make_application()
        app.scenario_loaded = True
        aircraft = object()
        app.aircraft_list = aircraft
        with patch.object(app, "activate_location") as activate:
            app.select_location(LOCATIONS[1])
            self.assertTrue(app.confirm_replace)
            self.assertIs(app.selected_location, LOCATIONS[0])
            app.on_key_press(arcade.key.N, 0)
            self.assertIs(app.aircraft_list, aircraft)
            self.assertFalse(app.confirm_replace)
            activate.assert_not_called()
            app.select_location(LOCATIONS[1])
            app.on_key_press(arcade.key.Y, 0)
            activate.assert_called_once_with(LOCATIONS[1], LOCATIONS[1].sectors[0])

    def test_failed_location_setup_keeps_current_scenario(self):
        app = make_application()
        app.scenario_loaded = True
        app.gis_overlays = Mock(visible={0})
        with (
            patch("simulator.app.application.FlightStripPanel"),
            patch("simulator.app.application.CommunicationsPanel"),
            patch(
                "simulator.app.application.GISOverlays",
                side_effect=RuntimeError("map unavailable"),
            ),
            self.assertLogs("simulator.app.application", level="ERROR"),
        ):
            app.select_location(LOCATIONS[1])
            app.on_key_press(arcade.key.Y, 0)
        self.assertIs(app.selected_location, LOCATIONS[0])
        self.assertTrue(app.scenario_loaded)
        self.assertIn("map unavailable", app.menu_message)
        app.gis_overlays.close.assert_not_called()

    def test_scenario_waits_for_maps_and_enabled_voice(self):
        app = make_application()
        create = Mock()
        add_test_scenario(app, create)
        app.gis_overlays.status[0] = "loading"
        app.request_scenario(app.available_scenarios()[0])
        self.assertIn("LOADING MAPS", app.menu_message)
        app.gis_overlays.status[0] = "ready"
        app.voice_audio = Mock(ready=False)
        app.request_scenario(app.available_scenarios()[0])
        self.assertEqual(app.menu_message, "LOADING VOICE")
        app.communications_panel.voice_status = "VOICE ERROR"
        app.voice_message = "Microphone unavailable"
        app.request_scenario(app.available_scenarios()[0])
        self.assertIn("Microphone unavailable", app.menu_message)
        create.assert_not_called()

    def test_menu_load_and_confirmed_replacement_reset_scenario(self):
        app = make_application()
        add_test_scenario(app)
        app.voice_audio = Mock(ready=True)
        with patch("simulator.app.application.FlightStripPanel") as panel:
            app.on_mouse_press(
                MENU_WIDTH + 10, MENU_BOTTOM + 5, arcade.MOUSE_BUTTON_LEFT, 0
            )
            app.on_mouse_press(
                MENU_WIDTH + 10, MENU_BOTTOM - 5, arcade.MOUSE_BUTTON_LEFT, 0
            )
            self.assertTrue(app.scenario_loaded)
            self.assertTrue(app.briefing)
            app.on_key_press(arcade.key.ENTER, 0)
            channels = {
                channel.identifier: channel.state
                for channel in app.communications_panel.channels
            }
            self.assertTrue(
                all(
                    channels[identifier] == RadioState.ON
                    for identifier in (
                        "approach_low",
                        "approach_high",
                        "departure_low",
                        "departure_high",
                        "enroute_low",
                        "enroute_high",
                    )
                )
            )
            self.assertEqual(channels["tower_low"], RadioState.OFF)
            self.assertEqual(channels["emergency_low"], RadioState.LISTEN)
            radio = {
                channel.identifier: channel
                for channel in app.communications_panel.channels
            }
            radio["departure_high"].state = RadioState.OFF
            radio["tower_low"].state = RadioState.ON
            first = app.aircraft_list
            first.aircraft_list[0].flight_guidance.assign_heading(180)
            app.selected_aircraft_id = first.aircraft_list[0].id
            app.request_scenario(app.available_scenarios()[0])
            self.assertTrue(app.confirm_replace)
            app.on_key_press(arcade.key.N, 0)
            self.assertIs(app.aircraft_list, first)
            self.assertEqual(radio["departure_high"].state, RadioState.OFF)
            app.request_scenario(app.available_scenarios()[0])
            app.on_key_press(arcade.key.Y, 0)
            self.assertIsNot(app.aircraft_list, first)
            self.assertIsNone(
                app.aircraft_list.aircraft_list[0].flight_guidance.vector_heading
            )
            self.assertIsNone(app.selected_aircraft_id)
            self.assertEqual(radio["departure_high"].state, RadioState.ON)
            self.assertEqual(radio["tower_low"].state, RadioState.ON)
            self.assertEqual(panel.call_count, 2)
            self.assertEqual(app.voice_audio.discard_transmissions.call_count, 2)

    def test_scenario_briefing_pauses_until_acknowledged(self):
        app = make_application()
        add_test_scenario(app)
        app.gis_overlays = Mock(visible={0}, status=["ready"])
        with patch("simulator.app.application.FlightStripPanel"):
            app.request_scenario(app.available_scenarios()[0])
        aircraft = app.aircraft_list.aircraft_list[0]
        position = aircraft.lat, aircraft.lon
        text = "\n".join(line for page in app.briefing for line in page)
        self.assertIn("altimeter 29.92 assumed", text)
        self.assertIn(aircraft.callsign, text)
        with patch.object(app, "update_menu_theme"):
            app.on_update(60)
            self.assertEqual((aircraft.lat, aircraft.lon), position)
            app.on_key_press(arcade.key.RIGHT, 0)
            self.assertEqual(app.briefing_page, 1)
            app.on_key_press(arcade.key.ENTER, 0)
            app.on_update(60)
        self.assertNotEqual((aircraft.lat, aircraft.lon), position)

    def test_tab_pauses_time_controls_and_voice_until_resumed(self):
        app = make_application()
        add_test_scenario(app)
        app.gis_overlays = Mock(visible={0}, status=["ready"])
        with patch("simulator.display.flight_strips.arcade.Text"):
            app.request_scenario(app.available_scenarios()[0])
        app.on_key_press(arcade.key.ENTER, 0)
        aircraft = app.aircraft_list.aircraft_list[0]
        position = aircraft.lat, aircraft.lon
        start = app.scenario_utc
        sweep = app.sweep.angle
        app.communications_panel.keyboard_ptt = True
        app.voice_audio = Mock(ready=True)
        app.communications_panel.pilot_channel = "enroute_low"

        app.on_key_press(arcade.key.TAB, 0)
        self.assertTrue(app.paused)
        self.assertFalse(app.communications_panel.mic_hot)
        self.assertIsNone(app.communications_panel.pilot_channel)
        app.voice_audio.discard_transmissions.assert_called_once()
        with (
            patch.object(RadarDisplay, "on_draw"),
            patch("simulator.app.application.arcade.draw_rect_filled"),
            patch.object(app, "_draw_text") as draw_text,
        ):
            app.on_draw()
            draw_text.assert_any_call(
                "PAUSED - PRESS TAB TO RESUME",
                (SCREEN_WIDTH + PANEL_WIDTH) / 2,
                SCREEN_HEIGHT - 47,
                "center",
            )

        with (
            patch.object(app, "update_menu_theme"),
            patch.object(RadarDisplay, "on_key_press") as keys,
            patch.object(RadarDisplay, "on_mouse_press") as clicks,
            patch.object(RadarDisplay, "on_mouse_drag") as drag,
            patch.object(RadarDisplay, "on_mouse_release") as release,
            patch.object(RadarDisplay, "on_mouse_scroll") as scroll,
            patch.object(RadarDisplay, "on_mouse_motion") as motion,
            patch.object(RadarDisplay, "process_voice") as process_voice,
        ):
            app.on_update(60)
            app.on_key_press(arcade.key.SPACE, 0)
            app.on_key_press(arcade.key.ESCAPE, 0)
            self.assertTrue(app.paused)
            app.on_mouse_press(1, 1, arcade.MOUSE_BUTTON_LEFT, 0)
            app.on_mouse_drag(1, 1, 1, 1, arcade.MOUSE_BUTTON_LEFT, 0)
            app.on_mouse_release(1, 1, arcade.MOUSE_BUTTON_LEFT, 0)
            app.on_mouse_scroll(1, 1, 0, 1)
            app.on_mouse_motion(1, 1, 1, 1)
            self.assertEqual((aircraft.lat, aircraft.lon), position)
            self.assertEqual(app.scenario_utc, start)
            self.assertEqual(app.sweep.angle, sweep)
            for callback in (keys, clicks, drag, release, scroll, motion, process_voice):
                callback.assert_not_called()
            app.on_key_press(arcade.key.TAB, 0)
            self.assertFalse(app.paused)
            app.on_update(60)
            process_voice.assert_called_once()
        self.assertNotEqual((aircraft.lat, aircraft.lon), position)
        self.assertEqual(app.scenario_utc, start + timedelta(seconds=60))

    def test_escape_cancels_interactions_without_pausing(self):
        app = make_application()
        add_test_scenario(app)
        app.gis_overlays = Mock(visible={0}, status=["ready"])
        with patch("simulator.display.flight_strips.arcade.Text"):
            app.request_scenario(app.available_scenarios()[0])
        app.on_key_press(arcade.key.ENTER, 0)

        app.open_menu = "options"
        app.on_key_press(arcade.key.ESCAPE, 0)
        self.assertIsNone(app.open_menu)
        self.assertFalse(app.paused)

        for attribute, value in (
            ("drag_strip", app.strip_panel.strips[0]),
            ("edit_strip", app.strip_panel.strips[0]),
            ("show_discarded", True),
        ):
            with self.subTest(interaction=attribute):
                setattr(app.strip_panel, attribute, value)
                if attribute == "edit_strip":
                    app.strip_panel.edit_field = "remarks"
                app.on_key_press(arcade.key.ESCAPE, 0)
                self.assertFalse(getattr(app.strip_panel, attribute))
                self.assertFalse(app.paused)

        for attribute in (
            "clearance_draft",
            "coordination_draft",
            "scratchpad_edit_id",
            "handoff_choice_id",
        ):
            with self.subTest(interaction=attribute):
                setattr(app, attribute, "active")
                app.on_key_press(arcade.key.ESCAPE, 0)
                self.assertIsNone(getattr(app, attribute))
                self.assertFalse(app.paused)

        app.on_key_press(arcade.key.ESCAPE, 0)
        self.assertFalse(app.paused)

    def test_tab_pauses_without_closing_active_interactions(self):
        app = make_application()
        add_test_scenario(app)
        app.gis_overlays = Mock(visible={0}, status=["ready"])
        with patch("simulator.display.flight_strips.arcade.Text"):
            app.request_scenario(app.available_scenarios()[0])

        briefing = app.briefing
        app.on_key_press(arcade.key.TAB, 0)
        self.assertTrue(app.paused)
        self.assertIs(app.briefing, briefing)
        app.on_key_press(arcade.key.TAB, 0)
        app.on_key_press(arcade.key.ENTER, 0)

        for attribute, value in (
            ("open_menu", "options"),
            ("generator_dialog", Mock()),
            ("saves_dialog", Mock()),
            ("confirm_replace", True),
            ("clearance_draft", "active"),
            ("coordination_draft", "active"),
            ("scratchpad_edit_id", "A1"),
            ("handoff_choice_id", "A1"),
        ):
            with self.subTest(interaction=attribute):
                setattr(app, attribute, value)
                app.on_key_press(arcade.key.TAB, 0)
                self.assertTrue(app.paused)
                self.assertIs(getattr(app, attribute), value)
                app.on_key_press(arcade.key.TAB, 0)
                self.assertFalse(app.paused)
                setattr(app, attribute, False if attribute == "confirm_replace" else None)

        strip = app.strip_panel.strips[0]
        app.strip_panel.edit_strip = strip
        app.strip_panel.edit_field = "remarks"
        app.on_key_press(arcade.key.TAB, 0)
        self.assertTrue(app.paused)
        self.assertIs(app.strip_panel.edit_strip, strip)
        app.on_key_press(arcade.key.TAB, 0)
        app.on_key_press(arcade.key.ESCAPE, 0)
        self.assertIsNone(app.strip_panel.edit_strip)

        app.strip_panel.drag_strip = strip
        app.on_key_press(arcade.key.TAB, 0)
        self.assertTrue(app.paused)
        self.assertIsNone(app.strip_panel.drag_strip)
        app.on_mouse_release(1, 1, arcade.MOUSE_BUTTON_LEFT, 0)
        app.on_key_press(arcade.key.TAB, 0)
        self.assertFalse(app.paused)

    def test_scheduled_arrival_waits_while_paused_and_appears_on_radar(self):
        app = make_application()
        operations = dict.fromkeys(OPERATIONS, 0)
        operations["approaches"] = 1
        settings = GeneratorSettings(0, "light", operations)
        add_test_scenario(app, lambda: generate_yuma_scenario(settings)[:3])
        app.gis_overlays = Mock(visible={0}, status=["ready"])
        with patch("simulator.display.flight_strips.arcade.Text"):
            app.request_scenario(app.available_scenarios()[0])
        app.on_key_press(arcade.key.ENTER, 0)
        arrival = app.aircraft_list.aircraft_list[1]
        self.assertNotIn(arrival.id, [item.aircraft_id for item in app.secondary_radar_returns])
        with patch.object(app, "update_menu_theme"):
            app.on_update(299)
            self.assertEqual(arrival.entry_remaining, 1)
            app.on_key_press(arcade.key.TAB, 0)
            app.on_update(600)
            self.assertEqual(arrival.entry_remaining, 1)
            app.on_key_press(arcade.key.TAB, 0)
            app.on_update(1)
        self.assertIsNone(arrival.entry_remaining)
        self.assertIn(arrival.id, [item.aircraft_id for item in app.secondary_radar_returns])
        self.assertIn(arrival.id, [strip.aircraft.id for strip in app.strip_panel.active_strips()])

    def test_incoming_checkin_waits_while_paused(self):
        app = make_application()
        add_test_scenario(app)
        app.gis_overlays = Mock(visible={0}, status=["ready"])
        with patch("simulator.display.flight_strips.arcade.Text"):
            app.request_scenario(app.available_scenarios()[0])
        app.on_key_press(arcade.key.ENTER, 0)
        incoming = next(p for p in app.aircraft_list.aircraft_list if p.id == "A3")
        incoming.lat = app.atc_facility.location.latitude
        incoming.lon = app.atc_facility.location.longitude
        incoming.track.accept(TrackingPosition.YUMA)
        incoming.track.transfer_communications()
        with patch.object(app, "update_menu_theme"):
            app.on_key_press(arcade.key.TAB, 0)
            app.on_update(1)
            self.assertTrue(incoming.incoming_checkin_pending)
            self.assertFalse(app.departure_checkins)
            app.on_key_press(arcade.key.TAB, 0)
            app.on_update(1)
        self.assertFalse(incoming.incoming_checkin_pending)
        self.assertIn("YUMA APPROACH", app.departure_checkins[0])

    def test_audio_menu_toggles_voice_and_retry_requeues_failed_map(self):
        app = make_application()
        app.gis_overlays = Mock(visible={0}, status=["error"])
        app.enable_voice = Mock()
        app.disable_voice = Mock()
        app.on_mouse_press(
            2 * MENU_WIDTH + 10, MENU_BOTTOM + 5, arcade.MOUSE_BUTTON_LEFT, 0
        )
        app.on_mouse_press(
            2 * MENU_WIDTH + 10, MENU_BOTTOM - 5, arcade.MOUSE_BUTTON_LEFT, 0
        )
        self.assertEqual(app.submenu_option, "audio")
        app.on_mouse_press(
            2 * MENU_WIDTH + MENU_ITEM_WIDTH + 10,
            MENU_BOTTOM - 5,
            arcade.MOUSE_BUTTON_LEFT,
            0,
        )
        app.enable_voice.assert_called_once()
        app.voice_audio = Mock()
        app.on_mouse_press(
            2 * MENU_WIDTH + 10, MENU_BOTTOM + 5, arcade.MOUSE_BUTTON_LEFT, 0
        )
        app.on_mouse_motion(2 * MENU_WIDTH + 10, MENU_BOTTOM - 5, 0, 0)
        app.on_mouse_press(
            2 * MENU_WIDTH + MENU_ITEM_WIDTH + 10,
            MENU_BOTTOM - 5,
            arcade.MOUSE_BUTTON_LEFT,
            0,
        )
        app.disable_voice.assert_called_once()
        app.on_mouse_press(
            MENU_WIDTH + 10, MENU_BOTTOM + 5, arcade.MOUSE_BUTTON_LEFT, 0
        )
        app.on_mouse_press(
            MENU_WIDTH + 10,
            MENU_BOTTOM - (len(app.menu_entries("scenario")) - 1) * ITEM_HEIGHT - 5,
            arcade.MOUSE_BUTTON_LEFT,
            0,
        )
        self.assertEqual(app.gis_overlays.toggle.call_count, 2)

    def test_generator_menu_configures_traffic_and_starts_paused(self):
        app = make_application()
        app.gis_overlays = Mock(visible={0}, status=["ready"])
        start = datetime(2026, 11, 15, 20, 0, tzinfo=UTC)
        self.assertIn("Generate Yuma...", app.menu_entries("scenario"))
        with (
            patch.object(app, "utc_now", return_value=start),
            patch("simulator.app.application.FlightStripPanel"),
            patch.object(app, "update_menu_theme"),
        ):
            app.on_mouse_press(
                MENU_WIDTH + 10, MENU_BOTTOM + 5, arcade.MOUSE_BUTTON_LEFT, 0
            )
            app.on_mouse_press(
                MENU_WIDTH + 10,
                MENU_BOTTOM - 5,
                arcade.MOUSE_BUTTON_LEFT,
                0,
            )
            dialog = app.generator_dialog
            self.assertIsNotNone(dialog)
            for _ in range(len(dialog.seed)):
                app.on_key_press(arcade.key.BACKSPACE, 0)
            app.on_key_press(arcade.key.KEY_4, 0)
            app.on_key_press(arcade.key.KEY_2, 0)
            app.on_key_press(arcade.key.DOWN, 0)
            app.on_key_press(arcade.key.LEFT, 0)
            app.on_key_press(arcade.key.LEFT, 0)
            app.on_mouse_press(1160, 770 - 2 * 45, arcade.MOUSE_BUTTON_LEFT, 0)
            app.on_key_press(arcade.key.ENTER, 0)
            self.assertIsNone(app.generator_dialog)
            self.assertTrue(app.scenario_loaded)
            self.assertEqual(len(app.aircraft_list.aircraft_list), 3)
            self.assertEqual(app.generator_settings.seed, 42)
            self.assertEqual(app.generator_settings.operations["departures"], 2)
            self.assertIn("Location: MCAS Yuma", app.briefing[0])
            self.assertEqual(app.scenario_utc, start)
            app.on_update(60)
            self.assertEqual(app.scenario_utc, start)
            app.on_key_press(arcade.key.ENTER, 0)
            app.on_update(60)
            self.assertEqual(app.scenario_utc, start + timedelta(seconds=60))

    def test_menu_displays_wall_utc_then_scenario_utc(self):
        app = make_application()
        app.map_preview = True
        now = datetime(2026, 11, 15, 20, 0, tzinfo=UTC)
        with (
            patch.object(app, "utc_now", return_value=now),
            patch.object(app, "_draw_text") as text,
            patch.object(RadarDisplay, "on_draw"),
            patch("simulator.app.application.arcade.draw_rect_filled"),
        ):
            app.on_draw()
            self.assertTrue(
                any(
                    call.args[0] == "UTC 11-15 20:00:00" for call in text.call_args_list
                )
            )
            text.reset_mock()
            app.scenario_utc = now + timedelta(hours=1)
            app.on_draw()
            self.assertTrue(
                any(
                    call.args[0] == "UTC 11-15 21:00:00" for call in text.call_args_list
                )
            )

    def test_generator_cancel_and_invalid_settings_keep_existing_scenario(self):
        app = make_application()
        add_test_scenario(app)
        app.gis_overlays = Mock(visible={0}, status=["ready"])
        with patch("simulator.app.application.FlightStripPanel"):
            app.request_scenario(app.available_scenarios()[0])
            app.on_key_press(arcade.key.ENTER, 0)
            previous = app.aircraft_list
            app.open_generator()
            app.generator_dialog.operations = dict.fromkeys(
                app.generator_dialog.operations, 0
            )
            app.on_key_press(arcade.key.ENTER, 0)
            self.assertIn("at least one enabled", app.generator_dialog.error)
            self.assertIs(app.aircraft_list, previous)
            app.generator_dialog.operations["departures"] = 1
            app.on_key_press(arcade.key.ENTER, 0)
            self.assertTrue(app.confirm_replace)
            app.on_key_press(arcade.key.N, 0)
            self.assertIs(app.aircraft_list, previous)
            self.assertIsNotNone(app.generator_dialog)
            app.on_key_press(arcade.key.ENTER, 0)
            app.on_key_press(arcade.key.Y, 0)
            self.assertIsNot(app.aircraft_list, previous)
            self.assertTrue(app.briefing)

    def test_generator_reports_unsupported_selection_without_replacing_traffic(self):
        app = make_application()
        add_test_scenario(app)
        app.gis_overlays = Mock(visible={0}, status=["ready"])
        with patch("simulator.app.application.FlightStripPanel"):
            app.request_scenario(app.available_scenarios()[0])
            app.on_key_press(arcade.key.ENTER, 0)
            previous = app.aircraft_list
            app.open_generator()
            app.generator_dialog.operations = dict.fromkeys(
                app.generator_dialog.operations, 0
            )
            app.generator_dialog.operations["enroute"] = 1
            app.generator_dialog.aircraft_types = dict.fromkeys(
                app.generator_dialog.aircraft_types, 0
            )
            app.generator_dialog.aircraft_types["heavies"] = 1
            app.on_key_press(arcade.key.ENTER, 0)
            with (
                patch(
                    "locations.Yuma.Scenarios.generator._itineraries", return_value=[]
                ),
                self.assertLogs("simulator.app.application", level="ERROR"),
            ):
                app.on_key_press(arcade.key.Y, 0)
            self.assertIs(app.aircraft_list, previous)
            self.assertIn("No supported combinations", app.generator_dialog.error)

    def test_scenario_menu_saves_and_restores_running_state(self):
        app = make_application()
        add_test_scenario(app)
        app.gis_overlays = Mock(visible={0}, status=["ready"])

        def panel(strips, *args):
            return SimpleNamespace(strips=strips, edit_strip=None, drag_strip=None)

        with (
            tempfile.TemporaryDirectory() as folder,
            patch("simulator.app.scenario_storage.SAVE_DIRECTORY", Path(folder)),
            patch("simulator.app.application.FlightStripPanel", side_effect=panel),
            patch.object(app, "update_menu_theme"),
        ):
            app.request_scenario(app.available_scenarios()[0])
            del app.available_scenarios
            app.on_key_press(arcade.key.ENTER, 0)
            app.select_yuma_runways(1)
            app.select_yuma_runways(4)
            self.assertEqual(app.atc_facility.active_runways, ("21R", "21L", "26"))
            plane = app.aircraft_list.aircraft_list[0]
            voices = [item.pilot_voice for item in app.aircraft_list.aircraft_list]
            self.assertTrue(all(voices))
            with patch("simulator.display.radar.VoiceAudio"):
                app.enable_voice()
                app.disable_voice()
                app.enable_voice()
                self.assertEqual(
                    [item.pilot_voice for item in app.aircraft_list.aircraft_list],
                    voices,
                )
                app.disable_voice()
            plane.flight_guidance.assign_heading(230)
            plane.scratchpad = "XY"
            app.on_update(60)
            saved_position = plane.lat, plane.lon
            saved_time = app.scenario_utc
            app.communications_panel.channels[0].state = RadioState.OFF
            app.communications_panel.interfacility_lines[2].hot = True

            def choose(index):
                app.on_mouse_press(
                    MENU_WIDTH + 10, MENU_BOTTOM + 5, arcade.MOUSE_BUTTON_LEFT, 0
                )
                app.on_mouse_press(
                    MENU_WIDTH + 10,
                    MENU_BOTTOM - index * ITEM_HEIGHT - 5,
                    arcade.MOUSE_BUTTON_LEFT,
                    0,
                )

            choose(2)
            self.assertEqual(app.saves_dialog.mode, "save")
            for key in (
                arcade.key.S,
                arcade.key.A,
                arcade.key.V,
                arcade.key.E,
                arcade.key.KEY_1,
            ):
                app.on_key_press(key, 0)
            app.on_update(30)
            self.assertEqual(app.scenario_utc, saved_time)
            app.on_key_press(arcade.key.ENTER, 0)
            self.assertTrue((Path(folder) / "SAVE1.json").exists())
            app.communications_panel.interfacility_lines[2].hot = False
            app.on_update(60)
            self.assertNotEqual((plane.lat, plane.lon), saved_position)
            choose(1)
            self.assertEqual(app.saves_dialog.names, ["SAVE1"])
            app.on_key_press(arcade.key.ENTER, 0)
            self.assertTrue(app.confirm_replace)
            app.on_key_press(arcade.key.N, 0)
            self.assertIs(app.aircraft_list.aircraft_list[0], plane)
            app.on_key_press(arcade.key.ENTER, 0)
            app.on_key_press(arcade.key.Y, 0)
            restored = app.aircraft_list.aircraft_list[0]
            self.assertEqual(app.atc_facility.active_runways, ("21R", "21L", "26"))
            self.assertTrue(app.menu_entries("runways")[1].startswith("(*)"))
            self.assertTrue(app.menu_entries("runways")[4].startswith("(*)"))
            self.assertEqual(
                [item.pilot_voice for item in app.aircraft_list.aircraft_list], voices
            )
            self.assertEqual((restored.lat, restored.lon), saved_position)
            self.assertEqual(restored.scratchpad, "XY")
            self.assertEqual(restored.flight_guidance.vector_heading, 230)
            self.assertEqual(app.scenario_utc, saved_time)
            self.assertEqual(app.communications_panel.channels[0].state, RadioState.OFF)
            self.assertTrue(app.communications_panel.interfacility_lines[2].hot)
            self.assertTrue(app.briefing)
            app.on_update(60)
            self.assertEqual(app.scenario_utc, saved_time)

    def test_bad_save_and_cancelled_overwrite_preserve_existing_state(self):
        app = make_application()
        add_test_scenario(app)
        app.gis_overlays = Mock(visible={0}, status=["ready"])

        def panel(strips, *args):
            return SimpleNamespace(strips=strips, edit_strip=None, drag_strip=None)

        with (
            tempfile.TemporaryDirectory() as folder,
            patch("simulator.app.scenario_storage.SAVE_DIRECTORY", Path(folder)),
            patch("simulator.app.application.FlightStripPanel", side_effect=panel),
        ):
            app.request_scenario(app.available_scenarios()[0])
            app.on_key_press(arcade.key.ENTER, 0)
            aircraft = app.aircraft_list
            path = Path(folder) / "BAD.json"
            path.write_text('{"version": 1}', encoding="utf-8")
            app.open_saves("load")
            with self.assertLogs("simulator.app.application", level="WARNING"):
                app.on_key_press(arcade.key.ENTER, 0)
            self.assertIn("Invalid saved state fields", app.saves_dialog.error)
            self.assertIs(app.aircraft_list, aircraft)
            app.on_key_press(arcade.key.ESCAPE, 0)
            app.open_saves("save")
            for key in (arcade.key.B, arcade.key.A, arcade.key.D):
                app.on_key_press(key, 0)
            app.on_key_press(arcade.key.ENTER, 0)
            self.assertTrue(app.saves_dialog.confirm_overwrite)
            app.on_key_press(arcade.key.N, 0)
            self.assertEqual(path.read_text(encoding="utf-8"), '{"version": 1}')
            app.on_key_press(arcade.key.ENTER, 0)
            app.on_key_press(arcade.key.Y, 0)
            self.assertIn('"records"', path.read_text(encoding="utf-8"))
            self.assertIs(app.aircraft_list, aircraft)

    def test_display_submenu_selects_arts_and_reports_unavailable_scopes(self):
        app = make_application()
        self.assertEqual(
            app.menu_entries("options"),
            ("Audio  >", "Display  >", "Range rings  >", "Runways  >"),
        )
        self.assertEqual(
            app.menu_entries("display"),
            ("* ARTS IIE", "  FDAD (unavailable)", "  ACD (unavailable)"),
        )
        options_x = 2 * MENU_WIDTH + 10
        submenu_x = 2 * MENU_WIDTH + MENU_ITEM_WIDTH + 10
        for index, scope in ((1, "FDAD"), (2, "ACD")):
            with self.subTest(scope=scope):
                app.on_mouse_press(
                    options_x, MENU_BOTTOM + 5, arcade.MOUSE_BUTTON_LEFT, 0
                )
                app.on_mouse_motion(options_x, MENU_BOTTOM - ITEM_HEIGHT - 5, 0, 0)
                self.assertEqual(app.submenu_option, "display")
                app.on_mouse_motion(
                    submenu_x, MENU_BOTTOM - (index + 1) * ITEM_HEIGHT - 5, 0, 0
                )
                self.assertEqual(app.menu_hover, ("option", index))
                app.on_mouse_press(
                    submenu_x,
                    MENU_BOTTOM - (index + 1) * ITEM_HEIGHT - 5,
                    arcade.MOUSE_BUTTON_LEFT,
                    0,
                )
                self.assertEqual(app.display_type, RadarDisplay.ARTS_IIE)
                self.assertIn(scope, app.menu_message)
                self.assertIn("not available", app.menu_message)
        app.display_type = RadarDisplay.STARS
        app.on_mouse_press(options_x, MENU_BOTTOM + 5, arcade.MOUSE_BUTTON_LEFT, 0)
        app.on_mouse_press(
            options_x, MENU_BOTTOM - ITEM_HEIGHT - 5, arcade.MOUSE_BUTTON_LEFT, 0
        )
        app.on_mouse_press(
            submenu_x, MENU_BOTTOM - ITEM_HEIGHT - 5, arcade.MOUSE_BUTTON_LEFT, 0
        )
        self.assertEqual(app.display_type, RadarDisplay.ARTS_IIE)
        self.assertEqual(app.menu_message, "")
        self.assertIsNone(app.open_menu)

    def test_range_ring_menu_selects_brightness_and_off(self):
        app = make_application()
        options_x = 2 * MENU_WIDTH + 10
        submenu_x = 2 * MENU_WIDTH + MENU_ITEM_WIDTH + 10
        self.assertEqual(app.menu_entries("range_rings")[3], "* 30%")
        for index in (10, 0, 4):
            app.on_mouse_press(options_x, MENU_BOTTOM + 5, arcade.MOUSE_BUTTON_LEFT, 0)
            app.on_mouse_press(
                options_x,
                MENU_BOTTOM - 2 * ITEM_HEIGHT - 5,
                arcade.MOUSE_BUTTON_LEFT,
                0,
            )
            self.assertEqual(app.submenu_option, "range_rings")
            app.on_mouse_press(
                submenu_x,
                MENU_BOTTOM - (index + 2) * ITEM_HEIGHT - 5,
                arcade.MOUSE_BUTTON_LEFT,
                0,
            )
            self.assertEqual(app.range_ring_brightness, index * 10)
            self.assertTrue(app.menu_entries("range_rings")[index].startswith("* "))
            self.assertIsNone(app.open_menu)

    def test_pubs_menu_browses_folders_and_opens_selected_pdf(self):
        app = make_application()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            approach = root / "Procedures" / "Approach"
            approach.mkdir(parents=True)
            chart = approach / "ILS 21R.PDF"
            chart.write_bytes(b"%PDF")
            (root / "Airport diagram.pdf").write_bytes(b"%PDF")
            app.selected_location = LocationChoice("Test", "KNYL", pubs_directory=root)
            x = 3 * MENU_WIDTH + 10
            app.on_mouse_press(x, MENU_BOTTOM + 5, arcade.MOUSE_BUTTON_LEFT, 0)
            self.assertEqual(
                app.menu_entries("pubs"),
                ("FAA JO 7110.65BB", "Procedures  >", "Airport diagram.pdf"),
            )
            app.on_mouse_press(
                x, MENU_BOTTOM - ITEM_HEIGHT - 5, arcade.MOUSE_BUTTON_LEFT, 0
            )
            self.assertEqual(app.menu_entries("pubs"), ("< Back", "Approach  >"))
            app.on_mouse_press(
                x, MENU_BOTTOM - ITEM_HEIGHT - 5, arcade.MOUSE_BUTTON_LEFT, 0
            )
            self.assertEqual(app.menu_entries("pubs"), ("< Back", "ILS 21R.PDF"))
            with patch("simulator.app.application.threading.Thread") as thread:
                app.on_mouse_press(
                    x, MENU_BOTTOM - ITEM_HEIGHT - 5, arcade.MOUSE_BUTTON_LEFT, 0
                )
            self.assertIsNone(app.open_menu)
            self.assertEqual(thread.call_args.kwargs["args"], (chart, app.pubs_results))
            thread.return_value.start.assert_called_once()

            app.on_mouse_press(x, MENU_BOTTOM + 5, arcade.MOUSE_BUTTON_LEFT, 0)
            app.on_mouse_press(
                x, MENU_BOTTOM - ITEM_HEIGHT - 5, arcade.MOUSE_BUTTON_LEFT, 0
            )
            app.on_mouse_press(x, MENU_BOTTOM - 5, arcade.MOUSE_BUTTON_LEFT, 0)
            self.assertEqual(app.pubs_directory, root)

    def test_pubs_uses_selected_sector_and_paginates(self):
        app = make_application()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            location_root = root / "location"
            sector_root = root / "sector"
            location_root.mkdir()
            sector_root.mkdir()
            for index in range(22):
                (sector_root / f"chart{index:02}.pdf").write_bytes(b"%PDF")
            app.selected_location = LocationChoice(
                "Test", "KMFR", pubs_directory=location_root
            )
            app.selected_sector = SectorChoice("Sector", (), sector_root)
            app.open_pubs_menu()
            self.assertEqual(app.pubs_directory, sector_root)
            self.assertEqual(app.menu_entries("pubs")[-1], "Next page >")
            app.select_pub(len(app.menu_entries("pubs")) - 1)
            self.assertEqual(
                app.menu_entries("pubs"),
                (
                    "FAA JO 7110.65BB",
                    "< Previous page",
                    "chart20.pdf",
                    "chart21.pdf",
                ),
            )
            app.select_pub(1)
            self.assertEqual(app.pubs_page, 0)
            app.selected_sector = None
            app.open_pubs_menu()
            self.assertEqual(
                app.menu_entries("pubs"),
                ("FAA JO 7110.65BB", "No publications available"),
            )

    def test_pubs_reports_file_and_viewer_errors(self):
        app = make_application()
        app.selected_location = None
        app.open_pubs_menu()
        self.assertEqual(
            app.menu_entries("pubs"), ("FAA JO 7110.65BB", "Select a location first")
        )
        self.assertTrue(FAA_7110_65.is_file())
        with patch("simulator.app.application.threading.Thread") as thread:
            x = 3 * MENU_WIDTH + 10
            app.on_mouse_press(x, MENU_BOTTOM + 5, arcade.MOUSE_BUTTON_LEFT, 0)
            app.on_mouse_press(x, MENU_BOTTOM - 5, arcade.MOUSE_BUTTON_LEFT, 0)
        self.assertEqual(
            thread.call_args.kwargs["args"], (FAA_7110_65, app.pubs_results)
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "chart.pdf"
            path.write_bytes(b"%PDF")
            (root / "notes.txt").write_text("notes", encoding="utf-8")
            app.selected_location = LocationChoice("Test", "KNYL", pubs_directory=root)
            app.open_pubs_menu()
            app.select_pub(2)
            self.assertIn("Only PDF", app.menu_message)
            path.unlink()
            app.select_pub(1)
            self.assertIn("File not found", app.menu_message)
            path.write_bytes(b"%PDF")
            with (
                patch("simulator.app.application.sys.platform", "win32"),
                patch(
                    "simulator.app.application.os.startfile",
                    side_effect=OSError("no viewer"),
                ),
            ):
                app.launch_publication(path, app.pubs_results)
            app.gis_overlays = None
            with self.assertLogs("simulator.app.application", level="ERROR"):
                app.on_update(0)
            self.assertIn("no viewer", app.menu_message)

    def test_pubs_reports_directory_read_failure(self):
        app = make_application()
        app.selected_location = LocationChoice(
            "Test", "KNYL", pubs_directory=Path("unreadable")
        )
        with (
            patch.object(Path, "iterdir", side_effect=PermissionError("access denied")),
            self.assertLogs("simulator.app.application", level="ERROR"),
        ):
            app.open_pubs_menu()
        self.assertIn("access denied", app.menu_message)
        self.assertIsNone(app.pubs_directory)

    def test_runway_change_reassigns_waiting_departures(self):
        app = make_application()
        _, facility, strips = create_yuma_scenario()
        app.scenario_loaded = True
        app.atc_facility = facility
        app.strip_panel = SimpleNamespace(
            strips=strips, active_runways=facility.active_runways
        )
        waiting = [
            strip
            for strip in strips
            if strip.aircraft.departure is not None
            and strip.operation_area in ("03L", "03R")
        ]
        self.assertTrue(waiting)
        old_areas = [strip.operation_area for strip in waiting]
        app.select_yuma_runways(1)
        self.assertEqual(facility.active_runways, ("21R", "21L", "35"))
        self.assertEqual(app.strip_panel.active_runways, facility.active_runways)
        self.assertEqual(
            [strip.operation_area for strip in waiting],
            [{"03L": "21R", "03R": "21L"}[area] for area in old_areas],
        )
        for strip in waiting:
            self.assertAlmostEqual(
                strip.aircraft.heading, facility.location.magnetic_to_true(210)
            )
        app.select_yuma_runways(0)
        self.assertEqual([strip.operation_area for strip in waiting], old_areas)

    def test_runway_change_waits_for_takeoff(self):
        app = make_application()
        _, facility, strips = create_yuma_scenario()
        app.scenario_loaded = True
        app.atc_facility = facility
        app.strip_panel = SimpleNamespace(
            strips=strips, active_runways=facility.active_runways
        )
        strip = next(
            strip
            for strip in strips
            if strip.aircraft.departure is not None
            and strip.operation_area in ("03L", "03R")
        )
        strip.aircraft.departure.state = "takeoff"
        app.select_yuma_runways(1)
        self.assertEqual(facility.active_runways, ("03L", "03R", "35"))
        self.assertIn("Wait", app.menu_message)

    def test_runway_radio_groups_and_waiting_departure_headings(self):
        app = make_application()
        _, facility, strips = create_yuma_scenario()
        app.scenario_loaded = True
        app.atc_facility = facility
        app.strip_panel = SimpleNamespace(
            strips=strips, active_runways=facility.active_runways
        )
        strip = next(item for item in strips if item.aircraft.departure is not None)
        strip.operation_area = "35"
        strip.aircraft.departure.align_runway_heading(facility.location)
        self.assertEqual(
            app.menu_entries("runways"),
            (
                "(*) Parallel 03L / 03R", "( ) Parallel 21L / 21R",
                "( ) Other 08", "( ) Other 17", "( ) Other 26", "(*) Other 35",
            ),
        )
        for index, runway in ((2, "08"), (3, "17"), (4, "26"), (5, "35")):
            with self.subTest(runway=runway):
                app.select_yuma_runways(index)
                self.assertEqual(facility.active_runways, ("03L", "03R", runway))
                self.assertEqual(strip.operation_area, runway)
                self.assertAlmostEqual(
                    strip.aircraft.heading,
                    facility.location.magnetic_to_true(int(runway) * 10),
                )
                self.assertTrue(app.menu_entries("runways")[index].startswith("(*)"))
                self.assertEqual(
                    sum(entry.startswith("(*)") for entry in app.menu_entries("runways")),
                    2,
                )
        app.select_yuma_runways(2)
        app.select_yuma_runways(1)
        self.assertEqual(facility.active_runways, ("21R", "21L", "08"))
        self.assertEqual(strip.operation_area, "08")
        self.assertEqual(app.strip_panel.active_runways, facility.active_runways)

    def test_other_runway_change_waits_for_affected_takeoff(self):
        app = make_application()
        _, facility, strips = create_yuma_scenario()
        app.scenario_loaded = True
        app.atc_facility = facility
        app.strip_panel = SimpleNamespace(
            strips=strips, active_runways=facility.active_runways
        )
        strip = next(item for item in strips if item.aircraft.departure is not None)
        strip.operation_area = "35"
        strip.aircraft.departure.state = "takeoff"
        app.select_yuma_runways(2)
        self.assertEqual(facility.active_runways, ("03L", "03R", "35"))
        self.assertEqual(strip.operation_area, "35")
        self.assertIn("Wait", app.menu_message)

    def test_other_runway_change_does_not_block_pad_or_parallel_takeoffs(self):
        app = make_application()
        _, facility, strips = create_yuma_scenario()
        app.scenario_loaded = True
        app.atc_facility = facility
        app.strip_panel = SimpleNamespace(
            strips=strips, active_runways=facility.active_runways
        )
        departures = [s for s in strips if s.aircraft.departure is not None]
        departures[0].operation_area = "P1"
        departures[0].aircraft.departure.state = "takeoff"
        departures[1].operation_area = "03L"
        departures[1].aircraft.departure.state = "takeoff"
        app.select_yuma_runways(2)
        self.assertEqual(facility.active_runways, ("03L", "03R", "08"))
        self.assertEqual(departures[0].operation_area, "P1")
        self.assertEqual(departures[1].operation_area, "03L")

    def test_runway_menu_mouse_selection_and_radio_indicators(self):
        app = make_application()
        _, facility, strips = create_yuma_scenario()
        app.scenario_loaded = True
        app.atc_facility = facility
        app.strip_panel = SimpleNamespace(
            strips=strips, active_runways=facility.active_runways
        )
        app.menu_text = Mock()
        options_x = 2 * MENU_WIDTH + 10
        submenu_x = 2 * MENU_WIDTH + MENU_ITEM_WIDTH + 10
        app.on_mouse_press(options_x, MENU_BOTTOM + 5, arcade.MOUSE_BUTTON_LEFT, 0)
        app.on_mouse_press(
            options_x, MENU_BOTTOM - 3 * ITEM_HEIGHT - 5, arcade.MOUSE_BUTTON_LEFT, 0
        )
        self.assertEqual(app.submenu_option, "runways")
        with (
            patch("simulator.app.application.arcade.draw_rect_filled"),
            patch("simulator.app.application.arcade.draw_rect_outline"),
            patch("simulator.app.application.arcade.draw_circle_outline") as circle,
            patch("simulator.app.application.arcade.draw_circle_filled") as selected,
        ):
            app.draw_menu(
                submenu_x - 10, MENU_BOTTOM - 3 * ITEM_HEIGHT,
                app.menu_entries("runways"), "option",
            )
        self.assertEqual(circle.call_count, 6)
        self.assertEqual(selected.call_count, 2)
        app.on_mouse_press(
            submenu_x, MENU_BOTTOM - 3 * ITEM_HEIGHT - 4 * ITEM_HEIGHT - 5,
            arcade.MOUSE_BUTTON_LEFT, 0,
        )
        self.assertEqual(facility.active_runways, ("03L", "03R", "26"))
        self.assertIsNone(app.open_menu)

    def test_active_runways_are_visible_in_top_bar(self):
        app = make_application()
        _, facility, strips = create_yuma_scenario()
        app.scenario_loaded = True
        app.atc_facility = facility
        app.strip_panel = SimpleNamespace(
            strips=strips, active_runways=facility.active_runways
        )
        app.menu_message = "Wait for the departure to become airborne"
        app.select_yuma_runways(1)
        app.menu_text = Mock()
        drawn = []
        app.menu_text.draw.side_effect = lambda: drawn.append(app.menu_text.text)
        with (
            patch.object(RadarDisplay, "on_draw"),
            patch("simulator.app.application.arcade.draw_rect_filled"),
        ):
            app.on_draw()
        self.assertIn("Yuma (KNYL) | RWY 21R/21L/35", drawn)
        self.assertEqual(app.menu_message, "")
        self.assertFalse(any(text.startswith("ACTIVE RUNWAYS:") for text in drawn))

    def test_options_submenu_escape_closes_menu(self):
        app = make_application()
        app.on_mouse_press(
            2 * MENU_WIDTH + 10, MENU_BOTTOM + 5, arcade.MOUSE_BUTTON_LEFT, 0
        )
        app.on_mouse_motion(2 * MENU_WIDTH + 10, MENU_BOTTOM - 5, 0, 0)
        app.on_key_press(arcade.key.ESCAPE, 0)
        self.assertIsNone(app.open_menu)
        self.assertIsNone(app.submenu_option)


if __name__ == "__main__":
    unittest.main()
