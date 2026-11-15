"""Yuma location configuration."""

from simulator.core.location import Location, RadioFrequency, RadioState


def create_location():
    return Location(
        name="MCAS Yuma",
        latitude=32.6566,
        longitude=-114.6056,
        elevation_ft=213.3,
        emergency_frequencies=(
            RadioFrequency(
                "emergency_low", "EMERGENCY", "VHF", "121.500", RadioState.LISTEN
            ),
            RadioFrequency(
                "emergency_high", "EMERGENCY", "UHF", "243.000", RadioState.LISTEN
            ),
        ),
        internal_frequencies=(
            RadioFrequency("tower_low", "KNYL TWR", "VHF", "119.300"),
            RadioFrequency("tower_high", "KNYL TWR", "UHF", "377.075"),
            RadioFrequency("approach_low", "KNYL APP", "VHF", "124.700", RadioState.ON),
            RadioFrequency("approach_high", "KNYL APP", "UHF", "371.975"),
            RadioFrequency("departure_low", "KNYL DEP", "VHF", "125.500"),
            RadioFrequency("departure_high", "KNYL DEP", "UHF", "282.325"),
            RadioFrequency("enroute_low", "KNYL ENR", "VHF", "132.275"),
            RadioFrequency("enroute_high", "KNYL ENR", "UHF", "292.200"),
        ),
        neighbor_frequencies=(
            RadioFrequency("zla9_low", "ZLA SEC 9", "VHF", "128.600"),
            RadioFrequency("zla9_high", "ZLA SEC 9", "UHF", "291.700"),
            RadioFrequency("zla10_low", "ZLA SEC 10", "VHF", "128.150"),
            RadioFrequency("zla10_high", "ZLA SEC 10", "UHF", "285.600"),
            RadioFrequency("zla31_low", "ZLA SEC 31", "VHF", "126.775"),
            RadioFrequency("zla31_high", "ZLA SEC 31", "UHF", "307.800"),
            RadioFrequency("zab42_low", "ZAB SEC 42", "VHF", "125.250"),
            RadioFrequency("zab42_high", "ZAB SEC 42", "UHF", "307.300"),
        ),
    )
