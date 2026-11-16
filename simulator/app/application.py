"""Application menu and scenario lifecycle."""

import logging
import math
import queue
import subprocess
import textwrap
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import arcade

from Locations.Yuma.Scenarios.generator import generate_yuma_scenario
from simulator.app.briefing import briefing_pages
from simulator.app.menu_theme import system_theme
from simulator.app.scenario_generator import (
    DIALOG_HEIGHT,
    DIALOG_WIDTH,
    DIALOG_X,
    DIALOG_Y,
    MINUS_X,
    PLUS_X,
    ROW_HEIGHT,
    ROW_TOP,
    ScenarioGeneratorDialog,
)
from simulator.app.scenario_saves import (
    SAVE_HEIGHT,
    SAVE_PAGE_SIZE,
    SAVE_ROW_HEIGHT,
    SAVE_ROW_TOP,
    SAVE_WIDTH,
    SAVE_X,
    SAVE_Y,
    ScenarioSavesDialog,
)
from simulator.app.scenario_storage import (
    read_scenario,
    scenario_path,
    snapshot_scenario,
    write_scenario,
)
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
        self.pending_generated_settings = None
        self.generator_settings = None
        self.generator_dialog = None
        self.saves_dialog = None
        self.pending_saved_scenario = None
        self.scenario_utc = None
        self.briefing = []
        self.briefing_page = 0
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

    @staticmethod
    def utc_now():
        return datetime.now(UTC)

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
                facility.location.interfacility_lines,
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
        self.briefing = []
        self.selected_location = location
        self.selected_sector = sector
        self.pending_scenario = None
        self.pending_generated_settings = None
        self.generator_settings = None
        self.generator_dialog = None
        self.saves_dialog = None
        self.pending_saved_scenario = None
        self.scenario_utc = None
        self.menu_message = self.loading_message()

    def request_scenario(self, scenario):
        if scenario not in self.available_scenarios():
            raise ValueError("Scenario is not available for the selected location")
        self.menu_message = self.loading_message()
        if self.menu_message:
            return
        self.pending_scenario = scenario
        self.pending_generated_settings = None
        self.pending_saved_scenario = None
        if self.scenario_loaded:
            self.confirm_replace = True
        else:
            self.load_scenario()

    def open_generator(self):
        if self.selected_location != LOCATIONS[0]:
            raise ValueError("The scenario generator is only available for Yuma")
        self.menu_message = self.loading_message()
        if self.menu_message:
            return
        self.communications_panel.release_all()
        if self.voice_audio is not None:
            self.voice_audio.discard_transmissions()
        self.generator_dialog = ScenarioGeneratorDialog()

    def request_generated_scenario(self):
        dialog = self.generator_dialog
        if dialog is None or self.selected_location != LOCATIONS[0]:
            raise ValueError("No Yuma generator is open")
        try:
            settings = dialog.settings()
        except ValueError as error:
            dialog.error = str(error)
            return
        self.pending_scenario = None
        self.pending_saved_scenario = None
        self.pending_generated_settings = settings
        if self.scenario_loaded:
            self.confirm_replace = True
        else:
            self.load_scenario()

    def open_saves(self, mode):
        if self.selected_location != LOCATIONS[0]:
            raise ValueError("Saved scenarios are only available for Yuma")
        self.menu_message = self.loading_message() if mode == "load" else ""
        if self.menu_message:
            return
        if mode == "save":
            if not self.scenario_loaded:
                self.menu_message = "No running scenario to save"
                return
            panel = self.strip_panel
            if (
                panel.edit_strip is not None
                or panel.drag_strip is not None
                or self.scratchpad_edit_id is not None
                or self.clearance_draft is not None
                or self.coordination_draft is not None
                or self.handoff_choice_id is not None
            ):
                self.menu_message = "Finish editing or coordination before saving"
                return
        try:
            dialog = ScenarioSavesDialog(mode)
        except OSError as error:
            logging.getLogger(__name__).exception("Failed to list saved scenarios")
            self.menu_message = f"SCENARIO ERROR: {error}"
            return
        self.communications_panel.release_all()
        if self.voice_audio is not None:
            self.voice_audio.discard_transmissions()
        self.saves_dialog = dialog

    def save_current_scenario(self, overwrite=False):
        dialog = self.saves_dialog
        if dialog is None or dialog.mode != "save":
            raise ValueError("No save dialog is open")
        try:
            name = dialog.selected_name()
            if scenario_path(name).exists() and not overwrite:
                dialog.confirm_overwrite = True
                return
            snapshot = snapshot_scenario(
                self.aircraft_list,
                self.atc_facility,
                self.strip_panel.strips,
                self.scenario_utc,
                self.generator_settings,
                self.communications_panel,
                self.departure_checkins,
                self.reported_departures,
            )
            write_scenario(name, snapshot, overwrite=overwrite)
        except (OSError, ValueError, TypeError) as error:
            logging.getLogger(__name__).warning("Could not save scenario: %s", error)
            dialog.error = str(error)
            dialog.confirm_overwrite = False
            return
        self.saves_dialog = None
        self.menu_message = f"SCENARIO SAVED: {name}"

    def request_saved_scenario(self):
        dialog = self.saves_dialog
        if dialog is None or dialog.mode != "load":
            raise ValueError("No load dialog is open")
        try:
            saved = read_scenario(dialog.selected_name())
        except (OSError, ValueError, TypeError, KeyError) as error:
            logging.getLogger(__name__).warning("Could not load scenario: %s", error)
            dialog.error = str(error)
            return
        self.pending_scenario = None
        self.pending_generated_settings = None
        self.pending_saved_scenario = saved
        if self.scenario_loaded:
            self.confirm_replace = True
        else:
            self.load_saved_scenario()

    def load_saved_scenario(self):
        saved = self.pending_saved_scenario
        if saved is None or self.selected_location != LOCATIONS[0]:
            raise ValueError("No saved Yuma scenario has been selected")
        self.confirm_replace = False
        self.menu_message = self.loading_message()
        if self.menu_message:
            if self.saves_dialog is not None:
                self.saves_dialog.error = self.menu_message
            return
        try:
            panel = FlightStripPanel(
                saved.strips,
                saved.aircraft,
                saved.facility.airport_code,
                saved.facility.active_runways,
                saved.facility.helicopter_pads,
            )
        except (OSError, ValueError, RuntimeError) as error:
            logging.getLogger(__name__).exception("Failed to load saved scenario")
            if self.saves_dialog is not None:
                self.saves_dialog.error = str(error)
            return
        self.communications_panel.release_all()
        if self.voice_audio is not None:
            self.voice_audio.discard_transmissions()
            self.communications_panel.pilot_channel = None
            if self.voice_audio.ready:
                self.communications_panel.voice_status = "VOICE READY"
        self.voice_message = ""
        self.set_caption(SCREEN_TITLE)
        for channel in self.communications_panel.channels:
            channel.state = saved.radios[channel.identifier]
        for line in (
            self.communications_panel.lines
            + self.communications_panel.interfacility_lines
        ):
            line.hot = saved.lines[line.identifier]
        self.install_traffic(saved.aircraft, saved.facility, panel)
        self.departure_checkins = saved.checkins
        self.reported_departures = saved.reported_departures
        self.scenario_utc = saved.time
        self.generator_settings = saved.settings
        self.scenario_loaded = True
        self.pending_saved_scenario = None
        self.saves_dialog = None
        self.menu_message = ""
        self.briefing = briefing_pages(
            saved.facility, saved.strips, self.communications_panel
        )
        self.briefing[0].insert(1, f"Scenario time: {saved.time:%Y-%m-%d %H:%M:%S} UTC")
        self.briefing_page = 0

    def load_scenario(self):
        self.confirm_replace = False
        scenario = self.pending_scenario
        generated = self.__dict__.get("pending_generated_settings")
        dialog = self.generator_dialog
        if generated is not None and dialog is None:
            raise ValueError("No Yuma generator is open")
        if generated is not None and self.selected_location != LOCATIONS[0]:
            raise ValueError("The scenario generator is only available for Yuma")
        if generated is None and (
            scenario is None or scenario not in self.available_scenarios()
        ):
            raise ValueError("No available scenario has been selected")
        self.menu_message = self.loading_message()
        if self.menu_message:
            if generated is not None and dialog is not None:
                dialog.error = self.menu_message
            return
        try:
            warnings = []
            start_time = self.utc_now()
            if generated is not None:
                aircraft, facility, strips, warnings = generate_yuma_scenario(
                    generated, start_time
                )
                active_radios = YUMA_ACTIVE_RADIOS
            else:
                if scenario is None:
                    raise ValueError("No available scenario has been selected")
                aircraft, facility, strips = scenario.create()
                active_radios = scenario.active_radios
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
            logging.getLogger(__name__).exception("Failed to load scenario")
            self.menu_message = f"SCENARIO ERROR: {error}"
            if generated is not None and dialog is not None:
                dialog.error = self.menu_message
            return

        self.communications_panel.release_all()
        if self.voice_audio is not None:
            self.voice_audio.discard_transmissions()
            self.communications_panel.pilot_channel = None
            self.communications_panel.voice_status = "VOICE READY"
        for channel in self.communications_panel.channels:
            if channel.identifier in active_radios:
                channel.state = RadioState.ON
        self.voice_message = ""
        self.set_caption(SCREEN_TITLE)
        self.install_traffic(aircraft, facility, panel)
        self.scenario_loaded = True
        self.pending_scenario = None
        self.pending_generated_settings = None
        self.generator_settings = generated
        self.generator_dialog = None
        self.scenario_utc = start_time
        self.menu_message = ""
        self.briefing = briefing_pages(facility, strips, self.communications_panel)
        self.briefing[0].insert(1, f"Scenario time: {start_time:%Y-%m-%d %H:%M:%S} UTC")
        if warnings:
            warning_lines = [
                line for warning in warnings for line in textwrap.wrap(warning, 130)
            ]
            self.briefing.insert(0, ["Traffic generation limitations:", *warning_lines])
        self.briefing_page = 0

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
        self.handoff_sector_text = ""
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
        if (
            self.__dict__.get("briefing")
            or self.__dict__.get("generator_dialog")
            or self.__dict__.get("saves_dialog")
        ):
            if self.gis_overlays is not None:
                self.gis_overlays.update()
            return
        if self.scenario_loaded or self.map_preview:
            super().on_update(delta_time)
            scenario_time = self.__dict__.get("scenario_utc")
            if self.scenario_loaded and scenario_time is not None:
                self.scenario_utc = scenario_time + timedelta(seconds=delta_time)
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
            yuma = self.selected_location == LOCATIONS[0]
            return (
                tuple(scenario.label for scenario in scenarios)
                + (() if scenarios or yuma else ("No scenarios available",))
                + (
                    ("Generate Yuma...", "Load saved scenario...", "Save scenario...")
                    if yuma
                    else ()
                )
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
        current_time = self.__dict__.get("scenario_utc") or self.utc_now()
        self._draw_text(
            current_time.strftime("UTC %m-%d %H:%M:%S"),
            SCREEN_WIDTH + PANEL_WIDTH - 150,
            MENU_BOTTOM + 7,
            "right",
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
        if self.__dict__.get("generator_dialog"):
            self.draw_generator()
        if self.__dict__.get("saves_dialog"):
            self.draw_saves()
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
        if self.__dict__.get("briefing"):
            self.draw_briefing()

    def draw_generator(self):
        dialog = self.generator_dialog
        if dialog is None:
            raise ValueError("No scenario generator is open")
        colors = MENU_THEMES[self.menu_theme]
        arcade.draw_rect_filled(
            arcade.LBWH(DIALOG_X, DIALOG_Y, DIALOG_WIDTH, DIALOG_HEIGHT), colors["menu"]
        )
        arcade.draw_rect_outline(
            arcade.LBWH(DIALOG_X, DIALOG_Y, DIALOG_WIDTH, DIALOG_HEIGHT),
            colors["border"],
            1,
        )
        self._draw_text(
            "YUMA SCENARIO GENERATOR", DIALOG_X + 25, DIALOG_Y + DIALOG_HEIGHT - 30
        )
        self._draw_text(
            "Select a row; use +/- or arrow keys. Weights of 0 disable a category.",
            DIALOG_X + 25,
            DIALOG_Y + DIALOG_HEIGHT - 57,
        )
        for index, (label, value) in enumerate(dialog.rows()):
            center = ROW_TOP - index * ROW_HEIGHT
            if index == dialog.selected:
                arcade.draw_rect_filled(
                    arcade.LBWH(DIALOG_X + 20, center - 17, DIALOG_WIDTH - 40, 35),
                    colors["highlight"],
                )
            self._draw_text(label, DIALOG_X + 35, center - 5)
            self._draw_text(value, (MINUS_X + PLUS_X) / 2, center - 5, "center")
            if index:
                self._draw_text("[-]", MINUS_X, center - 5, "center")
                self._draw_text("[+]", PLUS_X, center - 5, "center")
        self._draw_text(
            "Seed: select row and type digits; R selects a new seed.",
            DIALOG_X + 25,
            DIALOG_Y + 85,
        )
        if dialog.error:
            self._draw_text(dialog.error, DIALOG_X + 25, DIALOG_Y + 60)
        self._draw_text("CANCEL [ESC]", DIALOG_X + 25, DIALOG_Y + 25)
        self._draw_text(
            "GENERATE [ENTER]", DIALOG_X + DIALOG_WIDTH - 25, DIALOG_Y + 25, "right"
        )

    def draw_saves(self):
        dialog = self.saves_dialog
        if dialog is None:
            raise ValueError("No save dialog is open")
        colors = MENU_THEMES[self.menu_theme]
        bounds = arcade.LBWH(SAVE_X, SAVE_Y, SAVE_WIDTH, SAVE_HEIGHT)
        arcade.draw_rect_filled(bounds, colors["menu"])
        arcade.draw_rect_outline(bounds, colors["border"], 1)
        title = "SAVE SCENARIO" if dialog.mode == "save" else "LOAD SAVED SCENARIO"
        self._draw_text(title, SAVE_X + 25, SAVE_Y + SAVE_HEIGHT - 30)
        if dialog.mode == "save":
            self._draw_text(
                "Name (letters, digits, spaces, - and _):",
                SAVE_X + 25,
                SAVE_ROW_TOP + 35,
            )
            self._draw_text(dialog.name + "_", SAVE_X + 25, SAVE_ROW_TOP)
        else:
            self._draw_text(
                "Select a scenario; use arrow keys to browse.",
                SAVE_X + 25,
                SAVE_ROW_TOP + 35,
            )
            if not dialog.names:
                self._draw_text("No saved scenarios", SAVE_X + 25, SAVE_ROW_TOP)
            for index, name in enumerate(dialog.visible_names()):
                y = SAVE_ROW_TOP - index * SAVE_ROW_HEIGHT
                absolute = dialog.selected // SAVE_PAGE_SIZE * SAVE_PAGE_SIZE + index
                if absolute == dialog.selected:
                    arcade.draw_rect_filled(
                        arcade.LBWH(SAVE_X + 20, y - 10, SAVE_WIDTH - 40, 27),
                        colors["highlight"],
                    )
                self._draw_text(name, SAVE_X + 30, y)
            page = dialog.selected // SAVE_PAGE_SIZE + 1
            pages = max(1, (len(dialog.names) + SAVE_PAGE_SIZE - 1) // SAVE_PAGE_SIZE)
            self._draw_text(
                f"Page {page}/{pages} [LEFT/RIGHT]", SAVE_X + 25, SAVE_Y + 115
            )
        if dialog.confirm_overwrite:
            self._draw_text("Overwrite existing scenario?", SAVE_X + 25, SAVE_Y + 85)
            self._draw_text("YES [Y]", SAVE_X + 250, SAVE_Y + 85)
            self._draw_text("NO [N]", SAVE_X + 400, SAVE_Y + 85)
        if dialog.error:
            self._draw_text(dialog.error, SAVE_X + 25, SAVE_Y + 60)
        self._draw_text("CANCEL [ESC]", SAVE_X + 25, SAVE_Y + 25)
        action = "SAVE [ENTER]" if dialog.mode == "save" else "LOAD [ENTER]"
        self._draw_text(action, SAVE_X + SAVE_WIDTH - 25, SAVE_Y + 25, "right")

    def draw_briefing(self):
        colors = MENU_THEMES[self.menu_theme]
        x, y = 90, 130
        width, height = SCREEN_WIDTH + PANEL_WIDTH - 180, 680
        arcade.draw_rect_filled(arcade.LBWH(x, y, width, height), colors["menu"])
        arcade.draw_rect_outline(arcade.LBWH(x, y, width, height), colors["border"], 1)
        self._draw_text("CONTROLLER HANDOFF - SCENARIO PAUSED", x + 20, y + height - 35)
        self._draw_text(
            f"Page {self.briefing_page + 1} of {len(self.briefing)}",
            x + width - 25,
            y + height - 35,
            "right",
        )
        for index, line in enumerate(self.briefing[self.briefing_page]):
            self._draw_text(line, x + 25, y + height - 75 - index * 22)
        self._draw_text("PREVIOUS [LEFT]", x + 25, y + 28)
        self._draw_text("NEXT [RIGHT]", x + 250, y + 28)
        self._draw_text("ACKNOWLEDGE / START [ENTER]", x + width - 25, y + 28, "right")

    def briefing_key(self, symbol):
        if symbol == arcade.key.LEFT:
            self.briefing_page = max(0, self.briefing_page - 1)
        elif symbol == arcade.key.RIGHT:
            self.briefing_page = min(len(self.briefing) - 1, self.briefing_page + 1)
        elif symbol in (arcade.key.ENTER, arcade.key.RETURN):
            self.briefing = []

    def on_mouse_press(self, x, y, button, modifiers):
        x, y = self.logical_mouse_position(x, y)
        if button != arcade.MOUSE_BUTTON_LEFT:
            return
        if not (
            0 <= x < SCREEN_WIDTH + PANEL_WIDTH and 0 <= y < MENU_BOTTOM + MENU_HEIGHT
        ):
            return
        if self.__dict__.get("briefing"):
            if 150 <= y <= 190:
                if 110 <= x < 320:
                    self.briefing_key(arcade.key.LEFT)
                elif 320 <= x < 550:
                    self.briefing_key(arcade.key.RIGHT)
                elif 1000 <= x <= SCREEN_WIDTH + PANEL_WIDTH - 100:
                    self.briefing_key(arcade.key.ENTER)
            return
        self.menu_hover = None
        if self.confirm_replace:
            if 460 <= y <= 490:
                if 380 <= x <= 550:
                    self.confirm_action()
                elif 620 <= x <= 840:
                    self.cancel_confirmation()
            return
        dialog = self.generator_dialog
        if dialog is not None:
            if DIALOG_Y + 10 <= y <= DIALOG_Y + 45:
                if DIALOG_X + 10 <= x <= DIALOG_X + 220:
                    self.generator_dialog = None
                elif DIALOG_X + DIALOG_WIDTH - 250 <= x <= DIALOG_X + DIALOG_WIDTH - 10:
                    self.request_generated_scenario()
            else:
                dialog.click(x, y)
            return
        saves = self.saves_dialog
        if saves is not None:
            if saves.confirm_overwrite:
                if SAVE_Y + 70 <= y <= SAVE_Y + 105:
                    if SAVE_X + 230 <= x < SAVE_X + 360:
                        self.save_current_scenario(overwrite=True)
                    elif SAVE_X + 360 <= x <= SAVE_X + 500:
                        saves.confirm_overwrite = False
                return
            if SAVE_Y + 10 <= y <= SAVE_Y + 45:
                if SAVE_X + 10 <= x <= SAVE_X + 200:
                    self.saves_dialog = None
                elif SAVE_X + SAVE_WIDTH - 220 <= x <= SAVE_X + SAVE_WIDTH - 10:
                    if saves.mode == "save":
                        self.save_current_scenario()
                    else:
                        self.request_saved_scenario()
            else:
                saves.click(x, y)
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
                    elif self.selected_location == LOCATIONS[0] and index == len(
                        scenarios
                    ):
                        self.open_generator()
                    elif (
                        self.selected_location == LOCATIONS[0]
                        and index == len(scenarios) + 1
                    ):
                        self.open_saves("load")
                    elif (
                        self.selected_location == LOCATIONS[0]
                        and index == len(scenarios) + 2
                    ):
                        self.open_saves("save")
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
        dialog = self.generator_dialog
        if dialog is not None or self.__dict__.get("saves_dialog"):
            return
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
        if self.__dict__.get("briefing"):
            self.briefing_key(symbol)
            return
        if self.confirm_replace:
            if symbol == arcade.key.Y:
                self.confirm_action()
            elif symbol in (arcade.key.N, arcade.key.ESCAPE):
                self.cancel_confirmation()
            return
        dialog = self.generator_dialog
        if dialog is not None:
            if symbol == arcade.key.ESCAPE:
                self.generator_dialog = None
            elif symbol in (arcade.key.ENTER, arcade.key.NUM_ENTER):
                self.request_generated_scenario()
            else:
                dialog.key(symbol)
            return
        saves = self.saves_dialog
        if saves is not None:
            if saves.confirm_overwrite:
                if symbol == arcade.key.Y:
                    self.save_current_scenario(overwrite=True)
                elif symbol in (arcade.key.N, arcade.key.ESCAPE):
                    saves.confirm_overwrite = False
            elif symbol == arcade.key.ESCAPE:
                self.saves_dialog = None
            elif symbol in (arcade.key.ENTER, arcade.key.NUM_ENTER):
                if saves.mode == "save":
                    self.save_current_scenario()
                else:
                    self.request_saved_scenario()
            else:
                saves.key(symbol, modifiers)
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
        elif self.pending_saved_scenario is not None:
            self.load_saved_scenario()
        else:
            self.load_scenario()

    def cancel_confirmation(self):
        self.confirm_replace = False
        self.pending_scenario = None
        self.pending_location = None
        self.pending_generated_settings = None
        self.pending_saved_scenario = None

    def on_mouse_scroll(self, x, y, scroll_x, scroll_y):
        x, y = self.logical_mouse_position(x, y)
        if not (
            0 <= x < SCREEN_WIDTH + PANEL_WIDTH and 0 <= y < MENU_BOTTOM + MENU_HEIGHT
        ):
            return
        if (self.scenario_loaded or self.map_preview) and not (
            self.open_menu
            or self.confirm_replace
            or self.__dict__.get("briefing")
            or self.__dict__.get("generator_dialog")
            or self.__dict__.get("saves_dialog")
        ):
            super().on_mouse_scroll(x, y, scroll_x, scroll_y)

    def on_mouse_drag(self, x, y, dx, dy, buttons, modifiers):
        x, y = self.logical_mouse_position(x, y)
        dx, dy = dx / self.ui_scale_x, dy / self.ui_scale_y
        if (self.scenario_loaded or self.map_preview) and not (
            self.open_menu
            or self.confirm_replace
            or self.__dict__.get("briefing")
            or self.__dict__.get("generator_dialog")
            or self.__dict__.get("saves_dialog")
        ):
            super().on_mouse_drag(x, y, dx, dy, buttons, modifiers)

    def on_mouse_release(self, x, y, button, modifiers):
        if self.__dict__.get("generator_dialog") or self.__dict__.get("saves_dialog"):
            return
        x, y = self.logical_mouse_position(x, y)
        super().on_mouse_release(x, y, button, modifiers)
