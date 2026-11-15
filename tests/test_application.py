import queue
import runpy
import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import arcade

from Locations.Yuma.Scenarios.yuma import create_yuma_scenario
from simulator.app.application import (
    ITEM_HEIGHT,
    LOCATIONS,
    MENU_BOTTOM,
    MENU_ITEM_WIDTH,
    MENU_THEMES,
    MENU_WIDTH,
    THEME_CHECK_INTERVAL,
    ApplicationWindow,
    LocationChoice,
    ScenarioChoice,
    SectorChoice,
)
from simulator.app.menu_theme import system_theme
from simulator.core.atc import ATCFacility
from simulator.radio.communications import CommunicationsPanel, RadioState


def make_application():
    app = ApplicationWindow.__new__(ApplicationWindow)
    app.scenario_loaded = False
    app.selected_location = LOCATIONS[0]
    app.selected_sector = None
    app.pending_scenario = None
    app.open_menu = None
    app.submenu_location = None
    app.menu_hover = None
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
    with patch("simulator.radio.communications.arcade.Text"):
        app.communications_panel = CommunicationsPanel()
    app.atc_facility = ATCFacility.get_atc_facility_by_name("KNYL")
    app.set_caption = Mock()
    return app


class ApplicationTests(unittest.TestCase):
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
            patch("simulator.app.application.create_yuma_scenario") as scenario,
            patch("arcade.run") as run,
        ):
            runpy.run_path("main.py", run_name="__main__")
        window.return_value.setup.assert_called_once()
        window.return_value.enable_voice.assert_not_called()
        scenario.assert_not_called()
        run.assert_called_once()

    def test_default_location_and_filtered_scenarios(self):
        app = make_application()
        self.assertEqual(app.selected_location.label, "Yuma (KNYL)")
        self.assertEqual(app.menu_entries("scenario")[0], "Load Yuma")
        app.on_mouse_press(10, MENU_BOTTOM + 5, arcade.MOUSE_BUTTON_LEFT, 0)
        app.on_mouse_press(10, MENU_BOTTOM - 5, arcade.MOUSE_BUTTON_LEFT, 0)
        self.assertIs(app.selected_location, LOCATIONS[0])

    def test_sector_submenu_selects_sector_and_filters_scenarios(self):
        app = make_application()
        north = ScenarioChoice("North scenario", Mock())
        south = ScenarioChoice("South scenario", Mock(side_effect=create_yuma_scenario))
        facility = LocationChoice(
            "Test facility",
            sectors=(
                SectorChoice("North", (north,)),
                SectorChoice("South", (south,)),
            ),
        )
        with patch("simulator.app.application.LOCATIONS", (LOCATIONS[0], facility)):
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
        app.select_location(LocationChoice("Empty facility"))
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

    def test_scenario_waits_for_maps_and_enabled_voice(self):
        app = make_application()
        app.gis_overlays.status[0] = "loading"
        with patch("simulator.app.application.create_yuma_scenario") as create:
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
        app.voice_audio = Mock(ready=True)
        with patch("simulator.app.application.FlightStripPanel") as panel:
            app.on_mouse_press(
                MENU_WIDTH + 10, MENU_BOTTOM + 5, arcade.MOUSE_BUTTON_LEFT, 0
            )
            app.on_mouse_press(
                MENU_WIDTH + 10, MENU_BOTTOM - 5, arcade.MOUSE_BUTTON_LEFT, 0
            )
            self.assertTrue(app.scenario_loaded)
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
        app.enable_voice.assert_called_once()
        app.voice_audio = Mock()
        app.on_mouse_press(
            2 * MENU_WIDTH + 10, MENU_BOTTOM + 5, arcade.MOUSE_BUTTON_LEFT, 0
        )
        app.on_mouse_press(
            2 * MENU_WIDTH + 10, MENU_BOTTOM - 5, arcade.MOUSE_BUTTON_LEFT, 0
        )
        app.disable_voice.assert_called_once()
        app.on_mouse_press(
            MENU_WIDTH + 10, MENU_BOTTOM + 5, arcade.MOUSE_BUTTON_LEFT, 0
        )
        app.on_mouse_press(
            MENU_WIDTH + 10, MENU_BOTTOM - ITEM_HEIGHT - 5, arcade.MOUSE_BUTTON_LEFT, 0
        )
        self.assertEqual(app.gis_overlays.toggle.call_count, 2)


if __name__ == "__main__":
    unittest.main()
