from constants import KNOTS_TO_MILES_PER_FRAME, MAX_DISTANCE_MILES, VFR_SQUAWK, IFR_SQUAWK
import numpy as np


class AircraftModel:
    """
    Defines the specifications and performance characteristics of different aircraft models.
    """
    def __init__(self, aircraft_type, climb_rate, turn_rate, air_braking_rate, thrust_rate, drag_rate, mass, max_speed,
                 cruise_speed, service_ceiling, fuel_capacity, fuel_consumption_rate, max_range, stall_speed, wing_span, length,
                 max_takeoff_weight, engine_type, passenger_capacity, landing_gear_type, avionics_systems,
                 min_takeoff_distance):
        self.aircraft_type = aircraft_type
        self.climb_rate = climb_rate
        self.turn_rate = turn_rate
        self.air_braking_rate = air_braking_rate
        self.thrust_rate = thrust_rate
        self.drag_rate = drag_rate
        self.mass = mass
        self.max_speed = max_speed
        self.cruise_speed = cruise_speed
        self.service_ceiling = service_ceiling
        self.fuel_capacity = fuel_capacity
        self.fuel_consumption_rate = fuel_consumption_rate
        self.max_range = max_range
        self.stall_speed = stall_speed
        self.wing_span = wing_span
        self.length = length
        self.max_takeoff_weight = max_takeoff_weight
        self.engine_type = engine_type
        self.passenger_capacity = passenger_capacity
        self.landing_gear_type = landing_gear_type
        self.avionics_systems = avionics_systems
        self.min_takeoff_distance = min_takeoff_distance


class Aircraft:
    """
    Represents an instance of an aircraft with specific attributes and behaviors.
    """
    def __init__(self, aircraft_id, squawk, mode_s, callsign, aircraft_model, angle, altitude, speed, distance, ads_b,
                 flight_rules="None", landed=False):
        self.id = aircraft_id
        self.squawk = squawk
        self.mode_s = mode_s
        self.callsign = callsign
        self.aircraft_model = aircraft_model
        self.angle = angle
        self.altitude = altitude  # Altitude in hundreds of feet
        self.speed = speed
        self.distance = distance
        self.ads_b = ads_b
        self.landed = landed

        # Set squawk code based on flight rules
        if flight_rules == "VFR":
            self.squawk = VFR_SQUAWK
        elif flight_rules == "IFR":
            self.squawk = IFR_SQUAWK

        # Adjust altitude based on heading
        if self.altitude >= 30:  # Considering altitude in hundreds of feet
            heading = np.degrees(self.angle)
            if 0 <= heading < 180:
                self.altitude = ((self.altitude // 20) * 20) + 50  # Odd intervals starting from 5000 feet
            else:
                self.altitude = ((self.altitude // 20) * 20) + 40  # Even intervals starting from 4000 feet

    def on_ground(self):
        """
        Update the distance of the aircraft if it is not landed.
        """
        if not self.landed:
            self.distance = (self.distance + self.speed * KNOTS_TO_MILES_PER_FRAME) % MAX_DISTANCE_MILES

    def update_heading(self, target_angle):
        """
        Update the heading of the aircraft towards the target angle.
        """
        current_angle_deg = np.degrees(self.angle)
        target_angle_deg = np.degrees(target_angle)
        angle_diff = (target_angle_deg - current_angle_deg + 360) % 360

        if angle_diff > 180:
            angle_diff -= 360

        if abs(angle_diff) < self.aircraft_model.turn_rate:
            self.angle = target_angle
        else:
            angle_change = np.radians(
                self.aircraft_model.turn_rate if angle_diff > 0 else -self.aircraft_model.turn_rate)
            self.angle = (self.angle + angle_change) % (2 * np.pi)

    def update_altitude(self, target_altitude):
        """
        Update the altitude of the aircraft towards the target altitude.
        """
        if abs(target_altitude - self.altitude) < self.aircraft_model.climb_rate:
            self.altitude = target_altitude
        else:
            self.altitude += self.aircraft_model.climb_rate if target_altitude > self.altitude else -self.aircraft_model.climb_rate

    def update_speed(self, target_speed):
        """
        Update the speed of the aircraft towards the target speed.
        """
        if abs(target_speed - self.speed) < self.aircraft_model.thrust_rate:
            self.speed = target_speed
        else:
            if target_speed > self.speed:
                self.speed += self.aircraft_model.thrust_rate
            else:
                self.speed -= self.aircraft_model.air_braking_rate

    def update_squawk(self, squawk):
        """
        Update the squawk code of the aircraft.
        """
        self.squawk = squawk


class AircraftList:
    """
    Manages a list of aircraft and updates their positions.
    """
    def __init__(self):
        self.aircraft_list = []

    def add_aircraft(self, aircraft):
        """
        Add an aircraft to the list.
        """
        self.aircraft_list.append(aircraft)

    def update_positions(self):
        """
        Update the positions of all aircraft in the list.
        """
        for aircraft in self.aircraft_list:
            aircraft.on_ground()
