"""Versioned JSON snapshots of a running Yuma scenario."""

import json
import math
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from Locations.Yuma.Scenarios.generator import GeneratorSettings
from simulator.core import aircraft_models
from simulator.core.aircraft import Aircraft, AircraftList, AircraftModel
from simulator.core.atc import (
    ATCFacility,
    Coordination,
    CoordinationKind,
    FlightPlan,
    FlightStrip,
    RadarControlState,
    TrackingPosition,
)
from simulator.core.location import RadioState
from simulator.navigation.departure import Departure
from simulator.navigation.flight_navigation import (
    FlightPlanGuidance,
    NavigationData,
    Waypoint,
)

SAVE_DIRECTORY = Path.home() / ".atc_simulator" / "scenarios"
VERSION = 1
AIRCRAFT_FIELDS = (
    "id",
    "squawk",
    "mode_s",
    "callsign",
    "heading",
    "altitude",
    "speed",
    "distance",
    "lat",
    "lon",
    "flight_rules",
    "landed",
    "scratchpad",
    "target_heading",
    "target_turn_direction",
    "target_altitude",
    "target_speed",
    "radio_channel",
)
STRIP_FIELDS = (
    "active",
    "beacon_code",
    "operation_area",
    "assigned_altitude",
    "fix_time",
    "remarks",
)
TRACK_FIELDS = (
    "owner",
    "communications_owner",
    "handoff_target",
    "handoff_elapsed",
    "handoff_information",
    "identification_confirmation_due",
)
GUIDANCE_FIELDS = (
    "next_index",
    "approach",
    "vector_heading",
    "vector_turn_direction",
    "assigned_altitude",
)
DEPARTURE_FIELDS = (
    "takeoff_speed",
    "cruise_speed",
    "liftoff_altitude",
    "delay",
    "state",
    "elapsed",
    "airborne_elapsed",
    "check_in",
    "check_in_time",
    "frequency",
)


@dataclass
class RestoredScenario:
    aircraft: AircraftList
    facility: ATCFacility
    strips: list[FlightStrip]
    time: datetime
    settings: GeneratorSettings | None
    radios: dict[str, RadioState]
    lines: dict[str, bool]
    checkins: list[str]
    reported_departures: set[str]


def _fields(obj, names):
    return {name: getattr(obj, name) for name in names}


def _coordination(item):
    return asdict(item) if item is not None else None


def snapshot_scenario(
    aircraft, facility, strips, time, settings, communications, checkins, reported
):
    if facility.airport_code != "KNYL" or time is None:
        raise ValueError("Only a running Yuma scenario can be saved")
    if time.tzinfo is None or time.utcoffset() is None:
        raise ValueError("Scenario time must include a UTC offset")
    by_id = {strip.flight_id: strip for strip in strips}
    if len(by_id) != len(strips) or set(by_id) != {
        item.id for item in aircraft.aircraft_list
    }:
        raise ValueError("Each aircraft must have one flight strip")
    records = []
    for plane in aircraft.aircraft_list:
        strip = by_id[plane.id]
        if strip.aircraft is not plane:
            raise ValueError(f"Strip does not match aircraft {plane.id}")
        track = _fields(plane.track, TRACK_FIELDS)
        track["radar_control_state"] = plane.track.radar_control_state.value
        track["pending_radio_channel"] = plane.track.pending_radio_channel
        track["coordination"] = _coordination(plane.track.coordination)
        track["coordination_history"] = [
            _coordination(item) for item in plane.track.coordination_history
        ]
        guidance = plane.flight_guidance
        if guidance is None:
            raise ValueError(f"No flight guidance for {plane.id}")
        nav = _fields(guidance, GUIDANCE_FIELDS)
        nav["signature"] = guidance.signature
        nav["route"] = [asdict(point) for point in guidance.route]
        departure = plane.departure
        dep = None
        if departure is not None:
            dep = _fields(departure, DEPARTURE_FIELDS)
            dep["scheduled_utc"] = (
                departure.scheduled_utc.isoformat() if departure.scheduled_utc else None
            )
        records.append(
            {
                "aircraft": {
                    **_fields(plane, AIRCRAFT_FIELDS),
                    "ident_remaining": plane.ident_remaining,
                },
                "model": plane.aircraft_model.aircraft_type,
                "track": track,
                "guidance": nav,
                "departure": dep,
                "strip": {
                    **_fields(strip, STRIP_FIELDS),
                    "offset_right": strip.offset_right,
                    "discarded": strip.discarded,
                },
                "plan": _fields(
                    strip.flight_plan,
                    ("origin", "destination", "route", "altitude", "speed"),
                ),
            }
        )
    return {
        "version": VERSION,
        "location": facility.airport_code,
        "time": time.astimezone(UTC).isoformat(),
        "runways": list(facility.active_runways),
        "pads": list(facility.helicopter_pads),
        "settings": asdict(settings) if settings is not None else None,
        "records": records,
        "strip_order": [strip.flight_id for strip in strips],
        "radios": {
            channel.identifier: channel.state.value
            for channel in communications.channels
        },
        "lines": {
            line.identifier: line.hot
            for line in communications.lines + communications.interfacility_lines
        },
        "checkins": list(checkins),
        "reported_departures": sorted(reported),
    }


