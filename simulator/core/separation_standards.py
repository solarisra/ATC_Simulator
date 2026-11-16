"""FAA 7110.65 separation minima standards and validation."""

from dataclasses import dataclass
from enum import Enum


class AircraftCategory(Enum):
    """Aircraft categories per 7110.65 wake turbulence separation."""

    A = "A"  # Heavy (max certificated takeoff weight 300,000+ lbs)
    B = "B"  # Large (max certificated takeoff weight 41,000-300,000 lbs)
    C = "C"  # Large (max certificated takeoff weight 41,000-300,000 lbs) with specific specs
    D = "D"  # Small (max certificated takeoff weight 15,000-41,000 lbs)
    E = "E"  # Small (max certificated takeoff weight 15,000-41,000 lbs)
    F = "F"  # Small (max certificated takeoff weight 15,000-41,000 lbs) or some larger military
    G = "G"  # Small (max certificated takeoff weight 15,000-41,000 lbs) or some larger military
    H = "H"  # Helicopter
    I = "I"  # Rotorcraft (helicopter)


@dataclass(frozen=True)
class SeparationMinima:
    """Radar and nonradar separation minima from 7110.65."""

    # Radar separation minima (NM) - Ch 5 Section 5
    radar_lateral_minima = {
        # Wake turbulence separation table (5-5-4 TBL 5-5-1)
        # Format: (leader_category, follower_category): minimum_nm
        (AircraftCategory.A, AircraftCategory.B): 5,
        (AircraftCategory.A, AircraftCategory.C): 6,
        (AircraftCategory.A, AircraftCategory.D): 6,
        (AircraftCategory.A, AircraftCategory.E): 7,
        (AircraftCategory.A, AircraftCategory.F): 7,
        (AircraftCategory.A, AircraftCategory.G): 7,
        (AircraftCategory.A, AircraftCategory.H): 8,
        (AircraftCategory.A, AircraftCategory.I): 8,
        (AircraftCategory.B, AircraftCategory.C): 3,
        (AircraftCategory.B, AircraftCategory.D): 4,
        (AircraftCategory.B, AircraftCategory.E): 4,
        (AircraftCategory.B, AircraftCategory.F): 5,
        (AircraftCategory.B, AircraftCategory.G): 5,
        (AircraftCategory.B, AircraftCategory.H): 5,
        (AircraftCategory.B, AircraftCategory.I): 5,
        (AircraftCategory.C, AircraftCategory.E): 3.5,
        (AircraftCategory.C, AircraftCategory.F): 3.5,
        (AircraftCategory.C, AircraftCategory.G): 3.5,
        (AircraftCategory.C, AircraftCategory.H): 5,
        (AircraftCategory.C, AircraftCategory.I): 5,
        (AircraftCategory.D, AircraftCategory.C): 3,
        (AircraftCategory.D, AircraftCategory.D): 4,
        (AircraftCategory.D, AircraftCategory.E): 4,
        (AircraftCategory.D, AircraftCategory.F): 5,
        (AircraftCategory.D, AircraftCategory.G): 5,
        (AircraftCategory.D, AircraftCategory.H): 5,
        (AircraftCategory.D, AircraftCategory.I): 5,
        (AircraftCategory.E, AircraftCategory.I): 4,
    }

    # Vertical separation minima: 1000 feet (standard for radar)
    # Can be reduced to 500 feet only with specific aircraft equipment/procedures
    radar_vertical_minima = 1000  # feet

    # Nonradar separation minima - Ch 6
    # Time-based separations (minutes) for nonradar operations
    nonradar_time_minima = {
        # Format: (leader_category, follower_category): (minutes, description)
        (AircraftCategory.A, AircraftCategory.B): (5, "Heavy behind heavy"),
        (AircraftCategory.A, AircraftCategory.C): (5, "Heavy behind heavy"),
        (AircraftCategory.A, AircraftCategory.D): (5, "Heavy behind heavy"),
        (AircraftCategory.A, AircraftCategory.E): (5, "Heavy behind heavy"),
        (AircraftCategory.B, AircraftCategory.D): (3, "Large behind large"),
        (AircraftCategory.B, AircraftCategory.E): (3, "Large behind large"),
        (AircraftCategory.D, AircraftCategory.B): (2, "Small behind large"),
        (AircraftCategory.E, AircraftCategory.A): (3, "Small behind heavy"),
        (AircraftCategory.H, AircraftCategory.A): (4, "Helicopter behind heavy"),
        (AircraftCategory.I, AircraftCategory.E): (3, "Rotorcraft behind small"),
    }

    # Distance-based separations (NM) for nonradar operations
    nonradar_distance_minima = {
        # Format: (leader_category, follower_category): (nm, description)
        (AircraftCategory.B, AircraftCategory.D): (4, "Large to small"),
        (AircraftCategory.B, AircraftCategory.E): (4, "Large to small"),
        (AircraftCategory.D, AircraftCategory.D): (3, "Same category"),
        (AircraftCategory.E, AircraftCategory.E): (3, "Same category"),
        (AircraftCategory.A, AircraftCategory.H): (8, "Heavy before helicopter"),
        (AircraftCategory.H, AircraftCategory.D): (5, "Helicopter behind small"),
        (AircraftCategory.I, AircraftCategory.E): (6, "Rotorcraft behind small"),
    }

    # Minimum distance in NM for all radar operations
    minimum_radar_distance = 3

    @classmethod
    def get_radar_separation(
        cls, leader_category: AircraftCategory, follower_category: AircraftCategory
    ) -> float:
        """Get radar separation minima in NM between two aircraft.
        
        Args:
            leader_category: Category of leading aircraft
            follower_category: Category of following aircraft
            
        Returns:
            Minimum separation in nautical miles. Returns minimum_radar_distance
            if no specific minima exists (same category).
        """
        return cls.radar_lateral_minima.get(
            (leader_category, follower_category), cls.minimum_radar_distance
        )

    @classmethod
    def get_nonradar_time_separation(
        cls, leader_category: AircraftCategory, follower_category: AircraftCategory
    ) -> float | None:
        """Get time-based nonradar separation minima.
        
        Args:
            leader_category: Category of leading aircraft
            follower_category: Category of following aircraft
            
        Returns:
            Minimum separation in minutes, or None if not applicable.
        """
        result = cls.nonradar_time_minima.get((leader_category, follower_category))
        return result[0] if result else None

    @classmethod
    def get_nonradar_distance_separation(
        cls, leader_category: AircraftCategory, follower_category: AircraftCategory
    ) -> float | None:
        """Get distance-based nonradar separation minima.
        
        Args:
            leader_category: Category of leading aircraft
            follower_category: Category of following aircraft
            
        Returns:
            Minimum separation in nautical miles, or None if not applicable.
        """
        result = cls.nonradar_distance_minima.get((leader_category, follower_category))
        return result[0] if result else None


