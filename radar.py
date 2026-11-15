import logging
import math
from typing import NamedTuple

import arcade
import numpy as np

from constants import (
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
from gis_overlays import LAYER_KEYS, GISOverlays
from navmath import NavigationalCoordinateSystem

SWEEP_COLOR = arcade.color.ORANGE
DATA_BLOCK_DISTANCE = 40
DATA_BLOCK_WIDTH = 200
DATA_BLOCK_FONT = "Consolas"
DATA_BLOCK_FONT_SIZE = 11
EMERGENCY_FLASH_SECONDS = 1.0
SCRATCHPAD_MAX_LENGTH = 16
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

    def __init__(self, aircraft_list, atc_facility):
        super().__init__(SCREEN_WIDTH, SCREEN_HEIGHT, SCREEN_TITLE)
        arcade.set_background_color(arcade.color.BLACK)
        self.aircraft_list = aircraft_list
        self.atc_facility = atc_facility
        self.sweep = RadarSweep()
        self.radar_return_manager = RadarReturnManager()
        self.display_type = self.ARTS_IIE
        self.secondary_update_elapsed = 0.0
        self.emergency_flash_elapsed = 0.0
        self.secondary_radar_returns = []
        self.selected_aircraft_id = None
        self.scratchpad_edit_id = None
        self.scratchpad_edit_text = ""
        self.scratchpad_edit_error = ""
        self.data_block_directions = {}
        self.data_block_labels = {}
        self.secondary_return_layouts = []
        self.data_block_overlap_warned = False
        self.capture_secondary_radar_returns()
        self.gis_overlays = GISOverlays(
            atc_facility.location["lat"], atc_facility.location["lon"]
        )
        self.radar_viewport = RadarViewport()
        self.map_camera = arcade.Camera2D(window=self)
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
        shapes.position = self.center_x, self.center_y
        return shapes

    def create_scope_mask(self):
        cx, cy, radius = self.center_x, self.center_y, DISPLAY_RADIUS
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
        return self.radar_viewport.transform(x, y, self.center_x, self.center_y, radius)

    def is_visible_scope_position(self, x, y):
        if self.display_type == self.STARS:
            return 0 <= x <= self.width and 0 <= y <= self.height
        return np.hypot(x - self.center_x, y - self.center_y) <= DISPLAY_RADIUS

    def setup(self):
        """
        Set up the radar display.
        """

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
            self.center_x, self.center_y, radius
        )
        self.map_camera.zoom = self.radar_viewport.zoom
        self.map_camera.use()
        self.gis_overlays.draw_map(radius)
        self.default_camera.use()
        if self.display_type == self.ARTS_IIE:
            visible = self.is_visible_scope_position
        else:
            visible = lambda x, y: 0 <= x <= self.width and 0 <= y <= self.height
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

    def on_update(self, delta_time):
        """
        Advance the sweep, aircraft, and radar returns.
        """
        previous_sweep_angle = self.sweep.angle
        self.sweep.update(delta_time)
        self.radar_return_manager.update(delta_time)
        self.emergency_flash_elapsed = (
            self.emergency_flash_elapsed + delta_time
        ) % EMERGENCY_FLASH_SECONDS

        # Generate radar returns
        for aircraft in self.aircraft_list.aircraft_list:
            if not aircraft.landed:
                aircraft.update_position(delta_time)
            distance, bearing = self.calculate_range_and_bearing(
                aircraft.lat, aircraft.lon
            )
            aircraft.distance = distance
            if self.display_type == self.ARTS_IIE:
                PrimaryRadarReturn(
                    self.radar_return_manager,
                    bearing,
                    distance,
                    previous_sweep_angle,
                    self.sweep.angle,
                    self.center_x,
                    self.center_y,
                    DISPLAY_RADIUS,
                ).add_return()

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
            return (aircraft.altitude > previous) - (aircraft.altitude < previous)

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
            )
            for aircraft in self.aircraft_list.aircraft_list
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
        text = f"{snapshot.callsign}{emergency}\n{altitude}  {speed}\n{snapshot.aircraft_type}\n{snapshot.scratchpad or ' '}"
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
            direction = self.data_block_directions.get(snapshot.aircraft_id)
            _, preferred_x, preferred_y = self.secondary_return_layout(
                snapshot, x, y, distance, direction
            )
            preferred_dx, preferred_dy = preferred_x - x, preferred_y - y
            directions = [(preferred_dx, preferred_dy), *DATA_BLOCK_DIRECTIONS]
            position = None

            def available(text_x, text_y, width=width, height=height):
                return (
                    width / 2 <= text_x <= self.width - width / 2
                    and height / 2 <= text_y <= self.height - height / 2
                    and not any(
                        abs(text_x - other.text_x) < (width + other.width) / 2 + 4
                        and abs(text_y - other.text_y) < (height + other.height) / 2 + 4
                        for other in layouts
                    )
                )

            max_radius = np.hypot(self.width, self.height) + DATA_BLOCK_DISTANCE
            for radius in range(
                DATA_BLOCK_DISTANCE, int(max_radius) + 1, DATA_BLOCK_DISTANCE
            ):
                for dx, dy in directions:
                    length = np.hypot(dx, dy)
                    text_x, text_y = x + radius * dx / length, y + radius * dy / length
                    if not available(text_x, text_y):
                        continue
                    position = (text_x, text_y)
                    break
                if position is not None:
                    break
            if position is None:
                candidate_x = [width / 2, self.width - width / 2]
                candidate_y = [height / 2, self.height - height / 2]
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
                position = (
                    min(max(preferred_x, width / 2), self.width - width / 2),
                    min(max(preferred_y, height / 2), self.height - height / 2),
                )
            layouts.append(
                SecondaryReturnLayout(
                    snapshot, distance, x, y, *position, width, height
                )
            )

        if placement_failed and not self.data_block_overlap_warned:
            logging.getLogger(__name__).warning(
                "Unable to place all radar data blocks without overlap."
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
        dx, dy = text_x - x, text_y - y
        intersection = min(
            1.0,
            width / (2 * abs(dx)) if dx else 1.0,
            height / (2 * abs(dy)) if dy else 1.0,
        )
        arcade.draw_line(
            x,
            y,
            text_x - intersection * dx,
            text_y - intersection * dy,
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
        if self.scratchpad_edit_id == snapshot.aircraft_id:
            text += f"\nEDIT SCRATCHPAD:\n{self.scratchpad_edit_text}_\nENTER SAVE / ESC CANCEL"
            if self.scratchpad_edit_error:
                text += f"\n{self.scratchpad_edit_error}"
        if self.selected_details_text.text != text:
            self.selected_details_text.text = text
        self.selected_details_text.draw()

    def on_mouse_press(self, x, y, button, modifiers):
        if button != arcade.MOUSE_BUTTON_LEFT:
            return
        self.scratchpad_edit_id = None

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

    def on_key_press(self, symbol, modifiers):
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

    def on_mouse_scroll(self, x, y, scroll_x, scroll_y):
        self.radar_viewport.zoom_by(scroll_y)

    def on_close(self):
        self.gis_overlays.close()
        super().on_close()

    def close(self):
        self.gis_overlays.close()
        super().close()

    def update(self, delta_time):
        self.on_update(delta_time)

    def draw_arts_iie(self):
        """
        Draw the ARTS IIE display.
        """
        arcade.draw_circle_outline(
            self.center_x, self.center_y, DISPLAY_RADIUS, arcade.color.DIM_GRAY, 1
        )
        self.draw_degree_markings(self.center_x, self.center_y, DISPLAY_RADIUS + 24)

    def draw_sweep(self):
        self.map_camera.use()
        self.sweep_sector.angle = np.degrees(self.sweep.angle)
        self.sweep_sector.draw()
        self.default_camera.use()
        start_x, start_y = self.transform_position(self.center_x, self.center_y)
        end_x, end_y = self.transform_position(
            self.center_x + DISPLAY_RADIUS * np.sin(self.sweep.angle),
            self.center_y + DISPLAY_RADIUS * np.cos(self.sweep.angle),
        )
        arcade.draw_line(start_x, start_y, end_x, end_y, SWEEP_COLOR, 2)

    def draw_stars(self):
        """
        Draw the STARS display.
        """
        rect_width = SCREEN_WIDTH
        rect_height = SCREEN_HEIGHT

        arcade.draw_rect_outline(
            arcade.XYWH(self.center_x, self.center_y, rect_width, rect_height),
            arcade.color.DIM_GRAY,
            1,
        )
        self.draw_degree_markings(self.center_x, self.center_y, rect_width, rect_height)

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
        x = self.center_x + distance * pixels_per_mile * np.sin(bearing)
        y = self.center_y + distance * pixels_per_mile * np.cos(bearing)
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
