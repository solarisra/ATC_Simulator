from dataclasses import dataclass
from enum import StrEnum

SIMULATED_HANDOFF_DELAY_SECONDS = 3.0


class TrackingPosition(StrEnum):
    YUMA = "Y"
    LOS_ANGELES = "L"
    ALBUQUERQUE = "A"


class CoordinationKind(StrEnum):
    POINT_OUT = "POINT OUT"
    TRAFFIC = "TRAFFIC"


@dataclass
class Coordination:
    kind: CoordinationKind
    source: TrackingPosition
    target: TrackingPosition
    information: str
    approved: bool = False
    elapsed: float = 0.0


class TrackOwnership:
    def __init__(self):
        self.owner = TrackingPosition.YUMA
        self.communications_owner = TrackingPosition.YUMA
        self.handoff_target = None
        self.handoff_elapsed = 0.0
        self.handoff_information = ""
        self.identification_confirmation_due = False
        self.coordination = None
        self.coordination_history = []

    def offer(self, target, information=""):
        if not isinstance(target, TrackingPosition):
            raise TypeError("Invalid tracking position")
        if self.handoff_target is not None:
            raise ValueError("A handoff is already pending")
        if self.communications_owner != self.owner:
            raise ValueError("Complete the communications transfer first")
        if self.identification_confirmation_due:
            raise ValueError("Confirm incoming identification first")
        if self.coordination is not None and not self.coordination.approved:
            raise ValueError("Coordination is already pending")
        if target == self.owner or (
            self.owner != TrackingPosition.YUMA and target != TrackingPosition.YUMA
        ):
            raise ValueError("Handoffs must be between Yuma and a neighboring center")
        self.handoff_target = target
        self.handoff_elapsed = 0.0
        self.handoff_information = information

    def accept(self, position):
        if (
            not isinstance(position, TrackingPosition)
            or self.handoff_target is None
            or position != self.handoff_target
        ):
            raise ValueError("No handoff is pending for this position")
        incoming = position == TrackingPosition.YUMA
        self.owner = position
        self.handoff_target = None
        self.handoff_elapsed = 0.0
        self.identification_confirmation_due = incoming

    def cancel(self):
        if self.handoff_target is None:
            raise ValueError("No handoff is pending")
        self.handoff_target = None
        self.handoff_elapsed = 0.0
        self.handoff_information = ""

    def transfer_communications(self):
        if self.handoff_target is not None or self.owner == self.communications_owner:
            raise ValueError("No accepted handoff awaiting communications transfer")
        self.communications_owner = self.owner

    def confirm_identification(self):
        if not self.identification_confirmation_due:
            raise ValueError("No incoming identification confirmation due")
        self.identification_confirmation_due = False

    def offer_coordination(self, kind, target, information):
        if not isinstance(kind, CoordinationKind) or not isinstance(
            target, TrackingPosition
        ):
            raise TypeError("Invalid coordination kind or position")
        if not information.strip():
            raise ValueError("Enter coordination information")
        if kind == CoordinationKind.TRAFFIC and information.strip().upper() == "NONE":
            raise ValueError("Traffic coordination requires restrictions")
        if self.coordination is not None:
            raise ValueError("Close the existing coordination first")
        if self.handoff_target is not None:
            raise ValueError("A handoff is already pending")
        if target == self.owner or (
            self.owner != TrackingPosition.YUMA and target != TrackingPosition.YUMA
        ):
            raise ValueError("Coordinate between Yuma and a neighboring center")
        self.coordination = Coordination(kind, self.owner, target, information.strip())

    def accept_coordination(self, position):
        item = self.coordination
        if item is None or item.approved or position != item.target:
            raise ValueError("No coordination is pending for this position")
        item.approved = True

    def close_coordination(self):
        if self.coordination is None:
            raise ValueError("No coordination to close")
        self.coordination_history.append(self.coordination)
        self.coordination = None

    def advance_coordination(self, delta_time):
        item = self.coordination
        if item is None or item.approved or item.source != TrackingPosition.YUMA:
            return False
        item.elapsed += delta_time
        if item.elapsed < SIMULATED_HANDOFF_DELAY_SECONDS:
            return False
        self.accept_coordination(item.target)
        return True

    def advance(self, delta_time):
        if self.owner != TrackingPosition.YUMA or self.handoff_target is None:
            return False
        self.handoff_elapsed += delta_time
        if self.handoff_elapsed < SIMULATED_HANDOFF_DELAY_SECONDS:
            return False
        self.accept(self.handoff_target)
        return True


