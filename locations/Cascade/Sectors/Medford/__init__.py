"""Medford sector location data, based on the 29 October 2026 FAA listing."""

from simulator.core.location import (
    AirportDiagram,
    FlightPlate,
    Location,
    RadioFrequency,
    RadioState,
)


def create_location():
    return Location(
        name="Cascade Approach - Medford Sector",
        latitude=42.3749647,
        longitude=-122.8732875,
        elevation_ft=1335.3,
        magnetic_declination_degrees=13 + 15 / 60,
        active_runways=("32",),
        airport_diagram=AirportDiagram(
            "KMFR", "https://aeronav.faa.gov/d-tpp/2611/00251AD.PDF"
        ),
        approach_procedures=tuple(
            FlightPlate("approach", "KMFR", name)
            for name in (
                "ILS OR LOC RWY 14",
                "RNAV (RNP) Z RWY 14",
                "RNAV (RNP) Z RWY 32",
                "RNAV (GPS) Y RWY 14",
                "RNAV (GPS) Y RWY 32",
                "RNAV (GPS)-D",
                "LOC/DME BC-B",
                "VOR/DME RWY 14",
                "VOR/DME-C",
                "VOR-A",
            )
        ),
        departure_procedures=tuple(
            FlightPlate("departure", "KMFR", name)
            for name in (
                "BLAAZ ONE (RNAV)",
                "EAGLE SIX",
                "JACKSON ONE",
                "KLAMATH FALLS ONE (RNAV)",
            )
        ),
        emergency_frequencies=(
            RadioFrequency(
                "emergency_low", "EMERGENCY", "VHF", "121.500", RadioState.LISTEN
            ),
            RadioFrequency(
                "emergency_high", "EMERGENCY", "UHF", "243.000", RadioState.LISTEN
            ),
        ),
        internal_frequencies=(
            RadioFrequency("tower_low", "MFR TWR", "VHF", "119.400"),
            RadioFrequency("tower_high", "MFR TWR", "UHF", "257.800"),
            RadioFrequency("approach_low", "CASCADE APP/DEP", "VHF", "124.300"),
        ),
        neighbor_frequencies=(
            RadioFrequency("zse_king_low", "ZSE KING MTN", "VHF", "124.850"),
            RadioFrequency("zse_king_high", "ZSE KING MTN", "UHF", "306.300"),
        ),
    )