def _datetime(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("Saved time has no UTC offset")
    return result.astimezone(UTC)


def _finite(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Saved scenario contains a non-finite number")
    if isinstance(value, dict):
        for item in value.values():
            _finite(item)
    elif isinstance(value, list):
        for item in value:
            _finite(item)


def _validate_fields(data, schema):
    if not isinstance(data, dict) or set(data) != set(schema):
        raise ValueError("Invalid saved state fields")
    for name, types in schema.items():
        value = data[name]
        if not isinstance(value, types) or (
            isinstance(value, bool) and bool not in types
        ):
            raise ValueError(f"Invalid saved field: {name}")


NUMBER = (int, float)
OPTIONAL_NUMBER = (int, float, type(None))
STRING = (str,)
OPTIONAL_STRING = (str, type(None))
BOOL = (bool,)


def _validate_coordination(data):
    if data is None:
        return
    _validate_fields(
        data,
        {
            "kind": STRING,
            "source": STRING,
            "target": STRING,
            "information": STRING,
            "approved": BOOL,
            "elapsed": NUMBER,
        },
    )
    if data["elapsed"] < 0:
        raise ValueError("Invalid coordination elapsed time")


def _validate_record(record):
    _validate_fields(
        record,
        {
            "aircraft": (dict,),
            "model": STRING,
            "track": (dict,),
            "guidance": (dict,),
            "departure": (dict, type(None)),
            "strip": (dict,),
            "plan": (dict,),
        },
    )
    plane = record["aircraft"]
    aircraft_schema = {
        "id": STRING,
        "squawk": STRING,
        "mode_s": STRING,
        "callsign": STRING,
        "heading": NUMBER,
        "altitude": NUMBER,
        "speed": NUMBER,
        "distance": NUMBER,
        "lat": NUMBER,
        "lon": NUMBER,
        "flight_rules": STRING,
        "landed": BOOL,
        "scratchpad": STRING,
        "target_heading": OPTIONAL_NUMBER,
        "target_turn_direction": OPTIONAL_STRING,
        "target_altitude": OPTIONAL_NUMBER,
        "target_speed": OPTIONAL_NUMBER,
        "radio_channel": OPTIONAL_STRING,
    }
    if "ident_remaining" in plane:
        aircraft_schema["ident_remaining"] = NUMBER
    _validate_fields(plane, aircraft_schema)
    if (
        not plane["id"]
        or not plane["callsign"]
        or not 0 <= plane["heading"] < 360
        or not -90 <= plane["lat"] <= 90
        or not -180 <= plane["lon"] <= 180
        or plane["altitude"] < 0
        or plane["distance"] < 0
        or plane.get("ident_remaining", 0) < 0
        or plane["target_turn_direction"] not in (None, "LEFT", "RIGHT")
        or (
            plane["target_heading"] is not None
            and not 0 <= plane["target_heading"] < 360
        )
        or (plane["target_altitude"] is not None and plane["target_altitude"] < 0)
    ):
        raise ValueError("Invalid saved aircraft state")
    strip_schema = {
        "active": BOOL,
        "beacon_code": STRING,
        "operation_area": STRING,
        "assigned_altitude": STRING,
        "fix_time": STRING,
        "remarks": STRING,
    }
    if "offset_right" in record["strip"]:
        strip_schema["offset_right"] = BOOL
    if "discarded" in record["strip"]:
        strip_schema["discarded"] = BOOL
    _validate_fields(record["strip"], strip_schema)
    _validate_fields(
        record["plan"],
        {
            "origin": STRING,
            "destination": STRING,
            "route": STRING,
            "altitude": NUMBER,
            "speed": NUMBER,
        },
    )
    track = record["track"]
    track_schema = {
        "owner": STRING,
        "communications_owner": STRING,
        "handoff_target": OPTIONAL_STRING,
        "handoff_elapsed": NUMBER,
        "handoff_information": STRING,
        "identification_confirmation_due": BOOL,
        "coordination": (dict, type(None)),
        "coordination_history": (list,),
    }
    if "radar_control_state" in track:
        track_schema["radar_control_state"] = STRING
    if "pending_radio_channel" in track:
        track_schema["pending_radio_channel"] = OPTIONAL_STRING
    _validate_fields(track, track_schema)
    if "radar_control_state" in track:
        RadarControlState(track["radar_control_state"])
    if track["handoff_elapsed"] < 0:
        raise ValueError("Invalid handoff elapsed time")
    _validate_coordination(track["coordination"])
    for item in track["coordination_history"]:
        if item is None:
            raise ValueError("Invalid coordination history")
        _validate_coordination(item)
    nav = record["guidance"]
    _validate_fields(
        nav,
        {
            "next_index": (int,),
            "approach": BOOL,
            "vector_heading": OPTIONAL_NUMBER,
            "vector_turn_direction": OPTIONAL_STRING,
            "assigned_altitude": OPTIONAL_NUMBER,
            "signature": (list, type(None)),
            "route": (list,),
        },
    )
    if nav["vector_turn_direction"] not in (None, "LEFT", "RIGHT"):
        raise ValueError("Invalid vector turn direction")
    if nav["vector_heading"] is not None and not 0 <= nav["vector_heading"] < 360:
        raise ValueError("Invalid vector heading")
    signature = nav["signature"]
    if signature is not None and (
        len(signature) != 4
        or any(not isinstance(value, str) for value in signature[:3])
        or isinstance(signature[3], bool)
        or not isinstance(signature[3], NUMBER)
    ):
        raise ValueError("Invalid route signature")
    for point in nav["route"]:
        _validate_fields(
            point,
            {
                "name": STRING,
                "latitude": NUMBER,
                "longitude": NUMBER,
                "elevation": OPTIONAL_NUMBER,
            },
        )
        if not -90 <= point["latitude"] <= 90 or not -180 <= point["longitude"] <= 180:
            raise ValueError("Invalid route coordinates")
    dep = record["departure"]
    if dep is not None:
        _validate_fields(
            dep,
            {
                "takeoff_speed": NUMBER,
                "cruise_speed": NUMBER,
                "liftoff_altitude": NUMBER,
                "delay": NUMBER,
                "state": STRING,
                "elapsed": NUMBER,
                "airborne_elapsed": NUMBER,
                "check_in": OPTIONAL_STRING,
                "check_in_time": OPTIONAL_NUMBER,
                "frequency": STRING,
                "scheduled_utc": OPTIONAL_STRING,
            },
        )
        if dep["state"] not in ("waiting", "takeoff", "airborne") or any(
            dep[key] < 0
            for key in (
                "takeoff_speed",
                "cruise_speed",
                "delay",
                "elapsed",
                "airborne_elapsed",
            )
        ):
            raise ValueError("Invalid departure state")
        if (
            (dep["check_in"] is None) != (dep["check_in_time"] is None)
            or (dep["check_in"] is not None and dep["state"] != "airborne")
            or not dep["frequency"]
        ):
            raise ValueError("Invalid departure check-in")


def _restore_coordination(data):
    if data is None:
        return None
    return Coordination(
        CoordinationKind(data["kind"]),
        TrackingPosition(data["source"]),
        TrackingPosition(data["target"]),
        data["information"],
        data["approved"],
        data["elapsed"],
    )


def _assign(obj, data, names):
    if set(data) != set(names):
        raise ValueError("Invalid saved state fields")
    for name in names:
        setattr(obj, name, data[name])


def restore_scenario(data):
    _finite(data)
    _validate_fields(
        data,
        {
            "version": (int,),
            "location": STRING,
            "time": STRING,
            "runways": (list,),
            "pads": (list,),
            "settings": (dict, type(None)),
            "records": (list,),
            "strip_order": (list,),
            "radios": (dict,),
            "lines": (dict,),
            "checkins": (list,),
            "reported_departures": (list,),
        },
    )
    if data["version"] != VERSION or data["location"] != "KNYL":
        raise ValueError("Unsupported scenario file or location")
    if len(data["records"]) > 1000:
        raise ValueError("Too many aircraft in saved scenario")
    facility = ATCFacility.get_atc_facility_by_name("KNYL")
    if facility is None:
        raise ValueError("The KNYL facility is not configured")
    for name in ("runways", "pads", "strip_order", "checkins", "reported_departures"):
        if any(not isinstance(value, str) for value in data[name]):
            raise ValueError(f"Invalid saved {name}")
    facility.active_runways = tuple(data["runways"])
    facility.helicopter_pads = tuple(data["pads"])
    settings = None
    if data["settings"] is not None:
        settings = GeneratorSettings(**data["settings"])
        settings.validate()
    models = {
        model.aircraft_type: model
        for model in vars(aircraft_models).values()
        if isinstance(model, AircraftModel)
    }
    navigation = NavigationData()
    aircraft = AircraftList()
    strips_by_id = {}
    for record in data["records"]:
        _validate_record(record)
        values = record["aircraft"]
        if set(values) - {"ident_remaining"} != set(AIRCRAFT_FIELDS):
            raise ValueError("Invalid aircraft state fields")
        model = models[record["model"]]
        if values["target_speed"] is not None:
            Aircraft._validate_speed(values["target_speed"], model)
        if values["radio_channel"] is not None and values["radio_channel"] not in {
            item.identifier for item in facility.location.radio_frequencies
        }:
            raise ValueError("Unknown aircraft radio channel")
        plane = Aircraft(
            values["id"],
            values["squawk"],
            values["mode_s"],
            values["callsign"],
            model,
            values["heading"],
            values["altitude"],
            values["speed"],
            values["distance"],
            values["lat"],
            values["lon"],
            values["flight_rules"],
            values["landed"],
        )
        if plane.id in strips_by_id:
            raise ValueError(f"Duplicate aircraft identifier {plane.id}")
        plan = FlightPlan(plane.id, **record["plan"])
        strip = FlightStrip(plane.id, plane, plan)
        _assign(
            strip, {name: record["strip"][name] for name in STRIP_FIELDS}, STRIP_FIELDS
        )
        strip.offset_right = record["strip"].get("offset_right", False)
        strip.discarded = record["strip"].get("discarded", False)
        track = record["track"]
        _assign(plane.track, {name: track[name] for name in TRACK_FIELDS}, TRACK_FIELDS)
        plane.track.radar_control_state = RadarControlState(
            track.get("radar_control_state", RadarControlState.UNCONTROLLED)
        )
        pending_channel = track.get("pending_radio_channel")
        if pending_channel is not None:
            target_prefix = {
                TrackingPosition.LOS_ANGELES: "zla",
                TrackingPosition.ALBUQUERQUE: "zab",
            }.get(track["handoff_target"])
            if (
                target_prefix is None
                or track["owner"] != TrackingPosition.YUMA
                or track["communications_owner"] != TrackingPosition.YUMA
                or pending_channel
                not in {
                    item.identifier
                    for item in facility.location.neighbor_frequencies
                    if item.identifier.startswith(target_prefix)
                }
            ):
                raise ValueError("Invalid pending communications transfer")
        plane.track.pending_radio_channel = pending_channel
        plane.track.owner = TrackingPosition(track["owner"])
        plane.track.communications_owner = TrackingPosition(
            track["communications_owner"]
        )
        plane.track.handoff_target = (
            TrackingPosition(track["handoff_target"])
            if track["handoff_target"]
            else None
        )
        plane.track.coordination = _restore_coordination(track["coordination"])
        plane.track.coordination_history = [
            _restore_coordination(item) for item in track["coordination_history"]
        ]
        plane.radio_channel = values["radio_channel"]
        dep = record["departure"]
        if dep is not None:
            plane.speed = dep["cruise_speed"]
            plane.departure = Departure(
                strip, navigation.airport("KNYL"), dep["delay"], facility.location
            )
            _assign(
                plane.departure,
                {name: dep[name] for name in DEPARTURE_FIELDS},
                DEPARTURE_FIELDS,
            )
            plane.departure.scheduled_utc = (
                _datetime(dep["scheduled_utc"]) if dep["scheduled_utc"] else None
            )
        guidance = FlightPlanGuidance(strip, navigation)
        nav = record["guidance"]
        _assign(
            guidance, {name: nav[name] for name in GUIDANCE_FIELDS}, GUIDANCE_FIELDS
        )
        guidance.route = [Waypoint(**point) for point in nav["route"]]
        guidance.signature = (
            tuple(nav["signature"]) if nav["signature"] is not None else None
        )
        if not 1 <= guidance.next_index < len(guidance.route):
            raise ValueError(f"Invalid route progress for {plane.id}")
        plane.flight_guidance = guidance
        _assign(
            plane, {name: values[name] for name in AIRCRAFT_FIELDS}, AIRCRAFT_FIELDS
        )
        plane.ident_remaining = values.get("ident_remaining", 0.0)
        aircraft.add_aircraft([plane])
        strips_by_id[plane.id] = strip
    order = data["strip_order"]
    if len(order) != len(strips_by_id) or set(order) != set(strips_by_id):
        raise ValueError("Invalid saved flight strip order")
    if not set(data["reported_departures"]).issubset(strips_by_id):
        raise ValueError("Invalid reported departures")
    if set(data["radios"]) != {
        item.identifier for item in facility.location.radio_frequencies
    }:
        raise ValueError("Saved radio channels do not match the location")
    intrafacility_ids = {
        identifier for identifier, _ in facility.location.coordination_lines
    }
    interfacility_ids = {
        identifier for identifier, _ in facility.location.interfacility_lines
    }
    if (
        intrafacility_ids & interfacility_ids
        or set(data["lines"])
        not in (intrafacility_ids, intrafacility_ids | interfacility_ids)
        or any(type(hot) is not bool for hot in data["lines"].values())
    ):
        raise ValueError("Saved coordination lines do not match the location")
    aircraft.assign_to_atc_facility(facility)
    return RestoredScenario(
        aircraft,
        facility,
        [strips_by_id[identifier] for identifier in order],
        _datetime(data["time"]),
        settings,
        {name: RadioState(state) for name, state in data["radios"].items()},
        {**dict.fromkeys(interfacility_ids, False), **data["lines"]},
        list(data["checkins"]),
        set(data["reported_departures"]),
    )


def scenario_path(name, directory=None):
    if directory is None:
        directory = SAVE_DIRECTORY
    if name != name.strip() or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9 _-]{0,47}", name
    ):
        raise ValueError("Use 1–48 letters, digits, spaces, hyphens or underscores")
    if name.upper().split(".")[0] in {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }:
        raise ValueError("That name is reserved by the operating system")
    return directory / f"{name}.json"


def saved_names(directory=None):
    if directory is None:
        directory = SAVE_DIRECTORY
    if not directory.exists():
        return []
    return sorted(
        (path.stem for path in directory.glob("*.json") if path.is_file()),
        key=str.casefold,
    )


def write_scenario(name, data, directory=None, overwrite=False):
    if directory is None:
        directory = SAVE_DIRECTORY
    path = scenario_path(name, directory)
    text = json.dumps(data, ensure_ascii=True, allow_nan=False, indent=2)
    restore_scenario(json.loads(text))
    directory.mkdir(parents=True, exist_ok=True)
    if not overwrite:
        with path.open("x", encoding="utf-8") as file:
            try:
                file.write(text)
            except OSError:
                file.close()
                path.unlink()
                raise
        return
    fd, temporary = tempfile.mkstemp(prefix=".scenario-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(text)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_scenario(name, directory=None):
    path = scenario_path(name, directory)
    if path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("Scenario file is too large")
    with path.open(encoding="utf-8") as file:
        data = json.load(file)
    return restore_scenario(data)
