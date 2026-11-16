"""Location and radio configuration shared by facilities and scenarios."""

import math
from dataclasses import dataclass
from enum import StrEnum


class RadioState(StrEnum):
    OFF = "OFF"
    LISTEN = "LISTEN"
    ON = "ON"


@dataclass(frozen=True)
class RadioFrequency:
    identifier: str
    label: str
    band: str
    frequency: str
    initial_state: RadioState = RadioState.OFF


class FlightPlate:
    """A navigation procedure associated with an airport."""

    def __init__(self, plate_type, airport, procedure):
        self.plate_type = plate_type
        self.airport = airport
        self.procedure = procedure


class AirportDiagram:
    """Airport diagram data, when available."""

    def __init__(self, airport, diagram_data):
        self.airport = airport
        self.diagram_data = diagram_data


@dataclass
class Location:
    name: str
    latitude: float
    longitude: float
    elevation_ft: float | None = None
    active_runways: tuple[str, ...] = ()
    helicopter_pads: tuple[str, ...] = ()
    airport_diagram: AirportDiagram | None = None
    approach_procedures: tuple[FlightPlate, ...] = ()
    departure_procedures: tuple[FlightPlate, ...] = ()
    emergency_frequencies: tuple[RadioFrequency, ...] = ()
    internal_frequencies: tuple[RadioFrequency, ...] = ()
    neighbor_frequencies: tuple[RadioFrequency, ...] = ()
    coordination_lines: tuple[tuple[str, str], ...] = ()
    magnetic_declination_degrees: float | None = None

    def __getitem__(self, key):
        return {"lat": self.latitude, "lon": self.longitude}[key]

    def _declination(self) -> float:
        if self.magnetic_declination_degrees is None or not math.isfinite(
            self.magnetic_declination_degrees
        ):
            raise ValueError(f"Magnetic declination is not configured for {self.name}")
        return self.magnetic_declination_degrees

    def magnetic_to_true(self, heading: float) -> float:
        if not math.isfinite(heading):
            raise ValueError("Heading must be finite")
        return (heading + self._declination()) % 360

    def true_to_magnetic(self, heading: float) -> float:
        if not math.isfinite(heading):
            raise ValueError("Heading must be finite")
        return (heading - self._declination()) % 360

    @property
    def radio_frequencies(self):
        return (
            self.emergency_frequencies
            + self.internal_frequencies
            + self.neighbor_frequencies
        )
