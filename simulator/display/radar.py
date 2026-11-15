import logging
import math
import queue
from dataclasses import dataclass
from typing import NamedTuple

import arcade
import numpy as np

from simulator.core.atc import CoordinationKind, TrackingPosition
from simulator.core.clearances import (
    clearance_control_error,
    execute_clearance,
    is_airborne,
)
from simulator.core.constants import (
    DISPLAY_RADIUS,
    FPS,
    MAX_DISTANCE_MILES,
    PRIMARY_RETURN_LIFETIME_SECONDS,
    SCREEN_HEIGHT,
    SCREEN_TITLE,
    SCREEN_WIDTH,
    SECONDARY_RADAR_UPDATE_SECONDS,
    SWEEP_SPEED,
    SWEEP_TRAIL_DEGREES,
)
from simulator.display.flight_strips import (
    PANEL_WIDTH,
    FlightStripPanel,
    display_airport_identifier,
)
from simulator.display.gis_overlays import LAYER_KEYS, GISOverlays
from simulator.navigation.navmath import NavigationalCoordinateSystem
from simulator.radio.communications import COMMUNICATIONS_HEIGHT, CommunicationsPanel
from simulator.radio.voice_audio import VoiceAudio
from simulator.radio.voice_commands import handle_transmission

SWEEP_COLOR = arcade.color.ORANGE
DATA_BLOCK_DISTANCE = 40
MIN_LEADER_LINE_LENGTH = 12
DATA_BLOCK_WIDTH = 200
DATA_BLOCK_FONT = "Consolas"
DATA_BLOCK_FONT_SIZE = 11
EMERGENCY_FLASH_SECONDS = 1.0
SCRATCHPAD_MAX_LENGTH = 16
COORDINATION_MAX_LENGTH = 120
NUMPAD_DIRECTIONS = {
    arcade.key.NUM_1: (-1, -1),
    arcade.key.NUM_END: (-1, -1),
    arcade.key.NUM_2: (0, -1),
    arcade.key.NUM_DOWN: (0, -1),
    arcade.key.NUM_3: (1, -1),
    arcade.key.NUM_PAGE_DOWN: (1, -1),
    arcade.key.NUM_4: (-1, 0),
    arcade.key.NUM_LEFT: (-1, 0),
    arcade.key.NUM_6: (1, 0),
    arcade.key.NUM_RIGHT: (1, 0),
    arcade.key.NUM_7: (-1, 1),
    arcade.key.NUM_HOME: (-1, 1),
    arcade.key.NUM_8: (0, 1),
    arcade.key.NUM_UP: (0, 1),
    arcade.key.NUM_9: (1, 1),
    arcade.key.NUM_PAGE_UP: (1, 1),
}
DATA_BLOCK_DIRECTIONS = (
    (0, 1),
    (1, 1),
    (1, 0),
    (1, -1),
    (0, -1),
    (-1, -1),
    (-1, 0),
    (-1, 1),
)
PAN_DIRECTIONS = {
    arcade.key.LEFT: (-1, 0),
    arcade.key.RIGHT: (1, 0),
    arcade.key.UP: (0, 1),
    arcade.key.DOWN: (0, -1),
}


@dataclass
class CoordinationDraft:
    aircraft_id: str
    kind: str
    target: TrackingPosition | None = None
    stage: str = "details"
    text: str = ""


@dataclass
class ClearanceDraft:
    aircraft_id: str
    text: str = ""


def leader_line_end(x, y, text_x, text_y, width, height):
    dx, dy = text_x - x, text_y - y
    intersection = min(
        1.0,
        width / (2 * abs(dx)) if dx else 1.0,
        height / (2 * abs(dy)) if dy else 1.0,
    )
    return text_x - intersection * dx, text_y - intersection * dy


class RadarViewport:
    def __init__(self):
        self.zoom = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0

    def constrain_pan(self):
        maximum = DISPLAY_RADIUS * (1 - 1 / self.zoom)
        distance = np.hypot(self.pan_x, self.pan_y)
        if distance > maximum:
            self.pan_x *= maximum / distance
            self.pan_y *= maximum / distance

    def zoom_by(self, scroll):
        self.zoom = min(8.0, max(1.0, self.zoom * 1.1 ** max(-20, min(20, scroll))))
        self.constrain_pan()

    def pan(self, dx, dy):
        self.pan_x += dx * 20 / self.zoom
        self.pan_y += dy * 20 / self.zoom
        self.constrain_pan()

    def reset(self):
        self.zoom = 1.0
        self.pan_x = self.pan_y = 0.0

    def camera_position(self, center_x, center_y, radius):
        scale = radius / DISPLAY_RADIUS
        return center_x + self.pan_x * scale, center_y + self.pan_y * scale

    def transform(self, x, y, center_x, center_y, radius):
        camera_x, camera_y = self.camera_position(center_x, center_y, radius)
        return (
            center_x + (x - camera_x) * self.zoom,
            center_y + (y - camera_y) * self.zoom,
        )


class SecondaryRadarSnapshot(NamedTuple):
    latitude: float
    longitude: float
    callsign: str
    squawk: str
    heading: float
    altitude: float
    aircraft_type: str
    speed: float
    aircraft_id: str
    altitude_trend: int
    scratchpad: str
    tracking_owner: TrackingPosition
    handoff_target: TrackingPosition | None


class SecondaryReturnLayout(NamedTuple):
    snapshot: SecondaryRadarSnapshot
    distance: float
    x: float
    y: float
    text_x: float
    text_y: float
    width: float
    height: float


class DataBlockLabel(NamedTuple):
    text: str
    label: arcade.Text
    width: float
    height: float


class RadarSweep:
    """
    Manages the radar sweep animation and logic.
    """

    def __init__(self):
        self.angle = 0
        self.sweep_speed = SWEEP_SPEED

    def update(self, delta_time=1 / FPS):
        """
        Update the radar sweep angle.
        """
        self.angle = (self.angle + self.sweep_speed * delta_time * FPS) % (2 * np.pi)


class RadarReturnManager:
    """
    Manages the radar returns for aircraft.
    """

    def __init__(self):
        self.radar_returns = []

    def add_return(self, x, y):
        """
        Add a radar return at the specified coordinates.
        """
        self.radar_returns.append([x, y, 1.0])  # Add new return with full opacity

    def update(self, delta_time):
        """
        Update the opacity of radar returns, decreasing over time.
        """
        for radar_return in self.radar_returns:
            radar_return[2] -= delta_time / PRIMARY_RETURN_LIFETIME_SECONDS
        self.radar_returns = [
            r for r in self.radar_returns if r[2] > 0
        ]  # Keep returns with positive opacity

    def draw(self, transform=None):
        """
        Draw the radar returns.
        """
        for radar_return in self.radar_returns:
            x, y, opacity = radar_return
            if transform is not None:
                x, y = transform(x, y)
            arcade.draw_circle_filled(x, y, 2, (*SWEEP_COLOR[:3], int(255 * opacity)))


class PrimaryRadarReturn:
    """
    Handles the primary radar returns based on the radar sweep angle.
    """

    def __init__(
        self,
        radar_return_manager,
        bearing,
        distance,
        previous_sweep_angle,
        sweep_angle,
        center_x,
        center_y,
        display_radius,
    ):
        self.radar_return_manager = radar_return_manager
        self.bearing = bearing
        self.distance = distance
        self.previous_sweep_angle = previous_sweep_angle
        self.sweep_angle = sweep_angle
        self.center_x = center_x
        self.center_y = center_y
        self.display_radius = display_radius

    def add_return(self):
        """
        Add a radar return for the aircraft if it is within the sweep angle tolerance.
        """
        sweep_delta = (self.sweep_angle - self.previous_sweep_angle) % (2 * np.pi)
        bearing_delta = (self.bearing - self.previous_sweep_angle) % (2 * np.pi)
        if 0 < bearing_delta <= sweep_delta and self.distance <= MAX_DISTANCE_MILES:
            pixels_per_mile = self.display_radius / MAX_DISTANCE_MILES
            x = self.center_x + self.distance * pixels_per_mile * np.sin(self.bearing)
            y = self.center_y + self.distance * pixels_per_mile * np.cos(self.bearing)
            self.radar_return_manager.add_return(x, y)


