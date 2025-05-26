from geopy.distance import distance
from geopy.point import Point
import numpy as np


class Aircraft:
    def __init__(self, aircraft_type, bearing_deg, velocity, aircraft_id, mode_a, mode_c, mode_s, ads_b):
        self.aircraft_type = aircraft_type
        self.bearing_deg = bearing_deg  # aircraft bearing
        self.velocity = velocity  # knots
        self.id = aircraft_id  # aircraft game id
        self.mode_a = mode_a  # 4-digit squawk code
        self.mode_c = mode_c  # Altitude (based on pressure altitude)
        self.mode_s = mode_s  # Selective
        self.ads_b = ads_b  # ADS-B: Position, altitude, velocity, ID.
        #   - Currently used in game for instantiation location (lat, long).

        self.assigned_altitude = mode_c
        self.assigned_speed = aircraft_type.cruise_speed
        self.assigned_bearing_deg = bearing_deg

        self.tick_duration_minutes = 0.05 / 60

    def __repr__(self):
        return (f"<Aircraft {self.id} | {self.aircraft_type.name} | "
                f"{self.velocity:.1f} kt | FL{int(self.mode_c / 100):03d} | "
                f"Hdg {self.bearing_deg:.1f}°>")

    @property
    def bearing_rad(self):
        """Return the bearing in radians for internal calculations."""
        return np.radians(self.bearing_deg % 360)

    @property
    def vertical_status(self):
        delta = self.assigned_altitude - self.mode_c
        if abs(delta) < 50:
            return "Level"
        return "Climbing" if delta > 0 else "Descending"

    @property
    def speed_status(self):
        delta = self.assigned_speed - self.velocity
        if abs(delta) < 5:
            return "Cruise"
        return "Accelerating" if delta > 0 else "Slowing"

    @property
    def heading_status(self):
        delta = (self.assigned_bearing_deg - self.bearing_deg + 360) % 360
        if delta > 180:
            delta -= 360
        return "Turning" if abs(delta) > 1 else "Steady"

    def update_position(self):
        origin = Point(self.ads_b["lat"], self.ads_b["lon"])
        bearing = self.bearing_deg % 360
        speed_kph = self.velocity * 1.852  # 1 knot = 1.852 km/h
        tick_duration_hours = self.tick_duration_minutes / 60  # 10-second tick
        distance_km = speed_kph * tick_duration_hours

        new_location = distance(kilometers=distance_km).destination(origin, bearing)
        self.ads_b["lat"] = new_location.latitude
        self.ads_b["lon"] = new_location.longitude

    def update_speed(self, target_speed=None):
        """
        Adjust velocity toward a target speed using acceleration/deceleration rates.
        If no target is given, assume the aircraft is trying to reach cruise speed.
        """
        type_profile = self.aircraft_type
        current_speed = self.velocity
        altitude = self.mode_c  # Assuming in feet, you could convert to meters

        if target_speed is None:
            target_speed = type_profile.cruise_speed

        if current_speed < target_speed:
            accel = type_profile.get_acceleration(altitude, current_speed)
            self.velocity = min(self.velocity + accel, type_profile.max_speed)
        elif current_speed > target_speed:
            decel = type_profile.get_deceleration(altitude, current_speed)
            self.velocity = max(self.velocity - decel, 0)

    def update_squawk(self, mode_a):
        """Simulate the update of the aircraft's data."""
        self.mode_a = str(int(self.mode_a) + 1).zfill(4)

    def update_altitude(self, assigned_altitude):
        """
        Adjust altitude toward the assigned target using aircraft type climb/descent rate.
        """
        assigned_altitude = max(0, assigned_altitude)  # Prevent going below ground level
        current_altitude = self.mode_c
        type_profile = self.aircraft_type
        delta = assigned_altitude - current_altitude

        if abs(delta) < 50:  # Close enough, stop climbing/descending
            self.mode_c = assigned_altitude
            return

        if delta > 0:
            # Climb
            climb = type_profile.climb_rate * self.tick_duration_minutes
            self.mode_c = min(current_altitude + climb, assigned_altitude)
        else:
            # Descend
            descent = type_profile.descent_rate * self.tick_duration_minutes
            self.mode_c = max(current_altitude - descent, assigned_altitude)

    def update_bearing(self, new_bearing_deg):
        delta = (new_bearing_deg - self.bearing_deg + 360) % 360
        if delta > 180:
            delta -= 360  # Shortest turn direction

        turn_amount = self.aircraft_type.turn_rate * self.tick_duration_minutes
        if abs(delta) <= turn_amount:
            self.bearing_deg = new_bearing_deg
        else:
            self.bearing_deg += turn_amount if delta > 0 else -turn_amount
            self.bearing_deg %= 360

    def update_mode_s(self, mode_s):
        self.mode_s = mode_s

    def update_flight_profile(self):
        self.update_speed(self.assigned_speed)
        self.update_altitude(self.assigned_altitude)
        self.update_bearing(self.assigned_bearing_deg)