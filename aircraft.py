import math

from atc import TrackOwnership
from constants import FPS
from navmath import NavigationalCoordinateSystem


class AircraftModel:
    """
    Defines the specifications and performance characteristics of different aircraft models.

    Climb rate is in feet per second, turn rate in degrees per second, speed
    rates in knots per second, and fuel consumption in gallons per hour.
    """

    def __init__(
        self,
        aircraft_type,
        climb_rate,
        turn_rate,
        air_braking_rate,
        thrust_rate,
        drag_rate,
        mass,
        max_speed,
        cruise_speed,
        service_ceiling,
        fuel_capacity,
        fuel_consumption_rate,
        max_range,
        stall_speed,
        wing_span,
        length,
        max_takeoff_weight,
        engine_type,
        passenger_capacity,
        landing_gear_type,
        avionics_systems,
        min_takeoff_distance,
    ):
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

    def __init__(
        self,
        aircraft_id,
        squawk,
        mode_s,
        callsign,
        aircraft_model,
        heading,
        altitude,
        speed,
        distance,
        lat,
        lon,
        flight_rules="None",
        landed=False,
    ):
        self._validate_speed(speed, aircraft_model)
        self.id = aircraft_id
        self.squawk = squawk
        self.scratchpad = ""
        self.track = TrackOwnership()
        self.mode_s = mode_s
        self.callsign = callsign
        self.aircraft_model = aircraft_model
        self.heading = heading  # The direction the aircraft is traveling in degrees
        self.altitude = altitude  # Altitude in hundreds of feet
        self.speed = speed
        self.distance = distance
        self.lat = lat
        self.lon = lon
        self.landed = landed
        self.flight_rules = flight_rules
        self.target_heading = None
        self.target_altitude = None
        self.target_speed = None
        self.flight_guidance = None
        self.departure = None

    @staticmethod
    def _validate_speed(speed, aircraft_model):
        if not math.isfinite(speed) or not 0 <= speed <= aircraft_model.max_speed:
            raise ValueError(
                f"Speed must be between 0 and {aircraft_model.max_speed} knots"
            )

    @staticmethod
    def _advance_toward(current, target, rate, delta_time):
        difference = target - current
        if difference == 0 or delta_time == 0:
            return current, current
        change = min(abs(difference), rate * delta_time)
        end = (
            target
            if change == abs(difference)
            else current + math.copysign(change, difference)
        )
        time_changing = change / rate if rate else 0
        average = end - (end - current) * time_changing / (2 * delta_time)
        return end, average

    def on_ground(self, delta_time=1 / FPS, atc_facility=None):
        """Move an airborne aircraft and update its range from the facility."""
        if atc_facility is None:
            raise ValueError("An ATC facility is required to calculate aircraft range")
        if not self.landed:
            self.update_position(delta_time)
        location = atc_facility.location
        self.distance = NavigationalCoordinateSystem.calculate_distance(
            location["lat"], location["lon"], self.lat, self.lon
        )

    def update_position(self, delta_time=1 / FPS):
        """
        Advance commanded maneuvers and position by delta_time seconds.
        """
        if not math.isfinite(delta_time) or delta_time < 0:
            raise ValueError("Elapsed time must be a non-negative finite number")
        if delta_time == 0:
            return
        if self.departure is not None and self.departure.check_in is None:
            if self.landed:
                return
            if self.flight_guidance is None:
                raise RuntimeError("A departing aircraft requires flight guidance")
            remaining = delta_time
            while remaining > 0 and not self.landed:
                step = min(remaining, 1.0)
                airborne_time = self.departure.advance(self, step)
                if airborne_time:
                    self.flight_guidance.update(self, airborne_time)
                    self.departure.record_airborne(self, airborne_time)
                remaining -= step
                if self.departure.check_in is not None:
                    if remaining > 0:
                        self.flight_guidance.update(self, remaining)
                    return
            return
        if self.flight_guidance is not None:
            if not self.landed:
                self.flight_guidance.update(self, delta_time)
            return

        self._advance_position(delta_time)

    def _advance_position(self, delta_time):
        average_heading = self.heading
        if self.target_heading is not None:
            difference = (self.target_heading - self.heading + 360) % 360
            if difference > 180:
                difference -= 360
            heading, average_heading = self._advance_toward(
                self.heading,
                self.heading + difference,
                self.aircraft_model.turn_rate,
                delta_time,
            )
            self.heading = heading % 360
            if abs(difference) <= self.aircraft_model.turn_rate * delta_time:
                self.heading = self.target_heading
                self.target_heading = None

        if self.target_altitude is not None:
            self.altitude, _ = self._advance_toward(
                self.altitude,
                self.target_altitude,
                self.aircraft_model.climb_rate / 100,
                delta_time,
            )
            if self.altitude == self.target_altitude:
                self.target_altitude = None

        average_speed = self.speed
        if self.target_speed is not None:
            rate = (
                self.aircraft_model.thrust_rate
                if self.target_speed > self.speed
                else self.aircraft_model.air_braking_rate
            )
            self.speed, average_speed = self._advance_toward(
                self.speed, self.target_speed, rate, delta_time
            )
            if self.speed == self.target_speed:
                self.target_speed = None

        self.lat, self.lon = NavigationalCoordinateSystem.calculate_new_position(
            self.lat, self.lon, average_speed, average_heading, delta_time
        )

    def update_heading(self, target_heading):
        """Command a turn to the target heading in degrees."""
        if not math.isfinite(target_heading):
            raise ValueError("Target heading must be finite")
        self.target_heading = target_heading % 360

    def update_altitude(self, target_altitude):
        """Command an altitude in hundreds of feet."""
        if not math.isfinite(target_altitude):
            raise ValueError("Target altitude must be finite")
        self.target_altitude = target_altitude

    def update_speed(self, target_speed):
        """Command a speed in knots."""
        self._validate_speed(target_speed, self.aircraft_model)
        self.target_speed = target_speed

    def update_squawk(self, squawk):
        """
        Update the squawk code of the aircraft.

        :param squawk: The new squawk code.
        :type squawk: str
        """
        self.squawk = squawk

    def climb(self, target_altitude):
        """
        Simulate aircraft climbing to a target altitude.

        :param target_altitude: The target altitude in hundreds of feet.
        :type target_altitude: float
        """
        self.update_altitude(target_altitude)

    def descend(self, target_altitude):
        """
        Simulate aircraft descending to a target altitude.

        :param target_altitude: The target altitude in hundreds of feet.
        :type target_altitude: float
        """
        self.update_altitude(target_altitude)

    def accelerate(self, target_speed):
        """
        Simulate aircraft accelerating to a target speed.

        :param target_speed: The target speed in knots.
        :type target_speed: float
        """
        self.update_speed(target_speed)

    def decelerate(self, target_speed):
        """
        Simulate aircraft decelerating to a target speed.

        :param target_speed: The target speed in knots.
        :type target_speed: float
        """
        self.update_speed(target_speed)


class AircraftList:
    """
    Manages a list of aircraft and updates their positions.
    """

    def __init__(self):
        self.aircraft_list = []
        self.atc_facility = None

    def add_aircraft(self, aircraft: list[Aircraft]) -> None:
        """
        Add aircraft to the list.

        :param aircraft: The aircraft to be added, in order.
        """
        self.aircraft_list.extend(aircraft)

    def update_positions(self, delta_time=1 / FPS):
        """
        Advance positions and ranges relative to the assigned facility.
        """
        if self.atc_facility is None:
            raise ValueError(
                "Assign the aircraft list to an ATC facility before updating positions"
            )
        for aircraft in self.aircraft_list:
            aircraft.on_ground(delta_time, self.atc_facility)

    def assign_to_atc_facility(self, atc_facility):
        """
        Assign all aircraft in the list to an ATC facility.

        :param atc_facility: The ATC facility to which the aircraft are assigned.
        :type atc_facility: ATCFacility
        """
        self.atc_facility = atc_facility
        for aircraft in self.aircraft_list:
            atc_facility.add_aircraft(aircraft)
