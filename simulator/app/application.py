"""Application menu and scenario lifecycle."""

import logging
import math
import queue
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass

import arcade

from Locations.Yuma.Scenarios.yuma import create_yuma_scenario
from simulator.app.menu_theme import system_theme
from simulator.core.aircraft import AircraftList
from simulator.core.atc import ATCFacility, FlightStrip
from simulator.core.constants import SCREEN_HEIGHT, SCREEN_TITLE, SCREEN_WIDTH
from simulator.display.flight_strips import PANEL_WIDTH, FlightStripPanel
from simulator.display.gis_overlays import LAYERS, GISOverlays
from simulator.display.radar import (
    RadarDisplay,
    RadarReturnManager,
    RadarSweep,
    RadarViewport,
)
from simulator.radio.communications import (
    COMMUNICATIONS_HEIGHT,
    CommunicationsPanel,
    RadioState,
)

MENU_HEIGHT = 28
MENU_BOTTOM = SCREEN_HEIGHT + COMMUNICATIONS_HEIGHT
MENU_WIDTH = 150
ITEM_HEIGHT = 32
MENU_ITEM_WIDTH = 220
THEME_CHECK_INTERVAL = 5.0
MENU_THEMES = {
    "Dark": {
        "bar": (35, 40, 48),
        "menu": (47, 53, 62),
        "highlight": (73, 82, 95),
        "border": (120, 130, 145),
        "text": (255, 255, 255),
    },
    "Light": {
        "bar": (243, 243, 243),
        "menu": (255, 255, 255),
        "highlight": (215, 230, 250),
        "border": (150, 150, 150),
        "text": (25, 25, 25),
    },
}
YUMA_ACTIVE_RADIOS = frozenset(
    {
        "approach_low",
        "approach_high",
        "departure_low",
        "departure_high",
        "enroute_low",
        "enroute_high",
    }
)


@dataclass(frozen=True)
class ScenarioChoice:
    label: str
    create: Callable[[], tuple[AircraftList, ATCFacility, list[FlightStrip]]]
    active_radios: frozenset[str] = frozenset()


@dataclass(frozen=True)
class SectorChoice:
    label: str
    scenarios: tuple[ScenarioChoice, ...]


@dataclass(frozen=True)
class LocationChoice:
    label: str
    facility_code: str
    scenarios: tuple[ScenarioChoice, ...] = ()
    sectors: tuple[SectorChoice, ...] = ()


LOCATIONS = (
    LocationChoice(
        "Yuma (KNYL)",
        "KNYL",
        scenarios=(
            ScenarioChoice(
                "Load Yuma", lambda: create_yuma_scenario(), YUMA_ACTIVE_RADIOS
            ),
        ),
    ),
    LocationChoice(
        "Cascade Approach",
        "KMFR",
        sectors=(SectorChoice("Medford", ()),),
    ),
)
MENU_NAMES = ("location", "scenario", "options")
OPTION_MENUS = ("audio", "display")


