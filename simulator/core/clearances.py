"""Shared validation and execution of simulated controller clearances."""

from simulator.core.atc import TrackingPosition


def is_airborne(aircraft):
    departure = getattr(aircraft, "departure", None)
    return not aircraft.landed and (departure is None or departure.airborne)


def clearance_control_error(aircraft, facility):
    if not is_airborne(aircraft):
        return "Aircraft is not airborne"
    if (
        aircraft.track.owner != TrackingPosition.YUMA
        or aircraft.track.communications_owner != TrackingPosition.YUMA
    ):
        return "Yuma must own track and communications"
    if aircraft.track.identification_confirmation_due:
        return "Confirm incoming identification first"
    if aircraft.track.handoff_target is not None:
        return "Complete or cancel the pending handoff"
    if facility.above_control_limit(aircraft.altitude):
        return "Aircraft is above Yuma control limit"
    if aircraft.flight_guidance is None:
        return "Aircraft has no flight plan guidance"
    return None


def execute_clearance(aircraft, facility, text, *, turn_direction=None):
    error = clearance_control_error(aircraft, facility)
    if error is not None:
        raise ValueError(error)
    guidance = aircraft.flight_guidance
    guidance._refresh_route(aircraft)
    parts = text.upper().split()
    if turn_direction is not None and not (
        len(parts) == 2 and parts[0] == "HDG" and parts[1].isdigit()
    ):
        raise ValueError("Turn direction applies only to a heading clearance")
    if len(parts) == 2 and parts[0] == "HDG" and parts[1].isdigit():
        heading = int(parts[1])
        guidance.assign_heading(heading, turn_direction)
        return f"HEADING {heading:03d} TRUE"
    if len(parts) == 2 and parts[0] == "ALT" and parts[1].isdigit():
        altitude = int(parts[1])
        if facility.above_control_limit(altitude / 100):
            raise ValueError("Altitude is above Yuma control limit")
        guidance.assign_altitude(altitude)
        return f"MAINTAIN {altitude} FT"
    if parts == ["ALT", "CLR"]:
        guidance.clear_altitude()
        return f"RESUME FILED ALTITUDE {guidance.strip.flight_plan.altitude} FT"
    if len(parts) == 2 and parts[0] == "DCT":
        guidance.direct_to(parts[1])
        return f"DIRECT {parts[1]}, THEN FLIGHT PLAN"
    if parts == ["RESUME"]:
        guidance.resume_route()
        return f"RESUME FLIGHT PLAN DIRECT {guidance.route[guidance.next_index].name}"
    raise ValueError("USE HDG nnn, ALT feet, ALT CLR, DCT fix OR RESUME")