def map_model_to_category(aircraft_type: str) -> AircraftCategory:
    """Map aircraft model type to FAA wake turbulence category.
    
    Args:
        aircraft_type: Aircraft model type (e.g., 'B737', 'C172', 'H60')
        
    Returns:
        AircraftCategory based on MTOW and characteristics per 7110.65
    """
    # Heavy aircraft (MTOW >= 300,000 lbs)
    if aircraft_type in {"B767", "B52", "B777"}:
        return AircraftCategory.A

    # Large aircraft (MTOW 41,000-300,000 lbs)
    if aircraft_type in {"B737", "A320", "A380"}:
        return AircraftCategory.B

    # Small aircraft (MTOW 15,000-41,000 lbs)
    if aircraft_type in {"C208", "CE25", "M2"}:
        return AircraftCategory.D

    # Very small aircraft (MTOW <= 15,000 lbs)
    if aircraft_type in {"C172", "PA28"}:
        return AircraftCategory.E

    # Military jets (various sizes; use large as default)
    if aircraft_type in {"F16", "F18", "F35", "AV8"}:
        return AircraftCategory.B

    # Helicopters
    if aircraft_type in {"H135", "H60", "H46", "H53", "V22"}:
        return AircraftCategory.H

    # Default to small category
    return AircraftCategory.E
