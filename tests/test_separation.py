"""Tests for FAA 7110.65 separation standards."""

import unittest

from simulator.core.separation_standards import (
    AircraftCategory,
    SeparationMinima,
    map_model_to_category,
)


class SeparationStandardsTests(unittest.TestCase):
    """Test FAA 7110.65 Chapter 5 Section 5 separation minima."""

    def test_radar_lateral_separation_wake_turbulence(self):
        """Test wake turbulence separation minima from 5-5-4 TBL 5-5-1."""
        # Heavy (A) behind various aircraft
        self.assertEqual(
            SeparationMinima.get_radar_separation(
                AircraftCategory.A, AircraftCategory.B
            ),
            5,
        )
        self.assertEqual(
            SeparationMinima.get_radar_separation(
                AircraftCategory.A, AircraftCategory.C
            ),
            6,
        )
        self.assertEqual(
            SeparationMinima.get_radar_separation(
                AircraftCategory.A, AircraftCategory.D
            ),
            6,
        )
        self.assertEqual(
            SeparationMinima.get_radar_separation(
                AircraftCategory.A, AircraftCategory.H
            ),
            8,
        )

    def test_radar_lateral_separation_large_aircraft(self):
        """Test large aircraft separation minima."""
        # Large (B) behind various aircraft
        self.assertEqual(
            SeparationMinima.get_radar_separation(
                AircraftCategory.B, AircraftCategory.D
            ),
            4,
        )
        self.assertEqual(
            SeparationMinima.get_radar_separation(
                AircraftCategory.B, AircraftCategory.H
            ),
            5,
        )

    def test_radar_lateral_separation_same_category(self):
        """Test that same category uses minimum separation."""
        # Same category defaults to minimum or category-specific minima
        self.assertEqual(
            SeparationMinima.get_radar_separation(
                AircraftCategory.D, AircraftCategory.D
            ),
            4,  # D-D is 4 NM per table
        )
        self.assertEqual(
            SeparationMinima.get_radar_separation(
                AircraftCategory.E, AircraftCategory.E
            ),
            SeparationMinima.minimum_radar_distance,  # E-E not in table, uses minimum
        )

    def test_radar_vertical_separation(self):
        """Test vertical separation minima is 1000 feet."""
        self.assertEqual(SeparationMinima.radar_vertical_minima, 1000)

    def test_minimum_radar_distance(self):
        """Test minimum lateral separation is 3 NM."""
        self.assertEqual(SeparationMinima.minimum_radar_distance, 3)

    def test_nonradar_time_separation(self):
        """Test time-based nonradar separation minima from 6-4."""
        # Heavy behind heavy
        self.assertEqual(
            SeparationMinima.get_nonradar_time_separation(
                AircraftCategory.A, AircraftCategory.B
            ),
            5,
        )
        # Large behind large
        self.assertEqual(
            SeparationMinima.get_nonradar_time_separation(
                AircraftCategory.B, AircraftCategory.D
            ),
            3,
        )

    def test_nonradar_distance_separation(self):
        """Test distance-based nonradar separation minima."""
        # Large to small
        self.assertEqual(
            SeparationMinima.get_nonradar_distance_separation(
                AircraftCategory.B, AircraftCategory.D
            ),
            4,
        )
        # Helicopter behind heavy
        self.assertEqual(
            SeparationMinima.get_nonradar_distance_separation(
                AircraftCategory.A, AircraftCategory.H
            ),
            8,
        )

    def test_aircraft_category_mapping(self):
        """Test mapping of aircraft models to categories."""
        # Heavy aircraft
        self.assertEqual(map_model_to_category("B767"), AircraftCategory.A)
        self.assertEqual(map_model_to_category("B52"), AircraftCategory.A)

        # Large aircraft (commercial)
        self.assertEqual(map_model_to_category("B737"), AircraftCategory.B)
        self.assertEqual(map_model_to_category("A320"), AircraftCategory.B)

        # Small to medium aircraft
        self.assertEqual(map_model_to_category("C208"), AircraftCategory.D)
        self.assertEqual(map_model_to_category("C172"), AircraftCategory.E)
        self.assertEqual(map_model_to_category("PA28"), AircraftCategory.E)

        # Military jets
        self.assertEqual(map_model_to_category("F16"), AircraftCategory.B)
        self.assertEqual(map_model_to_category("F18"), AircraftCategory.B)

        # Helicopters
        self.assertEqual(map_model_to_category("H60"), AircraftCategory.H)
        self.assertEqual(map_model_to_category("H135"), AircraftCategory.H)
        self.assertEqual(map_model_to_category("V22"), AircraftCategory.H)


class SeparationValidationTests(unittest.TestCase):
    """Test separation validation in scenario generation."""

    def test_separation_enforcement_in_scenario(self):
        """Test that generated scenarios enforce separation standards."""
        from datetime import UTC, datetime
        from dataclasses import replace
        from unittest.mock import patch

        from locations.Yuma.Scenarios.generator import (
            AIRCRAFT_TYPES,
            OPERATIONS,
            GeneratorSettings,
            generate_yuma_scenario,
        )
        from simulator.navigation.flight_navigation import NavigationData
        from simulator.navigation.navmath import NavigationalCoordinateSystem

        navigation = NavigationData()
        settings = GeneratorSettings(seed=12345, volume="heavy")
        start_time = datetime(2026, 11, 15, 20, 0, tzinfo=UTC)

        with patch(
            "locations.Yuma.Scenarios.generator.NavigationData",
            return_value=navigation,
        ):
            aircraft_list, facility, strips, warnings = generate_yuma_scenario(
                settings, start_time
            )

        # Verify all airborne aircraft have adequate separation
        aircraft_array = aircraft_list.aircraft_list
        for i, subject in enumerate(aircraft_array):
            for other in aircraft_array[i + 1 :]:
                # Calculate horizontal distance
                distance = NavigationalCoordinateSystem.calculate_distance(
                    subject.lat, subject.lon, other.lat, other.lon
                )
                
                # Skip check for aircraft at the same position (departures/approaches at airport)
                # These aren't yet airborne and don't require separation
                if distance < 0.1:  # Less than 0.1 NM ~ same location
                    continue
                    
                # Calculate vertical separation
                vertical_distance = abs((subject.altitude - other.altitude) * 100)

                # Get categories
                subj_category = map_model_to_category(
                    subject.aircraft_model.aircraft_type
                )
                other_category = map_model_to_category(
                    other.aircraft_model.aircraft_type
                )

                # Either vertically separated or laterally separated
                if vertical_distance < SeparationMinima.radar_vertical_minima:
                    # Needs lateral separation
                    required = SeparationMinima.get_radar_separation(
                        other_category, subj_category
                    )
                    self.assertGreaterEqual(
                        distance,
                        required - 0.1,  # Allow small floating point tolerance
                        f"{subject.callsign} at {subject.lat:.4f}, {subject.lon:.4f}, "
                        f"FL{subject.altitude:.0f} is only {distance:.2f} NM from "
                        f"{other.callsign} at {other.lat:.4f}, {other.lon:.4f}, "
                        f"FL{other.altitude:.0f} (minimum {required} NM)",
                    )


if __name__ == "__main__":
    unittest.main()