class ApplicationWindow(RadarDisplay):
    def __init__(self):
        super().__init__(AircraftList(), None)
        self.set_size(SCREEN_WIDTH + PANEL_WIDTH, MENU_BOTTOM + MENU_HEIGHT)
        width, height = SCREEN_WIDTH + PANEL_WIDTH, MENU_BOTTOM + MENU_HEIGHT
        self.ui_camera = arcade.Camera2D(
            viewport=arcade.LBWH(0, 0, width, height),
            position=(width / 2, height / 2),
            projection=arcade.LRBT(-width / 2, width / 2, -height / 2, height / 2),
            window=self,
        )
        self._scaled_ui_camera = self.ui_camera
        self.on_resize(self.width, self.height)
        self.scenario_loaded = False
        self.map_preview = False
        self.selected_location = None
        self.selected_sector = None
        self.pending_scenario = None
        self.pending_location = None
        self.open_menu = None
        self.submenu_location = None
        self.submenu_option = None
        self.menu_hover = None
        self.confirm_replace = False
        self.menu_message = ""
        self.menu_theme = "Dark"
        self.theme_error = None
        self.theme_check_elapsed = THEME_CHECK_INTERVAL
        self.theme_check_pending = False
        self.theme_results = queue.Queue()
        self.menu_text = arcade.Text(
            "", 0, 0, arcade.color.WHITE, 11, font_name="Consolas"
        )
        self.startup_text = arcade.Text(
            "",
            40,
            SCREEN_HEIGHT - 50,
            arcade.color.WHITE,
            16,
            multiline=True,
            width=SCREEN_WIDTH - 80,
            anchor_y="top",
            font_name="Consolas",
        )

    def on_resize(self, width, height):
        if self.__dict__.get("_scaled_ui_camera") is None or width <= 0 or height <= 0:
            return
        logical_width = SCREEN_WIDTH + PANEL_WIDTH
        logical_height = MENU_BOTTOM + MENU_HEIGHT
        scale = min(width / logical_width, height / logical_height)
        viewport_width = max(1, round(logical_width * scale))
        viewport_height = max(1, round(logical_height * scale))
        self.ui_offset_x = (width - viewport_width) // 2
        self.ui_offset_y = (height - viewport_height) // 2
        self.ui_scale_x = viewport_width / logical_width
        self.ui_scale_y = viewport_height / logical_height
        self.ui_scale = min(self.ui_scale_x, self.ui_scale_y)
        self.ui_camera.viewport = arcade.LBWH(
            self.ui_offset_x, self.ui_offset_y, viewport_width, viewport_height
        )
        self.map_camera.viewport = arcade.LBWH(
            self.ui_offset_x,
            self.ui_offset_y,
            round(SCREEN_WIDTH * self.ui_scale_x),
            round(SCREEN_HEIGHT * self.ui_scale_y),
        )

    def logical_mouse_position(self, x, y):
        return (
            (x - self.ui_offset_x) / self.ui_scale_x,
            (y - self.ui_offset_y) / self.ui_scale_y,
        )

    def loading_message(self):
        overlays = self.gis_overlays
        if overlays is not None:
            states = [overlays.status[i] for i in overlays.visible]
            failed = [
                LAYERS[i][0]
                for i in sorted(overlays.visible)
                if overlays.status[i] == "error"
            ]
            if failed:
                return "MAP ERROR: " + ", ".join(failed) + " (Scenario > Retry maps)"
            if any(state != "ready" for state in states):
                return f"LOADING MAPS: {states.count('ready')}/{len(states)}"
        if self.voice_audio is not None and not self.voice_audio.ready:
            if self.communications_panel.voice_status == "VOICE ERROR":
                return "VOICE ERROR: " + self.voice_message
            return "LOADING VOICE"
        return ""

    def enable_voice(self):
        self.menu_message = ""
        super().enable_voice()

    def disable_voice(self):
        if self.voice_audio is None:
            return
        self.communications_panel.release_all()
        self.voice_audio.close()
        self.voice_audio = None
        self.voice_message = ""
        self.communications_panel.pilot_channel = None
        self.communications_panel.voice_status = None
        self.set_caption(SCREEN_TITLE)

    def retry_maps(self):
        if self.gis_overlays is None:
            return
        for index in sorted(self.gis_overlays.visible):
            if self.gis_overlays.status[index] == "error":
                self.gis_overlays.toggle(index)
                self.gis_overlays.toggle(index)
        self.menu_message = ""

    def available_scenarios(self):
        if self.selected_location is None:
            return ()
        if self.selected_location.sectors:
            if self.selected_sector is None:
                return ()
            return self.selected_sector.scenarios
        return self.selected_location.scenarios

    def select_location(self, location, sector=None):
        if sector is not None and sector not in location.sectors:
            raise ValueError("Sector does not belong to this location")
        if len(location.sectors) > 1 and sector is None:
            raise ValueError("Select a sector for this location")
        selected_sector = sector or (location.sectors[0] if location.sectors else None)
        if (
            location == self.selected_location
            and selected_sector == self.selected_sector
        ):
            return
        if self.scenario_loaded:
            self.pending_location = (location, selected_sector)
            self.confirm_replace = True
            return
        self.activate_location(location, selected_sector)

    def activate_location(self, location, sector):
        facility = ATCFacility.get_atc_facility_by_name(location.facility_code)
        if facility is None:
            self.menu_message = (
                f"LOCATION ERROR: {location.facility_code} is not configured"
            )
            logging.getLogger(__name__).error(self.menu_message)
            return
        new_overlays = None
        try:
            aircraft = AircraftList()
            strip_panel = FlightStripPanel(
                [],
                aircraft,
                facility.airport_code,
                facility.active_runways,
                facility.helicopter_pads,
            )
            communications = CommunicationsPanel(
                facility.location.radio_frequencies,
                facility.location.coordination_lines,
            )
            new_overlays = GISOverlays(
                facility.location.latitude, facility.location.longitude
            )
            if self.gis_overlays is not None:
                for index in new_overlays.visible ^ self.gis_overlays.visible:
                    new_overlays.toggle(index)
            communications.voice_status = self.communications_panel.voice_status
            self.communications_panel.release_all()
            if self.voice_audio is not None:
                self.voice_audio.discard_transmissions()
                if (
                    self.voice_audio.ready
                    and communications.voice_status != "VOICE ERROR"
                ):
                    communications.voice_status = "VOICE READY"
        except (OSError, ValueError, RuntimeError) as error:
            if new_overlays is not None:
                new_overlays.close()
            logging.getLogger(__name__).exception(
                "Failed to load location %s", location.label
            )
            self.menu_message = f"LOCATION ERROR: {error}"
            return

        if self.gis_overlays is not None:
            self.gis_overlays.close()
        self.gis_overlays = new_overlays
        self.communications_panel = communications
        self.radar_viewport = RadarViewport()
        self.install_traffic(aircraft, facility, strip_panel)
        self.scenario_loaded = False
        self.map_preview = True
        self.selected_location = location
        self.selected_sector = sector
        self.pending_scenario = None
        self.menu_message = self.loading_message()

    def request_scenario(self, scenario):
        if scenario not in self.available_scenarios():
            raise ValueError("Scenario is not available for the selected location")
        self.menu_message = self.loading_message()
        if self.menu_message:
            return
        self.pending_scenario = scenario
        if self.scenario_loaded:
            self.confirm_replace = True
        else:
            self.load_scenario()

    def load_scenario(self):
        self.confirm_replace = False
        scenario = self.pending_scenario
        if scenario is None or scenario not in self.available_scenarios():
            raise ValueError("No available scenario has been selected")
        self.menu_message = self.loading_message()
        if self.menu_message:
            return
        try:
            aircraft, facility, strips = scenario.create()
            if (facility.location.latitude, facility.location.longitude) != (
                self.atc_facility.location.latitude,
                self.atc_facility.location.longitude,
            ):
                raise ValueError("Scenario location does not match the loaded map")
            panel = FlightStripPanel(
                strips,
                aircraft,
                facility.airport_code,
                facility.active_runways,
                facility.helicopter_pads,
            )
        except Exception as error:
            logging.getLogger(__name__).exception("Failed to load Yuma scenario")
            self.menu_message = f"SCENARIO ERROR: {error}"
            return

        self.communications_panel.release_all()
        if self.voice_audio is not None:
            self.voice_audio.discard_transmissions()
            self.communications_panel.pilot_channel = None
            self.communications_panel.voice_status = "VOICE READY"
        for channel in self.communications_panel.channels:
            if channel.identifier in scenario.active_radios:
                channel.state = RadioState.ON
        self.voice_message = ""
        self.set_caption(SCREEN_TITLE)
        self.install_traffic(aircraft, facility, panel)
        self.scenario_loaded = True
        self.pending_scenario = None
        self.menu_message = ""

    def install_traffic(self, aircraft, facility, panel):
        self.aircraft_list = aircraft
        self.atc_facility = facility
        self.strip_panel = panel
        self.sweep = RadarSweep()
        self.radar_return_manager = RadarReturnManager()
        self.secondary_update_elapsed = 0.0
        self.emergency_flash_elapsed = 0.0
        self.secondary_radar_returns = []
        self.departure_checkins = []
        self.reported_departures = set()
        self.selected_aircraft_id = None
        self.scratchpad_edit_id = None
        self.scratchpad_edit_text = ""
        self.scratchpad_edit_error = ""
        self.handoff_choice_id = None
        self.handoff_choice_kind = "HANDOFF"
        self.coordination_draft = None
        self.clearance_draft = None
        self.handoff_message = ""
        self.data_block_directions = {}
        self.data_block_labels = {}
        self.secondary_return_layouts = []
        self.data_block_overlap_warned = False
        self.capture_secondary_radar_returns()

    def on_update(self, delta_time):
        self.update_menu_theme(delta_time)
        if self.scenario_loaded or self.map_preview:
            super().on_update(delta_time)
        else:
            if self.gis_overlays is not None:
                self.gis_overlays.update()
            if self.voice_audio is not None:
                self.process_voice()
        if self.menu_message.startswith(("LOADING ", "MAP ERROR:", "VOICE ERROR:")):
            self.menu_message = self.loading_message()

    def update_menu_theme(self, delta_time):
        try:
            theme, error = self.theme_results.get_nowait()
        except queue.Empty:
            pass
        else:
            self.theme_check_pending = False
            if error is not None:
                if error != self.theme_error:
                    logging.getLogger(__name__).warning(
                        "Could not detect system appearance; retaining %s menu: %s",
                        self.menu_theme,
                        error,
                    )
                self.theme_error = error
            else:
                self.menu_theme = theme
                self.theme_error = None

        self.theme_check_elapsed += delta_time
        if (
            self.theme_check_elapsed >= THEME_CHECK_INTERVAL
            and not self.theme_check_pending
        ):
            self.theme_check_elapsed = 0
            self.theme_check_pending = True
            threading.Thread(
                target=self._detect_menu_theme,
                args=(self.theme_results,),
                daemon=True,
            ).start()

    @staticmethod
    def _detect_menu_theme(results):
        try:
            theme = system_theme()
        except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
            results.put((None, str(error)))
        else:
            results.put((theme, None))

    def _draw_text(self, text, x, y, anchor_x="left"):
        self.menu_text.text = text
        self.menu_text.x = x
        self.menu_text.y = y
        self.menu_text.anchor_x = anchor_x
        self.menu_text.color = MENU_THEMES[self.menu_theme]["text"]
        self.menu_text.draw()

    def menu_entries(self, name):
        if name == "location":
            return tuple(
                ("* " if location == self.selected_location else "  ")
                + location.label
                + ("  >" if len(location.sectors) > 1 else "")
                for location in LOCATIONS
            )
        if name == "scenario":
            if self.selected_location is None:
                return ("Select a location first",)
            scenarios = self.available_scenarios()
            return (
                tuple(scenario.label for scenario in scenarios)
                + (() if scenarios else ("No scenarios available",))
                + ("Retry failed maps",)
            )
        if name == "audio":
            return (
                "Disable voice" if self.voice_audio is not None else "Enable voice",
            )
        if name == "options":
            return ("Audio  >", "Display  >")
        if name == "display":
            return (
                ("* " if self.display_type == self.ARTS_IIE else "  ") + "ARTS IIE",
                "  FDAD (unavailable)",
                "  ACD (unavailable)",
            )
        raise ValueError(f"Unknown menu: {name}")

    @staticmethod
    def menu_index(top, y):
        return math.ceil((top - y) / ITEM_HEIGHT) - 1

    def draw_menu(self, x, top, entries, hover_kind):
        colors = MENU_THEMES[self.menu_theme]
        height = len(entries) * ITEM_HEIGHT
        bounds = arcade.LBWH(x, top - height, MENU_ITEM_WIDTH, height)
        arcade.draw_rect_filled(bounds, colors["menu"])
        arcade.draw_rect_outline(bounds, colors["border"], 1)
        for index, label in enumerate(entries):
            y = top - (index + 1) * ITEM_HEIGHT
            if self.menu_hover == (hover_kind, index):
                arcade.draw_rect_filled(
                    arcade.LBWH(x + 1, y + 1, MENU_ITEM_WIDTH - 2, ITEM_HEIGHT - 2),
                    colors["highlight"],
                )
            self._draw_text(label, x + 10, y + 9)

    def on_draw(self):
        if self.scenario_loaded or self.map_preview:
            super().on_draw()
        else:
            self.clear()
            self.ui_camera.use()
            status = self.menu_message or self.loading_message() or "READY"
            self.startup_text.text = (
                "ATC SIMULATOR\n\n"
                "Use Options > Audio to enable voice if desired.\n"
                "Choose a location from the menu to begin.\n\n" + status
            )
            self.startup_text.draw()
        self.ui_camera.use()
        colors = MENU_THEMES[self.menu_theme]
        arcade.draw_rect_filled(
            arcade.LBWH(0, MENU_BOTTOM, SCREEN_WIDTH + PANEL_WIDTH, MENU_HEIGHT),
            colors["bar"],
        )
        for index, name in enumerate(MENU_NAMES):
            if self.open_menu == name or self.menu_hover == ("bar", name):
                arcade.draw_rect_filled(
                    arcade.LBWH(
                        index * MENU_WIDTH, MENU_BOTTOM, MENU_WIDTH, MENU_HEIGHT
                    ),
                    colors["highlight"],
                )
            self._draw_text(name.title(), index * MENU_WIDTH + 10, MENU_BOTTOM + 7)
        status = self.communications_panel.voice_status or "VOICE OFF"
        if status == "VOICE READY":
            status = "VOICE ON"
        location_label = (
            self.selected_location.label
            if self.selected_location is not None
            else "No location selected"
        )
        if self.selected_sector is not None:
            location_label += " / " + self.selected_sector.label
        self._draw_text(
            location_label, (SCREEN_WIDTH + PANEL_WIDTH) / 2, MENU_BOTTOM + 7, "center"
        )
        self._draw_text(
            status, SCREEN_WIDTH + PANEL_WIDTH - 10, MENU_BOTTOM + 7, "right"
        )
        if self.menu_message:
            arcade.draw_rect_filled(
                arcade.LBWH(0, SCREEN_HEIGHT - 27, SCREEN_WIDTH + PANEL_WIDTH, 27),
                colors["menu"],
            )
            self._draw_text(self.menu_message, 10, SCREEN_HEIGHT - 20)
        if self.open_menu:
            x = MENU_NAMES.index(self.open_menu) * MENU_WIDTH
            self.draw_menu(x, MENU_BOTTOM, self.menu_entries(self.open_menu), "item")
            if self.open_menu == "location" and self.submenu_location is not None:
                location = LOCATIONS[self.submenu_location]
                self.draw_menu(
                    MENU_ITEM_WIDTH,
                    MENU_BOTTOM - self.submenu_location * ITEM_HEIGHT,
                    tuple(
                        (
                            "* "
                            if location == self.selected_location
                            and sector == self.selected_sector
                            else "  "
                        )
                        + sector.label
                        for sector in location.sectors
                    ),
                    "sector",
                )
            elif self.open_menu == "options" and self.submenu_option is not None:
                index = OPTION_MENUS.index(self.submenu_option)
                self.draw_menu(
                    x + MENU_ITEM_WIDTH,
                    MENU_BOTTOM - index * ITEM_HEIGHT,
                    self.menu_entries(self.submenu_option),
                    "option",
                )
        if self.confirm_replace:
            x, y = 360, 440
            arcade.draw_rect_filled(arcade.LBWH(x, y, 500, 100), colors["menu"])
            arcade.draw_rect_outline(arcade.LBWH(x, y, 500, 100), colors["border"], 1)
            message = (
                "End scenario and switch location?"
                if self.pending_location is not None
                else "Replace the current scenario?"
            )
            self._draw_text(message, x + 20, y + 68)
            self._draw_text("YES [Y]", x + 35, y + 25)
            self._draw_text("NO [N / ESC]", x + 270, y + 25)

    def on_mouse_press(self, x, y, button, modifiers):
        x, y = self.logical_mouse_position(x, y)
        if button != arcade.MOUSE_BUTTON_LEFT:
            return
        if not (
            0 <= x < SCREEN_WIDTH + PANEL_WIDTH and 0 <= y < MENU_BOTTOM + MENU_HEIGHT
        ):
            return
        self.menu_hover = None
        if self.confirm_replace:
            if 460 <= y <= 490:
                if 380 <= x <= 550:
                    self.confirm_action()
                elif 620 <= x <= 840:
                    self.cancel_confirmation()
            return
        if MENU_BOTTOM <= y < MENU_BOTTOM + MENU_HEIGHT:
            index = int(x // MENU_WIDTH)
            name = MENU_NAMES[index] if 0 <= index < len(MENU_NAMES) else None
            self.open_menu = None if self.open_menu == name else name
            self.submenu_location = None
            self.submenu_option = None
            return
        if self.open_menu:
            name = self.open_menu
            if name == "location" and self.submenu_location is not None:
                location = LOCATIONS[self.submenu_location]
                top = MENU_BOTTOM - self.submenu_location * ITEM_HEIGHT
                if (
                    MENU_ITEM_WIDTH <= x < 2 * MENU_ITEM_WIDTH
                    and top - len(location.sectors) * ITEM_HEIGHT <= y < top
                ):
                    index = self.menu_index(top, y)
                    self.select_location(location, location.sectors[index])
                    self.open_menu = None
                    self.submenu_location = None
                    return
            if name == "options" and self.submenu_option is not None:
                option = self.submenu_option
                left = MENU_NAMES.index(name) * MENU_WIDTH + MENU_ITEM_WIDTH
                top = MENU_BOTTOM - OPTION_MENUS.index(option) * ITEM_HEIGHT
                entries = self.menu_entries(option)
                if (
                    left <= x < left + MENU_ITEM_WIDTH
                    and top - len(entries) * ITEM_HEIGHT <= y < top
                ):
                    index = self.menu_index(top, y)
                    if option == "audio":
                        if self.voice_audio is None:
                            self.enable_voice()
                        else:
                            self.disable_voice()
                    elif index == 0:
                        self.display_type = self.ARTS_IIE
                        if self.menu_message in (
                            "FDAD radar scope is not available yet",
                            "ACD radar scope is not available yet",
                        ):
                            self.menu_message = ""
                    else:
                        scope = ("FDAD", "ACD")[index - 1]
                        self.menu_message = f"{scope} radar scope is not available yet"
                    self.open_menu = None
                    self.submenu_option = None
                    return
            left = MENU_NAMES.index(name) * MENU_WIDTH
            entries = self.menu_entries(name)
            if (
                left <= x < left + MENU_ITEM_WIDTH
                and MENU_BOTTOM - len(entries) * ITEM_HEIGHT <= y < MENU_BOTTOM
            ):
                index = self.menu_index(MENU_BOTTOM, y)
                if name == "location":
                    location = LOCATIONS[index]
                    if len(location.sectors) > 1:
                        self.submenu_location = index
                        return
                    self.select_location(location)
                elif name == "scenario":
                    scenarios = self.available_scenarios()
                    if index < len(scenarios):
                        self.request_scenario(scenarios[index])
                    elif self.gis_overlays is not None and index == len(entries) - 1:
                        self.retry_maps()
                elif name == "options":
                    self.submenu_option = OPTION_MENUS[index]
                    return
            self.open_menu = None
            self.submenu_location = None
            self.submenu_option = None
            return
        if self.scenario_loaded or self.map_preview:
            super().on_mouse_press(x, y, button, modifiers)

    def on_mouse_motion(self, x, y, dx, dy):
        x, y = self.logical_mouse_position(x, y)
        dx, dy = dx / self.ui_scale_x, dy / self.ui_scale_y
        self.menu_hover = None
        if not self.confirm_replace:
            if MENU_BOTTOM <= y < MENU_BOTTOM + MENU_HEIGHT:
                index = int(x // MENU_WIDTH)
                if 0 <= index < len(MENU_NAMES):
                    self.menu_hover = ("bar", MENU_NAMES[index])
            elif self.open_menu:
                left = MENU_NAMES.index(self.open_menu) * MENU_WIDTH
                count = len(self.menu_entries(self.open_menu))
                if self.open_menu == "location" and self.submenu_location is not None:
                    location = LOCATIONS[self.submenu_location]
                    top = MENU_BOTTOM - self.submenu_location * ITEM_HEIGHT
                    if (
                        MENU_ITEM_WIDTH <= x < 2 * MENU_ITEM_WIDTH
                        and top - len(location.sectors) * ITEM_HEIGHT <= y < top
                    ):
                        index = self.menu_index(top, y)
                        self.menu_hover = ("sector", index)
                elif self.open_menu == "options" and self.submenu_option is not None:
                    submenu_left = left + MENU_ITEM_WIDTH
                    top = (
                        MENU_BOTTOM
                        - OPTION_MENUS.index(self.submenu_option) * ITEM_HEIGHT
                    )
                    submenu_count = len(self.menu_entries(self.submenu_option))
                    if (
                        submenu_left <= x < submenu_left + MENU_ITEM_WIDTH
                        and top - submenu_count * ITEM_HEIGHT <= y < top
                    ):
                        self.menu_hover = ("option", self.menu_index(top, y))
                if (
                    left <= x < left + MENU_ITEM_WIDTH
                    and MENU_BOTTOM - count * ITEM_HEIGHT <= y < MENU_BOTTOM
                ):
                    index = self.menu_index(MENU_BOTTOM, y)
                    self.menu_hover = ("item", index)
                    if self.open_menu == "location":
                        self.submenu_location = (
                            index if len(LOCATIONS[index].sectors) > 1 else None
                        )
                    elif self.open_menu == "options":
                        self.submenu_option = OPTION_MENUS[index]
        if self.scenario_loaded or self.map_preview:
            super().on_mouse_motion(x, y, dx, dy)

    def on_mouse_leave(self, x, y):
        self.menu_hover = None
        super().on_mouse_leave(x, y)

    def on_key_press(self, symbol, modifiers):
        if self.confirm_replace:
            if symbol == arcade.key.Y:
                self.confirm_action()
            elif symbol in (arcade.key.N, arcade.key.ESCAPE):
                self.cancel_confirmation()
            return
        if self.open_menu:
            if symbol == arcade.key.ESCAPE:
                self.open_menu = None
                self.submenu_location = None
                self.submenu_option = None
            return
        if self.scenario_loaded or self.map_preview:
            super().on_key_press(symbol, modifiers)

    def confirm_action(self):
        if self.pending_location is not None:
            location, sector = self.pending_location
            self.pending_location = None
            self.confirm_replace = False
            self.activate_location(location, sector)
        else:
            self.load_scenario()

    def cancel_confirmation(self):
        self.confirm_replace = False
        self.pending_scenario = None
        self.pending_location = None

    def on_mouse_scroll(self, x, y, scroll_x, scroll_y):
        x, y = self.logical_mouse_position(x, y)
        if not (
            0 <= x < SCREEN_WIDTH + PANEL_WIDTH and 0 <= y < MENU_BOTTOM + MENU_HEIGHT
        ):
            return
        if (self.scenario_loaded or self.map_preview) and not (
            self.open_menu or self.confirm_replace
        ):
            super().on_mouse_scroll(x, y, scroll_x, scroll_y)

    def on_mouse_drag(self, x, y, dx, dy, buttons, modifiers):
        x, y = self.logical_mouse_position(x, y)
        dx, dy = dx / self.ui_scale_x, dy / self.ui_scale_y
        if (self.scenario_loaded or self.map_preview) and not (
            self.open_menu or self.confirm_replace
        ):
            super().on_mouse_drag(x, y, dx, dy, buttons, modifiers)

    def on_mouse_release(self, x, y, button, modifiers):
        x, y = self.logical_mouse_position(x, y)
        super().on_mouse_release(x, y, button, modifiers)
