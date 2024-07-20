import arcade
import numpy as np
from constants import SCREEN_WIDTH, SCREEN_HEIGHT, SCREEN_TITLE, SWEEP_SPEED, ANGLE_TOLERANCE, DISPLAY_RADIUS, \
    DEGREE_INTERVAL, CIRCLE_SEGMENTS, MAX_DISTANCE_MILES
from aircraft import AircraftList


class RadarSweep:
    """
    Manages the radar sweep animation and logic.
    """
    def __init__(self):
        self.angle = 0
        self.sweep_speed = SWEEP_SPEED

    def update(self):
        """
        Update the radar sweep angle.
        """
        self.angle = (self.angle + self.sweep_speed) % (2 * np.pi)  # Clockwise rotation


class RadarReturnManager:
    """
    Manages the radar returns for aircraft.
    """
    def __init__(self):
        self.radar_returns = []

    def add_return(self, angle, distance):
        """
        Add a radar return at the specified angle and distance.
        """
        self.radar_returns.append([angle, distance, 1.0])  # Add new return with full opacity

    def update(self):
        """
        Update the opacity of radar returns, decreasing over time.
        """
        for radar_return in self.radar_returns:
            radar_return[2] -= 0.1 / 60  # Decrease opacity
        self.radar_returns = [r for r in self.radar_returns if r[2] > 0]  # Keep returns with positive opacity


class PrimaryRadarReturn:
    """
    Handles the primary radar returns based on the radar sweep angle.
    """
    def __init__(self, radar_return_manager, aircraft, sweep_angle):
        self.radar_return_manager = radar_return_manager
        self.aircraft = aircraft
        self.sweep_angle = sweep_angle
        self.add_return()

    def add_return(self):
        """
        Add a radar return for the aircraft if it is within the sweep angle tolerance.
        """
        angle, distance = self.aircraft.angle, self.aircraft.distance
        if abs(angle - self.sweep_angle) < ANGLE_TOLERANCE:
            self.radar_return_manager.add_return(angle, distance)


class SecondaryRadarReturn:
    """
    Plots the secondary radar return information for an aircraft.
    """
    def __init__(self, aircraft):
        self.aircraft = aircraft

    def plot(self, x, y):
        """
        Plot the secondary radar return on the display.
        """
        text = (f"{self.aircraft.callsign} {self.aircraft.squawk}\n"
                f"{round(np.degrees(self.aircraft.angle))} {self.aircraft.altitude}\n"
                f"{self.aircraft.aircraft_model.aircraft_type} {self.aircraft.speed}\n"
                f"{self.aircraft.distance:.1f}")

        heading_offset = np.pi  # 180 degrees in radians
        text_x = x + 40 * np.cos(self.aircraft.angle + heading_offset)
        text_y = y + 40 * np.sin(self.aircraft.angle + heading_offset)

        arcade.draw_line(x, y, text_x, text_y, arcade.color.LIGHT_BLUE, 1)
        arcade.draw_text(text, text_x, text_y, arcade.color.LIGHT_BLUE, 10, anchor_x="center", anchor_y="center",
                         multiline=True, width=200)


class RadarDisplay(arcade.Window):
    """
    Main class for managing the radar display window.
    """
    def __init__(self, aircraft_list):
        super().__init__(SCREEN_WIDTH, SCREEN_HEIGHT, SCREEN_TITLE)
        arcade.set_background_color(arcade.color.BLACK)

        self.aircraft_list = aircraft_list
        self.radar_return_manager = RadarReturnManager()
        self.radar_sweep = RadarSweep()
        self.center_x = SCREEN_WIDTH // 2
        self.center_y = SCREEN_HEIGHT // 2

    def setup(self):
        """
        Set up the radar display (placeholder for any setup operations).
        """
        pass

    def on_draw(self):
        """
        Render the radar display.
        """
        arcade.start_render()

        # Draw static radar overlay
        self.draw_static_overlay()

        # Draw radar sweep
        self.draw_sweep()

        # Draw aircraft
        self.draw_aircraft()

        # Update radar returns
        self.radar_return_manager.update()

    def draw_static_overlay(self):
        """
        Draw the static overlay for the radar display.
        """
        # Draw outer circle
        arcade.draw_circle_outline(self.center_x, self.center_y, DISPLAY_RADIUS, arcade.color.GREEN, 2,
                                   num_segments=CIRCLE_SEGMENTS)

        # Draw headings
        for degree in range(0, 360, DEGREE_INTERVAL):
            radian = np.radians(90 - degree)  # Adjust to navigational coordinates
            x = self.center_x + (DISPLAY_RADIUS + 30) * np.cos(radian)
            y = self.center_y + (DISPLAY_RADIUS + 30) * np.sin(radian)
            arcade.draw_text(f"{degree}", x, y, arcade.color.LIGHT_BLUE, 12, anchor_x="center", anchor_y="center")

    def draw_sweep(self):
        """
        Draw the radar sweep line.
        """
        sweep_angle_radian = np.radians(90 - np.degrees(self.radar_sweep.angle))  # Adjust to navigational coordinates
        end_x = self.center_x + DISPLAY_RADIUS * np.cos(sweep_angle_radian)
        end_y = self.center_y + DISPLAY_RADIUS * np.sin(sweep_angle_radian)
        arcade.draw_line(self.center_x, self.center_y, end_x, end_y, arcade.color.ORANGE, 2)
        self.radar_sweep.update()

    def draw_aircraft(self):
        """
        Draw all aircraft on the radar display.
        """
        for aircraft in self.aircraft_list.aircraft_list:
            aircraft_angle_radian = np.radians(90 - np.degrees(aircraft.angle))  # Adjust to navigational coordinates
            distance_in_pixels = DISPLAY_RADIUS * (aircraft.distance / MAX_DISTANCE_MILES)
            x = self.center_x + distance_in_pixels * np.cos(aircraft_angle_radian)
            y = self.center_y + distance_in_pixels * np.sin(aircraft_angle_radian)
            if distance_in_pixels <= DISPLAY_RADIUS:
                arcade.draw_circle_filled(x, y, 5, arcade.color.BLUE)
                PrimaryRadarReturn(self.radar_return_manager, aircraft, self.radar_sweep.angle)
                SecondaryRadarReturn(aircraft).plot(x, y + 10)

    def update(self, delta_time):
        """
        Update the positions of all aircraft and refresh the display.
        """
        self.aircraft_list.update_positions()
