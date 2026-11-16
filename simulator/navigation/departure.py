from datetime import datetime

from simulator.core.aircraft import display_callsign


class Departure:
    """Simplified automatic ground wait, takeoff, and pilot check-in."""

    def __init__(self, strip, airport, delay, location):
        aircraft = strip.aircraft
        if airport.elevation is None:
            raise ValueError(f"Missing departure airport elevation for {aircraft.id}")
        if aircraft.aircraft_model.thrust_rate <= 0 or aircraft.speed <= 0:
            raise ValueError(f"{aircraft.id} cannot accelerate for departure")
        if aircraft.aircraft_model.climb_rate <= 0:
            raise ValueError(f"{aircraft.id} cannot climb after departure")
        stall_speed = aircraft.aircraft_model.stall_speed
        self.takeoff_speed = 1.2 * stall_speed if stall_speed is not None else 0
        if aircraft.speed < self.takeoff_speed:
            raise ValueError(f"{aircraft.id} departure speed is below takeoff speed")
        self.cruise_speed = aircraft.speed
        self.liftoff_altitude = airport.elevation / 100 + 0.5
        self.strip = strip
        self.delay = delay
        self.state = "waiting"
        self.elapsed = 0.0
        self.airborne_elapsed = 0.0
        self.check_in = None
        self.check_in_time = None
        self.scheduled_utc: datetime | None = None
        matching = [
            frequency
            for frequency in location.radio_frequencies
            if frequency.identifier == aircraft.radio_channel
        ]
        if len(matching) != 1 or not matching[0].frequency:
            raise ValueError(f"No departure frequency configured for {aircraft.id}")
        self.frequency = matching[0].frequency

        aircraft.lat, aircraft.lon = airport.latitude, airport.longitude
        aircraft.altitude = airport.elevation / 100
        aircraft.speed = 0
        aircraft.distance = 0
        self.align_runway_heading(location)

    def align_runway_heading(self, location):
        aircraft = self.strip.aircraft
        if self.strip.operation_area in ("03L", "03R"):
            aircraft.heading = location.magnetic_to_true(30)
        elif self.strip.operation_area in ("21L", "21R"):
            aircraft.heading = location.magnetic_to_true(210)
        elif self.strip.operation_area == "35":
            aircraft.heading = location.magnetic_to_true(350)

    @property
    def airborne(self):
        return self.state == "airborne"

    def advance(self, aircraft, delta_time):
        self.elapsed += delta_time
        remaining = delta_time
        if self.state == "waiting":
            waiting = min(self.delay, remaining)
            self.delay -= waiting
            remaining -= waiting
            if self.delay > 0:
                return 0
            self.state = "takeoff"
            if self.takeoff_speed:
                aircraft.update_speed(self.cruise_speed)
        if self.state == "takeoff":
            if self.takeoff_speed:
                duration = (
                    self.takeoff_speed - aircraft.speed
                ) / aircraft.aircraft_model.thrust_rate
            else:
                duration = (self.liftoff_altitude - aircraft.altitude) / (
                    aircraft.aircraft_model.climb_rate / 100
                )
                aircraft.update_altitude(self.liftoff_altitude)
            takeoff_time = min(remaining, duration)
            if takeoff_time > 0:
                aircraft._advance_position(takeoff_time)
                remaining -= takeoff_time
            if takeoff_time < duration:
                return 0
            self.state = "airborne"
            if not self.takeoff_speed:
                aircraft.update_speed(self.cruise_speed)
        return remaining

    def record_airborne(self, aircraft, delta_time):
        self.airborne_elapsed += delta_time
        if self.check_in is None and self.airborne_elapsed >= 15:
            altitude = round(aircraft.altitude) * 100
            assigned = aircraft.flight_guidance.assigned_altitude
            target = (
                assigned if assigned is not None else self.strip.flight_plan.altitude
            )
            if target > altitude:
                status = f"CLIMBING {target} FT"
            elif target < altitude:
                status = f"DESCENDING {target} FT"
            else:
                status = f"LEVEL {target} FT"
            self.check_in = (
                f"{display_callsign(aircraft)}: YUMA DEPARTURE, ON {self.frequency}, "
                f"{altitude} FT, {status}"
            )
            self.check_in_time = self.elapsed