class RadarDisplay(arcade.Window):
    """
    Manages the radar display, including sweep, returns, and overlays.
    """

    ARTS_IIE = "ARTS IIE"
    STARS = "STARS"

    def __init__(self, aircraft_list, atc_facility, flight_strips=None):
        super().__init__(
            SCREEN_WIDTH + PANEL_WIDTH,
            SCREEN_HEIGHT + COMMUNICATIONS_HEIGHT,
            SCREEN_TITLE,
        )
        arcade.set_background_color(arcade.color.BLACK)
        self.aircraft_list = aircraft_list
        self.atc_facility = atc_facility
        self.communications_panel = CommunicationsPanel(
            atc_facility.location.radio_frequencies
        )
        self.voice_audio = None
        self.voice_message = ""
        self.strip_panel = FlightStripPanel(
            flight_strips if flight_strips is not None else [],
            aircraft_list,
            atc_facility.airport_code,
            atc_facility.active_runways,
            atc_facility.helicopter_pads,
        )
        self.sweep = RadarSweep()
        self.radar_return_manager = RadarReturnManager()
        self.display_type = self.ARTS_IIE
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
        self.coordination_draft: CoordinationDraft | None = None
        self.clearance_draft: ClearanceDraft | None = None
        self.handoff_message = ""
        self.data_block_directions = {}
        self.data_block_labels = {}
        self.secondary_return_layouts = []
        self.data_block_overlap_warned = False
        self.capture_secondary_radar_returns()
        self.gis_overlays = GISOverlays(
            atc_facility.location.latitude, atc_facility.location.longitude
        )
        self.radar_viewport = RadarViewport()
        self.map_camera = arcade.Camera2D(
            viewport=arcade.LBWH(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT), window=self
        )
        self.scope_mask = self.create_scope_mask()
        self.sweep_sector = self.create_sweep_sector()
        self.selected_details_text = arcade.Text(
            "",
            SCREEN_WIDTH - 190,
            SCREEN_HEIGHT - 20,
            arcade.color.LIGHT_BLUE,
            11,
            anchor_y="top",
            multiline=True,
            width=180,
            font_name=DATA_BLOCK_FONT,
        )
        self.control_warning_text = arcade.Text(
            "",
            10,
            90,
            arcade.color.YELLOW,
            11,
            anchor_y="bottom",
            multiline=True,
            width=400,
            font_name=DATA_BLOCK_FONT,
        )

    def create_sweep_sector(self):
        vertices = []
        colors = []
        segments = 36
        rings = 4
        for segment in range(segments):
            angles = [
                np.radians(-SWEEP_TRAIL_DEGREES * (1 - index / segments))
                for index in (segment, segment + 1)
            ]
            edge_colors = [
                (*SWEEP_COLOR[:3], round(180 * index / segments))
                for index in (segment, segment + 1)
            ]
            for ring in range(rings):
                inner = DISPLAY_RADIUS * ring / rings
                outer = DISPLAY_RADIUS * (ring + 1) / rings
                points = [
                    (radius * np.sin(angle), radius * np.cos(angle))
                    for radius, angle in (
                        (inner, angles[0]),
                        (outer, angles[0]),
                        (outer, angles[1]),
                        (inner, angles[0]),
                        (outer, angles[1]),
                        (inner, angles[1]),
                    )
                ]
                vertices.extend(points)
                colors.extend(
                    (
                        edge_colors[0],
                        edge_colors[0],
                        edge_colors[1],
                        edge_colors[0],
                        edge_colors[1],
                        edge_colors[1],
                    )
                )
        shapes = arcade.shape_list.ShapeElementList()
        shapes.append(
            arcade.shape_list.create_triangles_filled_with_colors(vertices, colors)
        )
        shapes.position = SCREEN_WIDTH / 2, SCREEN_HEIGHT / 2
        return shapes

    def create_scope_mask(self):
        cx, cy, radius = SCREEN_WIDTH / 2, SCREEN_HEIGHT / 2, DISPLAY_RADIUS
        vertices = []

        def rectangle(left, bottom, right, top):
            vertices.extend(
                (
                    (left, bottom),
                    (right, bottom),
                    (right, top),
                    (left, bottom),
                    (right, top),
                    (left, top),
                )
            )

        rectangle(0, 0, cx - radius, SCREEN_HEIGHT)
        rectangle(cx + radius, 0, SCREEN_WIDTH, SCREEN_HEIGHT)
        rectangle(cx - radius, 0, cx + radius, cy - radius)
        rectangle(cx - radius, cy + radius, cx + radius, SCREEN_HEIGHT)
        for quadrant in range(4):
            angle = quadrant * np.pi / 2
            corner = (
                cx + radius * (1 if quadrant in (0, 3) else -1),
                cy + radius * (1 if quadrant in (0, 1) else -1),
            )
            for step in range(32):
                a = angle + step * np.pi / 64
                b = angle + (step + 1) * np.pi / 64
                vertices.extend(
                    (
                        corner,
                        (cx + radius * np.cos(a), cy + radius * np.sin(a)),
                        (cx + radius * np.cos(b), cy + radius * np.sin(b)),
                    )
                )
        shapes = arcade.shape_list.ShapeElementList()
        shapes.append(
            arcade.shape_list.create_triangles_filled_with_colors(
                vertices, [(0, 0, 0, 255)] * len(vertices)
            )
        )
        return shapes

    def transform_position(self, x, y):
        radius = (
            DISPLAY_RADIUS
            if self.display_type == self.ARTS_IIE
            else min(SCREEN_WIDTH, SCREEN_HEIGHT) / 2
        )
        return self.radar_viewport.transform(
            x, y, SCREEN_WIDTH / 2, SCREEN_HEIGHT / 2, radius
        )

    def is_visible_scope_position(self, x, y):
        if self.display_type == self.STARS:
            return 0 <= x <= SCREEN_WIDTH and 0 <= y <= SCREEN_HEIGHT
        return np.hypot(x - SCREEN_WIDTH / 2, y - SCREEN_HEIGHT / 2) <= DISPLAY_RADIUS

    def setup(self):
        """
        Set up the radar display.
        """

    def enable_voice(self):
        if self.voice_audio is not None:
            raise RuntimeError("Voice is already enabled")
        self.communications_panel.voice_status = "VOICE LOADING"
        self.voice_audio = VoiceAudio()

    def sync_voice(self):
        voice = self.__dict__.get("voice_audio")
        if voice is not None:
            panel = self.communications_panel
            voice.sync(
                panel.mic_hot,
                {channel.identifier for channel in panel.transmitting},
                {channel.identifier for channel in panel.monitored},
            )
            panel.pilot_channel = voice.playing_channel

    def process_voice(self):
        voice = self.voice_audio
        if voice is None:
            return
        RadarDisplay.sync_voice(self)
        while True:
            try:
                kind, item = voice.events.get_nowait()
            except queue.Empty:
                break
            if kind == "status":
                self.communications_panel.voice_status = item.upper()
                if not self.voice_message:
                    self.set_caption(f"{SCREEN_TITLE} - {item}")
            elif kind == "error":
                self.communications_panel.voice_status = "VOICE ERROR"
                self.voice_message = item
                self.set_caption(f"{SCREEN_TITLE} - {self.voice_message}")
                logging.getLogger(__name__).warning("%s", item)
            elif kind == "transcript":
                text, channels = item
                try:
                    reply = handle_transmission(
                        text,
                        self.aircraft_list.aircraft_list,
                        self.atc_facility,
                        channels,
                    )
                except ValueError as error:
                    self.communications_panel.voice_status = "VOICE ERROR"
                    self.voice_message = f"{text}: {error}"
                    self.set_caption(f"{SCREEN_TITLE} - {self.voice_message}")
                    logging.getLogger(__name__).warning(
                        "Voice instruction rejected: %s: %s", text, error
                    )
                else:
                    self.voice_message = f"{text} | {reply.text}"
                    self.set_caption(f"{SCREEN_TITLE} - {self.voice_message}")
                    voice.speak(reply)

    def on_draw(self):
        """
        Render the screen.
        """
        self.clear()
        self.gis_overlays.update()
        radius = (
            DISPLAY_RADIUS
            if self.display_type == self.ARTS_IIE
            else min(SCREEN_WIDTH, SCREEN_HEIGHT) / 2
        )
        self.map_camera.position = self.radar_viewport.camera_position(
            SCREEN_WIDTH / 2, SCREEN_HEIGHT / 2, radius
        )
        self.map_camera.zoom = self.radar_viewport.zoom
        self.map_camera.use()
        self.gis_overlays.draw_map(radius)
        self.default_camera.use()
        if self.display_type == self.ARTS_IIE:
            visible = self.is_visible_scope_position
        else:
            visible = lambda x, y: 0 <= x <= SCREEN_WIDTH and 0 <= y <= SCREEN_HEIGHT
        self.gis_overlays.draw_labels(
            radius,
            self.transform_position,
            visible,
            (
                self.radar_viewport.zoom,
                self.radar_viewport.pan_x,
                self.radar_viewport.pan_y,
            ),
        )
        if self.display_type == self.ARTS_IIE:
            self.draw_sweep()
            self.radar_return_manager.draw(self.transform_position)
            self.scope_mask.draw()
            self.draw_arts_iie()
        elif self.display_type == self.STARS:
            self.radar_return_manager.draw(self.transform_position)
            self.draw_stars()
        self.gis_overlays.draw_legend()

        self.secondary_return_layouts = self.layout_secondary_returns()
        for layout in self.secondary_return_layouts:
            self.draw_secondary_return(
                layout.snapshot,
                layout.x,
                layout.y,
                layout.distance,
                selected=layout.snapshot.aircraft_id == self.selected_aircraft_id,
                text_position=(layout.text_x, layout.text_y),
                text_size=(layout.width, layout.height),
                label=self.data_block_labels[layout.snapshot.aircraft_id].label,
            )
        self.draw_selected_aircraft_details()
        warning = RadarDisplay.control_limit_warning(self)
        if warning:
            self.control_warning_text.text = warning
            self.control_warning_text.draw()
        self.strip_panel.draw(self.selected_aircraft_id, self.departure_checkins)
        self.communications_panel.draw()

    def control_limit_warning(self):
        facility = self.atc_facility
        overdue = [
            aircraft.callsign
            for aircraft in self.aircraft_list.aircraft_list
            if aircraft.track.owner == TrackingPosition.YUMA
            and facility.above_control_limit(aircraft.altitude)
        ]
        if not overdue:
            return ""
        center = {
            TrackingPosition.LOS_ANGELES: "LA CENTER",
            TrackingPosition.ALBUQUERQUE: "ALBUQUERQUE CENTER",
        }[facility.upper_control_center]
        return (
            f"ABOVE FL{facility.upper_control_flight_level:03d} - "
            f"HAND OFF TO {center}: {', '.join(overdue)}"
        )

    def on_update(self, delta_time):
        """
        Advance the sweep, aircraft, and radar returns.
        """
        if self.__dict__.get("voice_audio") is not None:
            RadarDisplay.process_voice(self)
        previous_sweep_angle = self.sweep.angle
        self.sweep.update(delta_time)
        self.radar_return_manager.update(delta_time)
        self.emergency_flash_elapsed = (
            self.emergency_flash_elapsed + delta_time
        ) % EMERGENCY_FLASH_SECONDS

        checkins = []
        # Generate radar returns
        for aircraft in self.aircraft_list.aircraft_list:
            if not aircraft.landed:
                aircraft.update_position(delta_time)
            departure = getattr(aircraft, "departure", None)
            if (
                departure is not None
                and departure.check_in is not None
                and aircraft.id not in self.reported_departures
            ):
                checkins.append(
                    (departure.check_in_time, aircraft.id, departure.check_in)
                )
            if not is_airborne(aircraft):
                self.secondary_radar_returns = [
                    snapshot
                    for snapshot in self.secondary_radar_returns
                    if snapshot.aircraft_id != aircraft.id
                ]
            facility = self.atc_facility
            if (
                facility.above_control_limit(aircraft.altitude)
                and aircraft.track.owner == TrackingPosition.YUMA
                and aircraft.track.handoff_target is not None
                and aircraft.track.handoff_target != facility.upper_control_center
            ):
                aircraft.track.cancel()
                RadarDisplay.refresh_track_snapshot(self, aircraft)
                if self.selected_aircraft_id == aircraft.id:
                    self.handoff_message = (
                        f"ABOVE FL{facility.upper_control_flight_level:03d}: "
                        f"HANDOFF TO {facility.upper_control_center} REQUIRED"
                    )
            if aircraft.track.advance(delta_time):
                RadarDisplay.refresh_track_snapshot(self, aircraft)
                if self.selected_aircraft_id == aircraft.id:
                    self.handoff_message = (
                        f"RADAR CONTACT BY {aircraft.track.owner}; C TRANSFERS COMMS"
                    )
            coordination_approved = aircraft.track.advance_coordination(delta_time)
            if coordination_approved and self.selected_aircraft_id == aircraft.id:
                response = (
                    "TRAFFIC OBSERVED"
                    if aircraft.track.coordination.kind == CoordinationKind.TRAFFIC
                    else "POINT OUT APPROVED"
                )
                self.handoff_message = f"{response} (SIMULATED CENTER)"
            distance, bearing = self.calculate_range_and_bearing(
                aircraft.lat, aircraft.lon
            )
            aircraft.distance = distance
            if self.display_type == self.ARTS_IIE and is_airborne(aircraft):
                PrimaryRadarReturn(
                    self.radar_return_manager,
                    bearing,
                    distance,
                    previous_sweep_angle,
                    self.sweep.angle,
                    SCREEN_WIDTH / 2,
                    SCREEN_HEIGHT / 2,
                    DISPLAY_RADIUS,
                ).add_return()

        for _, aircraft_id, message in sorted(checkins):
            self.reported_departures.add(aircraft_id)
            self.departure_checkins.append(message)
        if checkins:
            self.departure_checkins = self.departure_checkins[-3:]
        self.secondary_update_elapsed += delta_time
        if self.secondary_update_elapsed >= SECONDARY_RADAR_UPDATE_SECONDS:
            self.secondary_update_elapsed %= SECONDARY_RADAR_UPDATE_SECONDS
            self.capture_secondary_radar_returns()

    def capture_secondary_radar_returns(self):
        previous_altitudes = {
            snapshot.aircraft_id: snapshot.altitude
            for snapshot in self.secondary_radar_returns
        }

        def altitude_trend(aircraft):
            previous = previous_altitudes.get(aircraft.id, aircraft.altitude)
            return int(aircraft.altitude > previous) - int(aircraft.altitude < previous)

        self.secondary_radar_returns = [
            SecondaryRadarSnapshot(
                aircraft.lat,
                aircraft.lon,
                aircraft.callsign,
                aircraft.squawk,
                aircraft.heading,
                aircraft.altitude,
                aircraft.aircraft_model.aircraft_type,
                aircraft.speed,
                aircraft.id,
                altitude_trend(aircraft),
                aircraft.scratchpad,
                aircraft.track.owner,
                aircraft.track.handoff_target,
            )
            for aircraft in self.aircraft_list.aircraft_list
            if is_airborne(aircraft)
        ]

    def refresh_track_snapshot(self, aircraft):
        self.secondary_radar_returns = [
            snapshot._replace(
                tracking_owner=aircraft.track.owner,
                handoff_target=aircraft.track.handoff_target,
            )
            if snapshot.aircraft_id == aircraft.id
            else snapshot
            for snapshot in self.secondary_radar_returns
        ]

    @staticmethod
    def secondary_return_layout(
        snapshot, x, y, distance, direction=None, emergency_visible=True
    ):
        if direction is None:
            heading = np.radians(snapshot.heading)
            dx, dy = -np.sin(heading), -np.cos(heading)
        else:
            length = np.hypot(*direction)
            dx, dy = direction[0] / length, direction[1] / length
        text_x = x + DATA_BLOCK_DISTANCE * dx
        text_y = y + DATA_BLOCK_DISTANCE * dy
        trend = (
            "+"
            if snapshot.altitude_trend > 0
            else "-"
            if snapshot.altitude_trend < 0
            else ""
        )
        altitude = f"{trend}{math.floor(snapshot.altitude + 0.5):03d}"
        speed = f"{math.floor(snapshot.speed / 10 + 0.5):02d}"
        emergency = " EM" if snapshot.squawk == "7700" and emergency_visible else ""
        position = snapshot.tracking_owner
        if snapshot.handoff_target is not None:
            position = f"{position}>{snapshot.handoff_target}"
        text = f"{snapshot.callsign} {position}{emergency}\n{altitude}  {speed}\n{snapshot.aircraft_type}\n{snapshot.scratchpad or ' '}"
        return text, text_x, text_y

    def get_data_block_label(self, snapshot, distance):
        text = self.secondary_return_layout(snapshot, 0, 0, distance)[0]
        hidden_text = self.secondary_return_layout(
            snapshot, 0, 0, distance, emergency_visible=False
        )[0]
        cached = self.data_block_labels.get(snapshot.aircraft_id)
        if cached is None or cached.text != text:
            label = arcade.Text(
                text,
                0,
                0,
                arcade.color.WHITE,
                DATA_BLOCK_FONT_SIZE,
                font_name=DATA_BLOCK_FONT,
                anchor_x="left",
                anchor_y="center",
                multiline=True,
                width=DATA_BLOCK_WIDTH,
                align="left",
            )
            width, height = label.content_width, label.content_height
            label.text = hidden_text
            cached = DataBlockLabel(
                text,
                label,
                max(width, label.content_width),
                max(height, label.content_height),
            )
            self.data_block_labels[snapshot.aircraft_id] = cached
        visible = self.emergency_flash_elapsed < EMERGENCY_FLASH_SECONDS / 2
        current_text = text if visible else hidden_text
        if cached.label.text != current_text:
            cached.label.text = current_text
        return cached

    def layout_secondary_returns(self):
        contacts = []
        active_ids = {snapshot.aircraft_id for snapshot in self.secondary_radar_returns}
        for aircraft_id in self.data_block_labels.keys() - active_ids:
            del self.data_block_labels[aircraft_id]
        for snapshot in self.secondary_radar_returns:
            distance, _ = self.calculate_range_and_bearing(
                snapshot.latitude, snapshot.longitude
            )
            if distance > MAX_DISTANCE_MILES:
                continue
            x, y = self.convert_to_display_coordinates(
                snapshot.latitude, snapshot.longitude
            )
            if not self.is_visible_scope_position(x, y):
                continue
            label = RadarDisplay.get_data_block_label(self, snapshot, distance)
            contacts.append((snapshot, distance, x, y, label.width, label.height))

        contacts.sort(
            key=lambda contact: (
                contact[0].aircraft_id not in self.data_block_directions,
                contact[0].aircraft_id != self.selected_aircraft_id,
            )
        )
        layouts = []
        placement_failed = False
        for snapshot, distance, x, y, width, height in contacts:
            scope_width = min(self.width, SCREEN_WIDTH)
            scope_height = min(self.height, SCREEN_HEIGHT)
            direction = self.data_block_directions.get(snapshot.aircraft_id)
            _, preferred_x, preferred_y = self.secondary_return_layout(
                snapshot, x, y, distance, direction
            )
            preferred_dx, preferred_dy = preferred_x - x, preferred_y - y
            directions = [(preferred_dx, preferred_dy), *DATA_BLOCK_DIRECTIONS]
            position = None

            def available(
                text_x,
                text_y,
                allow_overlap=False,
                width=width,
                height=height,
                scope_width=scope_width,
                scope_height=scope_height,
                x=x,
                y=y,
            ):
                end_x, end_y = leader_line_end(x, y, text_x, text_y, width, height)
                return (
                    width / 2 <= text_x <= scope_width - width / 2
                    and height / 2 <= text_y <= scope_height - height / 2
                    and np.hypot(end_x - x, end_y - y) >= MIN_LEADER_LINE_LENGTH - 1e-8
                    and (
                        allow_overlap
                        or not any(
                            abs(text_x - other.text_x) < (width + other.width) / 2 + 4
                            and abs(text_y - other.text_y)
                            < (height + other.height) / 2 + 4
                            for other in layouts
                        )
                    )
                )

            max_radius = np.hypot(scope_width, scope_height) + DATA_BLOCK_DISTANCE
            overlap_position = None
            for offset in range(0, int(max_radius) + 1, DATA_BLOCK_DISTANCE):
                for dx, dy in directions:
                    length = np.hypot(dx, dy)
                    unit_x, unit_y = dx / length, dy / length
                    edge_distance = min(
                        width / (2 * abs(unit_x)) if unit_x else math.inf,
                        height / (2 * abs(unit_y)) if unit_y else math.inf,
                    )
                    radius = (
                        max(DATA_BLOCK_DISTANCE, edge_distance + MIN_LEADER_LINE_LENGTH)
                        + offset
                    )
                    text_x, text_y = x + radius * unit_x, y + radius * unit_y
                    if overlap_position is None and available(text_x, text_y, True):
                        overlap_position = (text_x, text_y)
                    if not available(text_x, text_y):
                        continue
                    position = (text_x, text_y)
                    break
                if position is not None:
                    break
            if position is None:
                candidate_x = [width / 2, scope_width - width / 2]
                candidate_y = [height / 2, scope_height - height / 2]
                for other in layouts:
                    candidate_x.extend(
                        (
                            other.text_x - (width + other.width) / 2 - 4,
                            other.text_x + (width + other.width) / 2 + 4,
                        )
                    )
                    candidate_y.extend(
                        (
                            other.text_y - (height + other.height) / 2 - 4,
                            other.text_y + (height + other.height) / 2 + 4,
                        )
                    )
                candidates = [
                    (text_x, text_y)
                    for text_x in candidate_x
                    for text_y in candidate_y
                    if available(text_x, text_y)
                ]
                if candidates:
                    position = min(
                        candidates,
                        key=lambda candidate: np.hypot(
                            candidate[0] - preferred_x, candidate[1] - preferred_y
                        ),
                    )
            if position is None:
                placement_failed = True
                if overlap_position is not None:
                    position = overlap_position
                else:
                    position = (
                        min(max(preferred_x, width / 2), scope_width - width / 2),
                        min(max(preferred_y, height / 2), scope_height - height / 2),
                    )
            layouts.append(
                SecondaryReturnLayout(
                    snapshot, distance, x, y, *position, width, height
                )
            )

        if placement_failed and not self.data_block_overlap_warned:
            logging.getLogger(__name__).warning(
                "Unable to place all radar data blocks without overlap or preserve leader clearance."
            )
        self.data_block_overlap_warned = placement_failed
        return layouts

    @staticmethod
    def draw_secondary_return(
        snapshot,
        x,
        y,
        distance,
        direction=None,
        selected=False,
        text_position=None,
        text_size=None,
        label=None,
    ):
        text, text_x, text_y = RadarDisplay.secondary_return_layout(
            snapshot,
            x,
            y,
            distance,
            direction,
        )
        if text_position is not None:
            text_x, text_y = text_position
        if text_size is None:
            label = arcade.Text(
                text,
                0,
                0,
                arcade.color.WHITE,
                DATA_BLOCK_FONT_SIZE,
                font_name=DATA_BLOCK_FONT,
                anchor_x="left",
                anchor_y="center",
                multiline=True,
                width=DATA_BLOCK_WIDTH,
                align="left",
            )
            text_size = (label.content_width, label.content_height)
        width, height = text_size
        arcade.draw_circle_filled(x, y, 3, arcade.color.LIGHT_BLUE)
        if selected:
            arcade.draw_circle_outline(x, y, 8, arcade.color.YELLOW, 2)
        end_x, end_y = leader_line_end(x, y, text_x, text_y, width, height)
        arcade.draw_line(
            x,
            y,
            end_x,
            end_y,
            arcade.color.WHITE,
            1,
        )
        if label is None:
            arcade.draw_text(
                text,
                text_x - width / 2,
                text_y,
                arcade.color.WHITE,
                DATA_BLOCK_FONT_SIZE,
                font_name=DATA_BLOCK_FONT,
                anchor_x="left",
                anchor_y="center",
                multiline=True,
                width=DATA_BLOCK_WIDTH,
                align="left",
            )
        else:
            label.position = (text_x - width / 2, text_y)
            label.draw()

    def draw_selected_aircraft_details(self):
        snapshot = next(
            (
                item
                for item in self.secondary_radar_returns
                if item.aircraft_id == self.selected_aircraft_id
            ),
            None,
        )
        if snapshot is None:
            if self.scratchpad_edit_id is not None and self.scratchpad_edit_error:
                self.selected_details_text.text = self.scratchpad_edit_error
                self.selected_details_text.draw()
            elif self.handoff_message:
                self.selected_details_text.text = self.handoff_message
                self.selected_details_text.draw()
            return
        distance, _ = self.calculate_range_and_bearing(
            snapshot.latitude, snapshot.longitude
        )
        text = (
            f"SELECTED {snapshot.callsign}\n"
            f"HDG {round(snapshot.heading) % 360:03d}\n"
            f"SQK {snapshot.squawk}\n"
            f"SPD {snapshot.speed:g} KT\n"
            f"RNG {distance:.1f} NM"
        )
        text += f"\nTRACK {snapshot.tracking_owner}"
        if snapshot.handoff_target is not None:
            text += f" TO {snapshot.handoff_target}"
            if snapshot.handoff_target == TrackingPosition.YUMA:
                text += "\nA ACCEPT / X REJECT"
        aircraft = next(
            (
                item
                for item in self.aircraft_list.aircraft_list
                if item.id == snapshot.aircraft_id
            ),
            None,
        )
        if aircraft is not None:
            track = aircraft.track
            text += f"\nCOMMS {track.communications_owner}"
            if self.__dict__.get("voice_audio") is not None:
                channel = next(
                    (
                        channel
                        for channel in self.communications_panel.channels
                        if channel.identifier == aircraft.radio_channel
                    ),
                    None,
                )
                if channel is not None:
                    text += f"\nRADIO {channel.frequency} {channel.band}"
            guidance = getattr(aircraft, "flight_guidance", None)
            if guidance is not None:
                if guidance.vector_heading is not None:
                    heading = guidance.vector_heading or 360
                    text += f"\nVECTOR {heading:03d} TRUE"
                else:
                    text += f"\nNEXT {guidance.route[guidance.next_index].name}"
                if guidance.assigned_altitude is not None:
                    text += f"\nCLEARED {guidance.assigned_altitude} FT"
            if track.owner != track.communications_owner:
                text += "\nC TRANSFER COMMS"
            if track.handoff_information:
                text += f"\nHANDOFF INFO: {track.handoff_information}"
            if track.identification_confirmation_due:
                text += "\nCONFIRM INCOMING ID: V"
            if track.coordination is not None:
                item = track.coordination
                status = (
                    "OBSERVED"
                    if item.approved and item.kind == CoordinationKind.TRAFFIC
                    else "APPROVED"
                    if item.approved
                    else "PENDING"
                )
                text += (
                    f"\n{item.kind} {item.source}>{item.target} {status}"
                    f"\nINFO: {item.information}"
                )
                if item.approved:
                    text += "\nD CLOSE"
                elif item.target == TrackingPosition.YUMA:
                    text += "\nA ACCEPT / X REJECT"
                else:
                    text += "\nX CANCEL"
        draft = self.coordination_draft
        clearance = self.__dict__.get("clearance_draft")
        if clearance is not None and clearance.aircraft_id == snapshot.aircraft_id:
            text += f"\nCLEARANCE:\n{clearance.text}_\nENTER SEND / ESC CANCEL"
            if self.handoff_message:
                text += f"\n{self.handoff_message}"
        elif self.scratchpad_edit_id == snapshot.aircraft_id:
            text += f"\nEDIT SCRATCHPAD:\n{self.scratchpad_edit_text}_\nENTER SAVE / ESC CANCEL"
            if self.scratchpad_edit_error:
                text += f"\n{self.scratchpad_edit_error}"
        elif self.handoff_choice_id == snapshot.aircraft_id:
            kind = self.__dict__.get("handoff_choice_kind", "HANDOFF")
            text += f"\n{kind}: L=LA / A=ABQ\nESC CANCEL"
            if self.handoff_message:
                text += f"\n{self.handoff_message}"
        elif draft is not None and draft.aircraft_id == snapshot.aircraft_id:
            if draft.stage == "details":
                label = (
                    "RESTRICTIONS / TRAFFIC"
                    if draft.kind == CoordinationKind.TRAFFIC
                    else "RESTRICTIONS / INFO OR NONE"
                )
                text += f"\n{draft.kind} {label}:\n{draft.text}_\nENTER / ESC"
            elif draft.stage == "offer":
                distance, bearing = self.calculate_range_and_bearing(
                    snapshot.latitude, snapshot.longitude
                )
                text += (
                    f"\n{draft.kind} {draft.target}\n"
                    f"POSITION {round(math.degrees(bearing)) % 360:03d}/"
                    f"{distance:.1f} NM FROM {display_airport_identifier(self.atc_facility.airport_code)}\n"
                    f"REPORTED ALT {snapshot.altitude * 100:g} FT\n"
                    f"INFO: {draft.text}\n"
                    "VERIFY ID AND COORDINATION\n"
                    "VERBAL IF REQUIRED\nY CONFIRM / ESC CANCEL"
                )
            elif draft.stage == "accept":
                text += "\nVERIFY TARGET AND RESTRICTIONS\nY ACCEPT / ESC CANCEL"
            elif draft.stage == "communications":
                text += (
                    "\nRESOLVE / COORDINATE CONFLICTS\n"
                    "Y CONFIRM COMMS TRANSFER\nESC CANCEL"
                )
            if self.handoff_message:
                text += f"\n{self.handoff_message}"
        elif self.handoff_message:
            text += f"\n{self.handoff_message}"
        if self.selected_details_text.text != text:
            self.selected_details_text.text = text
        self.selected_details_text.draw()

    def on_mouse_press(self, x, y, button, modifiers):
        if button != arcade.MOUSE_BUTTON_LEFT:
            return
        communications = self.__dict__.get("communications_panel")
        if communications is not None and communications.press(x, y):
            RadarDisplay.sync_voice(self)
            return
        self.scratchpad_edit_id = None
        self.handoff_choice_id = None
        self.coordination_draft = None
        self.clearance_draft = None
        self.handoff_message = ""
        panel = self.__dict__.get("strip_panel")
        if panel is not None:
            panel.cancel_edit()
            panel.cancel_drag()
            if x >= SCREEN_WIDTH:
                self.selected_aircraft_id = panel.select_at(y)
                panel.start_drag(x, y)
                return

        symbol_hits = [
            (np.hypot(x - layout.x, y - layout.y), layout.snapshot.aircraft_id)
            for layout in self.secondary_return_layouts
            if np.hypot(x - layout.x, y - layout.y) <= 10
        ]
        if symbol_hits:
            self.selected_aircraft_id = min(symbol_hits)[1]
            return

        block_hits = []
        for layout in self.secondary_return_layouts:
            if (
                abs(x - layout.text_x) <= layout.width / 2
                and abs(y - layout.text_y) <= layout.height / 2
            ):
                block_hits.append(
                    (
                        np.hypot(x - layout.text_x, y - layout.text_y),
                        layout.snapshot.aircraft_id,
                    )
                )
        self.selected_aircraft_id = min(block_hits)[1] if block_hits else None

    def handle_clearance_draft(self, symbol):
        draft = self.clearance_draft
        if draft is None:
            raise RuntimeError("No clearance draft is active")
        if symbol == arcade.key.ESCAPE:
            self.clearance_draft = None
            self.handoff_message = "CLEARANCE CANCELED"
            return
        if symbol == arcade.key.BACKSPACE:
            draft.text = draft.text[:-1]
            self.handoff_message = ""
            return
        if symbol not in (arcade.key.ENTER, arcade.key.NUM_ENTER):
            if arcade.key.A <= symbol <= arcade.key.Z:
                char = chr(symbol).upper()
            elif ord("0") <= symbol <= ord("9") or symbol == ord(" "):
                char = chr(symbol)
            elif arcade.key.NUM_0 <= symbol <= arcade.key.NUM_9:
                char = str(symbol - arcade.key.NUM_0)
            else:
                self.handoff_message = "USE A-Z, 0-9 OR SPACE"
                return
            if len(draft.text) >= 20:
                self.handoff_message = "MAX 20 CHARACTERS"
                return
            draft.text += char
            self.handoff_message = ""
            return
        aircraft = next(
            (
                item
                for item in self.aircraft_list.aircraft_list
                if item.id == draft.aircraft_id
            ),
            None,
        )
        if aircraft is None:
            self.clearance_draft = None
            self.handoff_message = "AIRCRAFT UNAVAILABLE"
            return
        try:
            readback = execute_clearance(aircraft, self.atc_facility, draft.text)
        except ValueError as error:
            self.handoff_message = str(error).upper()
            return
        self.clearance_draft = None
        self.handoff_message = f"{aircraft.callsign}: {readback}"

    def handle_coordination_draft(self, symbol):
        draft = self.coordination_draft
        if draft is None:
            raise RuntimeError("No coordination draft is active")
        if symbol == arcade.key.ESCAPE:
            self.coordination_draft = None
            self.handoff_message = "COORDINATION CANCELED"
            return
        if draft.stage == "details":
            if symbol in (arcade.key.ENTER, arcade.key.NUM_ENTER):
                if not draft.text.strip():
                    self.handoff_message = "ENTER INFORMATION OR NONE"
                elif (
                    draft.kind == CoordinationKind.TRAFFIC
                    and draft.text.strip().upper() == "NONE"
                ):
                    self.handoff_message = "TRAFFIC REQUIRES RESTRICTIONS"
                else:
                    draft.stage = "offer"
                    self.handoff_message = ""
            elif symbol == arcade.key.BACKSPACE:
                draft.text = draft.text[:-1]
                self.handoff_message = ""
            else:
                if arcade.key.A <= symbol <= arcade.key.Z:
                    char = chr(symbol).upper()
                elif ord("0") <= symbol <= ord("9") or symbol in (
                    ord(" "),
                    ord("-"),
                    ord("/"),
                    ord("."),
                ):
                    char = chr(symbol)
                elif arcade.key.NUM_0 <= symbol <= arcade.key.NUM_9:
                    char = str(symbol - arcade.key.NUM_0)
                else:
                    self.handoff_message = "USE A-Z, 0-9, SPACE, - / ."
                    return
                if len(draft.text) >= COORDINATION_MAX_LENGTH:
                    self.handoff_message = "MAX 120 CHARACTERS"
                    return
                draft.text += char
                self.handoff_message = ""
            return
        if symbol != arcade.key.Y:
            self.handoff_message = "PRESS Y TO CONFIRM OR ESC TO CANCEL"
            return
        aircraft = next(
            (
                item
                for item in self.aircraft_list.aircraft_list
                if item.id == draft.aircraft_id
            ),
            None,
        )
        if aircraft is None:
            self.coordination_draft = None
            self.handoff_message = "AIRCRAFT UNAVAILABLE"
            logging.getLogger(__name__).warning(
                "Cannot coordinate: aircraft is unavailable."
            )
            return
        track = aircraft.track
        try:
            if draft.stage == "offer":
                if draft.target is None:
                    raise ValueError("Coordination target is missing")
                if draft.kind == "HANDOFF":
                    if self.atc_facility.above_control_limit(aircraft.altitude):
                        if draft.target == TrackingPosition.YUMA:
                            raise ValueError(
                                f"Above FL{self.atc_facility.upper_control_flight_level:03d}: "
                                "Yuma cannot accept"
                            )
                        if draft.target != self.atc_facility.upper_control_center:
                            raise ValueError(
                                f"Above FL{self.atc_facility.upper_control_flight_level:03d}: "
                                f"handoff to {self.atc_facility.upper_control_center} required"
                            )
                    track.offer(draft.target, draft.text.strip())
                else:
                    track.offer_coordination(
                        CoordinationKind(draft.kind), draft.target, draft.text
                    )
                self.handoff_message = f"{draft.kind} OFFERED"
            elif draft.stage == "accept":
                if draft.kind == "HANDOFF":
                    if self.atc_facility.above_control_limit(aircraft.altitude):
                        raise ValueError(
                            f"Above FL{self.atc_facility.upper_control_flight_level:03d}: "
                            "Yuma cannot accept"
                        )
                    track.accept(TrackingPosition.YUMA)
                    self.handoff_message = "RADAR CONTACT; C COMMS / V ID"
                else:
                    track.accept_coordination(TrackingPosition.YUMA)
                    self.handoff_message = (
                        "TRAFFIC OBSERVED"
                        if draft.kind == CoordinationKind.TRAFFIC
                        else "POINT OUT APPROVED"
                    )
            elif draft.stage == "communications":
                track.transfer_communications()
                self.handoff_message = f"COMMS TRANSFER CONFIRMED TO {track.owner}"
            else:
                raise ValueError("Invalid coordination stage")
        except ValueError as error:
            self.handoff_message = str(error).upper()
            return
        self.coordination_draft = None
        RadarDisplay.refresh_track_snapshot(self, aircraft)

    def on_key_press(self, symbol, modifiers):
        panel = self.__dict__.get("strip_panel")
        if (
            panel is not None
            and panel.drag_strip is not None
            and symbol == arcade.key.ESCAPE
        ):
            panel.cancel_drag()
            return
        if panel is not None and panel.edit_strip is not None:
            panel.on_key_press(symbol, self.selected_aircraft_id)
            return
        if self.__dict__.get("clearance_draft") is not None:
            RadarDisplay.handle_clearance_draft(self, symbol)
            return
        if self.__dict__.get("coordination_draft") is not None:
            RadarDisplay.handle_coordination_draft(self, symbol)
            return
        if self.scratchpad_edit_id is not None:
            if symbol == arcade.key.ESCAPE:
                self.scratchpad_edit_id = None
            elif symbol == arcade.key.ENTER or symbol == arcade.key.NUM_ENTER:
                aircraft = next(
                    (
                        item
                        for item in self.aircraft_list.aircraft_list
                        if item.id == self.scratchpad_edit_id
                    ),
                    None,
                )
                if aircraft is None:
                    self.scratchpad_edit_error = "AIRCRAFT UNAVAILABLE"
                    logging.getLogger(__name__).warning(
                        "Cannot save scratchpad: aircraft is unavailable."
                    )
                    return
                aircraft.scratchpad = self.scratchpad_edit_text
                self.secondary_radar_returns = [
                    snapshot._replace(scratchpad=aircraft.scratchpad)
                    if snapshot.aircraft_id == aircraft.id
                    else snapshot
                    for snapshot in self.secondary_radar_returns
                ]
                self.scratchpad_edit_id = None
            elif symbol == arcade.key.BACKSPACE:
                self.scratchpad_edit_text = self.scratchpad_edit_text[:-1]
                self.scratchpad_edit_error = ""
            else:
                if arcade.key.A <= symbol <= arcade.key.Z:
                    character = chr(symbol).upper()
                elif ord("0") <= symbol <= ord("9") or symbol in (ord("-"), ord("/")):
                    character = chr(symbol)
                elif arcade.key.NUM_0 <= symbol <= arcade.key.NUM_9:
                    character = str(symbol - arcade.key.NUM_0)
                else:
                    self.scratchpad_edit_error = "USE A-Z, 0-9, - OR /"
                    return
                if len(self.scratchpad_edit_text) >= SCRATCHPAD_MAX_LENGTH:
                    self.scratchpad_edit_error = "MAX 16 CHARACTERS"
                    return
                self.scratchpad_edit_text += character
                self.scratchpad_edit_error = ""
            return
        if symbol == arcade.key.SPACE:
            communications = self.__dict__.get("communications_panel")
            if communications is not None:
                communications.keyboard_ptt = True
                RadarDisplay.sync_voice(self)
                return
        if self.handoff_choice_id is not None:
            if symbol == arcade.key.ESCAPE:
                self.handoff_choice_id = None
                kind = self.__dict__.get("handoff_choice_kind", "HANDOFF")
                self.handoff_message = f"{kind} CANCELED"
                return
            targets = {
                arcade.key.L: TrackingPosition.LOS_ANGELES,
                arcade.key.A: TrackingPosition.ALBUQUERQUE,
            }
            if symbol not in targets:
                self.handoff_message = "CHOOSE L OR A; ESC CANCEL"
                return
            aircraft = next(
                (
                    item
                    for item in self.aircraft_list.aircraft_list
                    if item.id == self.handoff_choice_id
                ),
                None,
            )
            self.handoff_choice_id = None
            if aircraft is None:
                self.handoff_message = "AIRCRAFT UNAVAILABLE"
                logging.getLogger(__name__).warning(
                    "Cannot coordinate: aircraft is unavailable."
                )
                return
            kind = self.__dict__.get("handoff_choice_kind", "HANDOFF")
            if (
                kind == "HANDOFF"
                and self.atc_facility.above_control_limit(aircraft.altitude)
                and targets[symbol] != self.atc_facility.upper_control_center
            ):
                self.handoff_message = (
                    f"ABOVE FL{self.atc_facility.upper_control_flight_level:03d}: "
                    f"HANDOFF TO {self.atc_facility.upper_control_center} REQUIRED"
                )
                return
            self.coordination_draft = CoordinationDraft(
                aircraft.id, kind, targets[symbol]
            )
            self.handoff_message = ""
            return
        if panel is not None and panel.on_key_press(symbol, self.selected_aircraft_id):
            return
        if symbol == arcade.key.G and self.selected_aircraft_id is not None:
            aircraft = next(
                (
                    item
                    for item in self.aircraft_list.aircraft_list
                    if item.id == self.selected_aircraft_id
                ),
                None,
            )
            if aircraft is None:
                self.handoff_message = "AIRCRAFT UNAVAILABLE"
                return
            error = clearance_control_error(aircraft, self.atc_facility)
            if error is not None:
                self.handoff_message = error.upper()
                return
            self.clearance_draft = ClearanceDraft(aircraft.id)
            self.handoff_message = ""
            return
        if self.selected_aircraft_id is not None and symbol in (
            arcade.key.H,
            arcade.key.I,
            arcade.key.A,
            arcade.key.X,
            arcade.key.P,
            arcade.key.T,
            arcade.key.D,
            arcade.key.C,
            arcade.key.V,
        ):
            aircraft = next(
                (
                    item
                    for item in self.aircraft_list.aircraft_list
                    if item.id == self.selected_aircraft_id
                ),
                None,
            )
            if aircraft is None:
                self.handoff_message = "AIRCRAFT UNAVAILABLE"
                logging.getLogger(__name__).warning(
                    "Cannot manage handoff: aircraft is unavailable."
                )
                return
            try:
                if symbol == arcade.key.H:
                    if aircraft.track.owner != TrackingPosition.YUMA:
                        raise ValueError("Yuma does not own this track")
                    if aircraft.track.handoff_target is not None:
                        raise ValueError("A handoff is already pending")
                    self.handoff_choice_id = aircraft.id
                    self.handoff_choice_kind = "HANDOFF"
                    self.handoff_message = ""
                    return
                if symbol == arcade.key.I:
                    if aircraft.track.owner == TrackingPosition.YUMA:
                        raise ValueError("Track is already owned by Yuma")
                    if self.atc_facility.above_control_limit(aircraft.altitude):
                        raise ValueError(
                            f"Above FL{self.atc_facility.upper_control_flight_level:03d}: "
                            "Yuma cannot accept"
                        )
                    self.coordination_draft = CoordinationDraft(
                        aircraft.id, "HANDOFF", TrackingPosition.YUMA
                    )
                    self.handoff_message = ""
                    return
                elif symbol == arcade.key.A:
                    coordination = aircraft.track.coordination
                    if aircraft.track.handoff_target == TrackingPosition.YUMA:
                        if self.atc_facility.above_control_limit(aircraft.altitude):
                            raise ValueError(
                                f"Above FL{self.atc_facility.upper_control_flight_level:03d}: "
                                "Yuma cannot accept"
                            )
                        kind = "HANDOFF"
                    elif (
                        coordination is not None
                        and not coordination.approved
                        and coordination.target == TrackingPosition.YUMA
                    ):
                        kind = coordination.kind
                    else:
                        raise ValueError("No incoming handoff or coordination")
                    self.coordination_draft = CoordinationDraft(
                        aircraft.id, kind, stage="accept"
                    )
                    self.handoff_message = ""
                    return
                elif symbol == arcade.key.X:
                    coordination = aircraft.track.coordination
                    if aircraft.track.handoff_target is not None:
                        aircraft.track.cancel()
                        self.handoff_message = "HANDOFF CANCELED"
                    elif coordination is not None and not coordination.approved:
                        aircraft.track.close_coordination()
                        self.handoff_message = "COORDINATION CANCELED OR REJECTED"
                    else:
                        raise ValueError("No pending coordination")
                elif symbol in (arcade.key.P, arcade.key.T):
                    if aircraft.track.coordination is not None:
                        raise ValueError("Close the existing coordination first")
                    if aircraft.track.handoff_target is not None:
                        raise ValueError("A handoff is already pending")
                    kind = (
                        CoordinationKind.POINT_OUT
                        if symbol == arcade.key.P
                        else CoordinationKind.TRAFFIC
                    )
                    if aircraft.track.owner == TrackingPosition.YUMA:
                        self.handoff_choice_id = aircraft.id
                        self.handoff_choice_kind = kind
                    else:
                        self.coordination_draft = CoordinationDraft(
                            aircraft.id, kind, TrackingPosition.YUMA
                        )
                    self.handoff_message = ""
                    return
                elif symbol == arcade.key.D:
                    if (
                        aircraft.track.coordination is None
                        or not aircraft.track.coordination.approved
                    ):
                        raise ValueError("No approved coordination to close")
                    aircraft.track.close_coordination()
                    self.handoff_message = "COORDINATION CLOSED"
                elif symbol == arcade.key.C:
                    if (
                        aircraft.track.handoff_target is not None
                        or aircraft.track.owner == aircraft.track.communications_owner
                    ):
                        raise ValueError("No accepted handoff awaiting comms")
                    self.coordination_draft = CoordinationDraft(
                        aircraft.id, "HANDOFF", stage="communications"
                    )
                    self.handoff_message = ""
                    return
                elif symbol == arcade.key.V:
                    aircraft.track.confirm_identification()
                    self.handoff_message = "INCOMING IDENTIFICATION CONFIRMED"
            except ValueError as error:
                self.handoff_message = str(error).upper()
                return
            RadarDisplay.refresh_track_snapshot(self, aircraft)
            return
        if symbol == arcade.key.S and self.selected_aircraft_id is not None:
            aircraft = next(
                (
                    item
                    for item in self.aircraft_list.aircraft_list
                    if item.id == self.selected_aircraft_id
                ),
                None,
            )
            if aircraft is None:
                logging.getLogger(__name__).warning(
                    "Cannot edit scratchpad: aircraft is unavailable."
                )
                return
            self.scratchpad_edit_id = aircraft.id
            self.scratchpad_edit_text = aircraft.scratchpad
            self.scratchpad_edit_error = ""
            return
        if symbol in LAYER_KEYS:
            self.gis_overlays.toggle(LAYER_KEYS.index(symbol))
            return
        if symbol in PAN_DIRECTIONS:
            self.radar_viewport.pan(*PAN_DIRECTIONS[symbol])
            return
        if symbol == arcade.key.HOME:
            self.radar_viewport.reset()
            return
        if self.selected_aircraft_id is not None and symbol in NUMPAD_DIRECTIONS:
            self.data_block_directions[self.selected_aircraft_id] = NUMPAD_DIRECTIONS[
                symbol
            ]

    def on_key_release(self, symbol, modifiers):
        if symbol == arcade.key.SPACE:
            communications = self.__dict__.get("communications_panel")
            if communications is not None:
                communications.keyboard_ptt = False
                RadarDisplay.sync_voice(self)

    def on_mouse_scroll(self, x, y, scroll_x, scroll_y):
        if y >= SCREEN_HEIGHT:
            return
        if x >= SCREEN_WIDTH:
            self.strip_panel.scroll(scroll_y)
        else:
            self.radar_viewport.zoom_by(scroll_y)

    def on_mouse_motion(self, x, y, dx, dy):
        self.strip_panel.hover_position = (x, y)

    def on_mouse_drag(self, x, y, dx, dy, buttons, modifiers):
        self.on_mouse_motion(x, y, dx, dy)
        if buttons & arcade.MOUSE_BUTTON_LEFT:
            self.strip_panel.move_drag(x, y)

    def on_mouse_release(self, x, y, button, modifiers):
        if button == arcade.MOUSE_BUTTON_LEFT:
            communications = self.__dict__.get("communications_panel")
            if communications is not None and communications.mouse_ptt:
                communications.release()
                RadarDisplay.sync_voice(self)
                return
            self.strip_panel.finish_drag(x, y)

    def on_mouse_leave(self, x, y):
        communications = self.__dict__.get("communications_panel")
        if communications is not None:
            communications.release()
            RadarDisplay.sync_voice(self)
        self.strip_panel.hover_position = None

    def on_deactivate(self):
        self.communications_panel.release_all()
        RadarDisplay.sync_voice(self)

    def on_close(self):
        if self.voice_audio is not None:
            self.voice_audio.close()
        self.gis_overlays.close()
        super().on_close()

    def close(self):
        if self.voice_audio is not None:
            self.voice_audio.close()
        self.gis_overlays.close()
        super().close()

    def update(self, delta_time):
        self.on_update(delta_time)

    def draw_arts_iie(self):
        """
        Draw the ARTS IIE display.
        """
        arcade.draw_circle_outline(
            SCREEN_WIDTH / 2,
            SCREEN_HEIGHT / 2,
            DISPLAY_RADIUS,
            arcade.color.DIM_GRAY,
            1,
        )
        self.draw_degree_markings(
            SCREEN_WIDTH / 2, SCREEN_HEIGHT / 2, DISPLAY_RADIUS + 24
        )

    def draw_sweep(self):
        self.map_camera.use()
        self.sweep_sector.angle = np.degrees(self.sweep.angle)
        self.sweep_sector.draw()
        self.default_camera.use()
        start_x, start_y = self.transform_position(SCREEN_WIDTH / 2, SCREEN_HEIGHT / 2)
        end_x, end_y = self.transform_position(
            SCREEN_WIDTH / 2 + DISPLAY_RADIUS * np.sin(self.sweep.angle),
            SCREEN_HEIGHT / 2 + DISPLAY_RADIUS * np.cos(self.sweep.angle),
        )
        arcade.draw_line(start_x, start_y, end_x, end_y, SWEEP_COLOR, 2)

    def draw_stars(self):
        """
        Draw the STARS display.
        """
        rect_width = SCREEN_WIDTH
        rect_height = SCREEN_HEIGHT

        arcade.draw_rect_outline(
            arcade.XYWH(SCREEN_WIDTH / 2, SCREEN_HEIGHT / 2, rect_width, rect_height),
            arcade.color.DIM_GRAY,
            1,
        )
        self.draw_degree_markings(
            SCREEN_WIDTH / 2, SCREEN_HEIGHT / 2, rect_width, rect_height
        )

    @staticmethod
    def draw_degree_markings(center_x, center_y, width, height=None):
        """
        Draw the degree markings around the display.
        """
        for angle in range(0, 360, 15):
            angle_radians = np.radians(angle)
            if height:
                x = center_x + width * np.sin(angle_radians) / 2
                y = center_y + height * np.cos(angle_radians) / 2
            else:
                x = center_x + width * np.sin(angle_radians)
                y = center_y + width * np.cos(angle_radians)
            arcade.draw_text(
                f"{angle}",
                x,
                y,
                arcade.color.WHITE,
                12,
                anchor_x="center",
                anchor_y="center",
            )

    def toggle_display_type(self):
        """
        Toggle between ARTS IIE and STARS display types.
        """
        if self.display_type == self.ARTS_IIE:
            self.display_type = self.STARS
        else:
            self.display_type = self.ARTS_IIE

    def convert_to_display_coordinates(self, lat, lon):
        """
        Convert a geographic position to display coordinates relative to the facility.
        """
        distance, bearing = self.calculate_range_and_bearing(lat, lon)
        if self.display_type == self.ARTS_IIE:
            pixels_per_mile = DISPLAY_RADIUS / MAX_DISTANCE_MILES
        else:
            pixels_per_mile = min(SCREEN_WIDTH, SCREEN_HEIGHT) / (
                2 * MAX_DISTANCE_MILES
            )
        x = SCREEN_WIDTH / 2 + distance * pixels_per_mile * np.sin(bearing)
        y = SCREEN_HEIGHT / 2 + distance * pixels_per_mile * np.cos(bearing)
        return self.transform_position(x, y)

    def calculate_range_and_bearing(self, lat, lon):
        facility_lat = self.atc_facility.location["lat"]
        facility_lon = self.atc_facility.location["lon"]
        lat1 = np.radians(facility_lat)
        lat2 = np.radians(lat)
        delta_lon = np.radians(lon - facility_lon)
        bearing_y = np.sin(delta_lon) * np.cos(lat2)
        bearing_x = np.cos(lat1) * np.sin(lat2) - np.sin(lat1) * np.cos(lat2) * np.cos(
            delta_lon
        )
        bearing = np.arctan2(bearing_y, bearing_x) % (2 * np.pi)
        distance = NavigationalCoordinateSystem.calculate_distance(
            facility_lat, facility_lon, lat, lon
        )
        return distance, bearing

    def draw_point(self, x, y, callsign=None, color=arcade.color.YELLOW):
        """
        Draw a point on the radar display.
        """
        arcade.draw_circle_filled(x, y, 3, color)
        if callsign is not None:
            arcade.draw_text(callsign, x + 5, y, color, 12)