class ATCFacility:
    """
    Represents an ATC (Air Traffic Control) facility.
    """

    def __init__(
        self,
        name,
        location,
        facilities=None,
        airport_code=None,
        upper_control_flight_level=None,
        upper_control_center=None,
    ):
        self.name = name
        self.location = location
        self.airport_code = airport_code
        self.upper_control_flight_level = upper_control_flight_level
        self.upper_control_center = upper_control_center
        self.active_runways: tuple[str, ...] = ()
        self.helicopter_pads: tuple[str, ...] = ()
        self.facilities = facilities if facilities is not None else []
        self.aircraft_list = []

    def above_control_limit(self, altitude):
        return (
            self.upper_control_flight_level is not None
            and altitude > self.upper_control_flight_level
        )

    def add_aircraft(self, aircraft):
        """
        Add an aircraft to the ATC facility.
        """
        self.aircraft_list.append(aircraft)

    def remove_aircraft(self, aircraft):
        """
        Remove an aircraft from the ATC facility.
        """
        self.aircraft_list.remove(aircraft)

    def manage_flight_plans(self):
        """
        Manage the flight plans for all aircraft in the facility.
        """
        for aircraft in self.aircraft_list:
            # Placeholder for managing flight plans
            pass

    @staticmethod
    def get_atc_facility_by_name(name):
        """
        Get an ATC facility by its name.
        """
        facilities = {
            "KNYL": ATCFacility(
                "MCAS Yuma",
                {"lat": 32.6566, "lon": -114.6056},
                airport_code="KNYL",
                upper_control_flight_level=230,
                upper_control_center=TrackingPosition.LOS_ANGELES,
            ),
            # Add more facilities as needed
        }
        return facilities.get(name)


class ATCFacilityFrequencies:
    """
    Represents the frequencies used by an ATC facility.
    """

    def __init__(self, facility, frequencies=None):
        self.facility = facility
        self.frequencies = frequencies if frequencies is not None else []


class ATC:
    """
    Represents an ATC role within a facility.
    """

    def __init__(self, role, facility):
        self.role = role
        self.facility = facility

    def manage_aircraft(self):
        """
        Manage aircraft within the ATC facility.
        """
        self.facility.manage_flight_plans()

    def set_facility(self, facility_name):
        """
        Set the ATC facility.
        """
        self.facility = ATCFacility.get_atc_facility_by_name(facility_name)


class FlightPlate:
    """
    Represents a flight plate for navigation procedures.
    """

    def __init__(self, plate_type, airport, procedure):
        self.plate_type = plate_type  # Approach, Departure, etc.
        self.airport = airport
        self.procedure = procedure


class RadarMap:
    """
    Represents a radar map for a specific area.
    """

    def __init__(self, area, map_data):
        self.area = area
        self.map_data = map_data


class AirportDiagram:
    """
    Represents an airport diagram.
    """

    def __init__(self, airport, diagram_data):
        self.airport = airport
        self.diagram_data = diagram_data


class NavigationAid:
    """
    Represents a navigation aid.
    """

    def __init__(self, name, navaid_type, location, frequency):
        self.name = name
        self.navaid_type = navaid_type  # VOR, NDB, ILS, etc.
        self.location = location
        self.frequency = frequency


class FlightStrip:
    """
    Represents a flight strip for tracking flight information.
    """

    def __init__(self, flight_id, aircraft, flight_plan):
        self.flight_id = flight_id
        self.aircraft = aircraft
        self.flight_plan = flight_plan
        self.active = True
        self.beacon_code = aircraft.squawk
        self.operation_area = ""
        self.assigned_altitude = ""
        self.fix_time = ""
        self.remarks = ""


class FlightPlan:
    """
    Represents a flight plan.
    """

    def __init__(self, flight_id, origin, destination, route, altitude, speed):
        self.flight_id = flight_id
        self.origin = origin
        self.destination = destination
        self.route = route
        self.altitude = altitude
        self.speed = speed

    def update_route(self, new_route):
        """
        Update the flight route.

        :param new_route: The new route for the flight.
        :type new_route: str
        """
        self.route = new_route


class Weather:
    """
    Represents weather information for a specific location.
    """

    def __init__(self, location, temperature, wind, visibility, conditions):
        self.location = location
        self.temperature = temperature
        self.wind = wind
        self.visibility = visibility
        self.conditions = conditions
