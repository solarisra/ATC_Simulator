"""Strict, callsign-addressed voice commands for the simulator."""

import math
import re
from dataclasses import dataclass

from simulator.core.clearances import (
    clearance_control_error,
    execute_clearance,
    is_airborne,
)
from simulator.navigation.navmath import NavigationalCoordinateSystem

DIGITS = {
    "ZERO": "0",
    "OH": "0",
    "ONE": "1",
    "TWO": "2",
    "THREE": "3",
    "TREE": "3",
    "FOUR": "4",
    "FIVE": "5",
    "FIFE": "5",
    "SIX": "6",
    "SEVEN": "7",
    "EIGHT": "8",
    "NINE": "9",
    "NINER": "9",
}
PHONETIC = dict(
    zip(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
        [
            "ALPHA",
            "BRAVO",
            "CHARLIE",
            "DELTA",
            "ECHO",
            "FOXTROT",
            "GOLF",
            "HOTEL",
            "INDIA",
            "JULIETT",
            "KILO",
            "LIMA",
            "MIKE",
            "NOVEMBER",
            "OSCAR",
            "PAPA",
            "QUEBEC",
            "ROMEO",
            "SIERRA",
            "TANGO",
            "UNIFORM",
            "VICTOR",
            "WHISKEY",
            "XRAY",
            "YANKEE",
            "ZULU",
        ],
    )
)
LETTERS = {word: letter for letter, word in PHONETIC.items()}
LETTERS.update({"ALFA": "A", "JULIET": "J", "X-RAY": "X"})
NUMBER_WORDS = {
    "TEN": 10,
    "ELEVEN": 11,
    "TWELVE": 12,
    "THIRTEEN": 13,
    "FOURTEEN": 14,
    "FIFTEEN": 15,
    "SIXTEEN": 16,
    "SEVENTEEN": 17,
    "EIGHTEEN": 18,
    "NINETEEN": 19,
    "TWENTY": 20,
    "THIRTY": 30,
    "FORTY": 40,
    "FIFTY": 50,
    "SIXTY": 60,
    "SEVENTY": 70,
    "EIGHTY": 80,
    "NINETY": 90,
}


@dataclass(frozen=True)
class PilotReply:
    aircraft_id: str
    channel: str
    text: str


def _tokens(text: str) -> list[str]:
    text = re.sub(r"(?<=\d)-(?=\d)", " ", text.upper())
    return re.findall(r"[A-Z0-9]+(?:-[A-Z0-9]+)?", text)


def _callsign_tokens(words: list[str]) -> list[str]:
    # Whisper can transcribe "niner" as "9 or" or append "er" to digits.
    return [
        word[:-2] if re.fullmatch(r"\d*9ER", word) else word
        for index, word in enumerate(words)
        if not (
            word == "OR"
            and index > 0
            and words[index - 1].isdigit()
            and words[index - 1].endswith("9")
        )
    ]


def _identifier(words: list[str]) -> str:
    return "".join(LETTERS.get(word, DIGITS.get(word, word)) for word in words)


def _number(words: list[str]) -> int:
    if not words:
        raise ValueError("Missing number")
    digits = [DIGITS.get(word, word) for word in words]
    if all(word.isdigit() for word in digits):
        return int("".join(digits))
    total = current = 0
    digit_run = ""
    seen_thousand = False
    for word in words:
        if word == "AND":
            continue
        if word in DIGITS:
            digit_run += DIGITS[word]
            continue
        if digit_run:
            current += int(digit_run)
            digit_run = ""
        if word == "HUNDRED":
            if not current:
                raise ValueError("Invalid number")
            current *= 100
        elif word == "THOUSAND":
            if not current or seen_thousand:
                raise ValueError("Invalid number")
            total += current * 1000
            current = 0
            seen_thousand = True
        elif word in NUMBER_WORDS:
            current += NUMBER_WORDS[word]
        elif word.isdigit():
            current += int(word)
        else:
            raise ValueError(f"Unrecognized number: {word}")
    if digit_run:
        current += int(digit_run)
    return total + current


def _spoken_callsign(callsign):
    match = re.fullmatch(r"([A-Z]+)([0-9]+)([A-Z]*)", callsign.upper())
    if match is None:
        return callsign
    prefix, number, suffix = match.groups()
    if len(prefix) == 1:
        prefix = PHONETIC[prefix]
    digits = " ".join(
        (
            "zero",
            "one",
            "two",
            "three",
            "four",
            "five",
            "six",
            "seven",
            "eight",
            "niner",
        )[int(digit)]
        for digit in number
    )
    ending = " ".join(PHONETIC[letter] for letter in suffix)
    return " ".join(part for part in (prefix, digits, ending) if part)


def _address(words, aircraft_list):
    matches = []
    for aircraft in aircraft_list:
        callsign = aircraft.callsign.upper()
        for end in range(1, len(words) + 1):
            candidate = _identifier(_callsign_tokens(words[:end]))
            if candidate == callsign:
                if (
                    words[end : end + 1] == ["OR"]
                    and words[end - 1].isdigit()
                    and words[end - 1].endswith("9")
                ):
                    end += 1
                matches.append((aircraft, words[end:]))
                break
            if not callsign.startswith(candidate):
                break
    if len(matches) != 1:
        raise ValueError("Say one unambiguous aircraft callsign first")
    return matches[0]


def _clearance(words):
    if words[:1] == ["CLIMBED"]:
        words = ["CLIMB", *words[1:]]
    if words[:1] == ["HITTING"]:
        words = ["HEADING", *words[1:]]
    elif words[:2] in (["FLY", "HITTING"], ["TURN", "HITTING"]):
        words = [words[0], "HEADING", *words[2:]]
    if words[:2] in (["FLY", "HEADING"], ["TURN", "HEADING"]):
        words = words[1:]
    if words[:1] == ["HEADING"]:
        return f"HDG {_number(words[1:])}"
    if words[:3] in (["CLIMB", "AND", "MAINTAIN"], ["DESCEND", "AND", "MAINTAIN"]):
        words = words[2:]
    elif words[:2] in (["CLIMB", "TO"], ["DESCEND", "TO"]):
        words = ["MAINTAIN", *words[2:]]
    if words[:1] in (["MAINTAIN"], ["ALTITUDE"]):
        altitude = words[1:]
        if altitude[:2] == ["FLIGHT", "LEVEL"]:
            return f"ALT {_number(altitude[2:]) * 100}"
        if altitude[-1:] in (["FEET"], ["FOOT"]):
            altitude = altitude[:-1]
        return f"ALT {_number(altitude)}"
    if words[:1] == ["DIRECT"]:
        fix = words[1:]
        if fix[:1] == ["TO"]:
            fix = fix[1:]
        identifier = _identifier(fix)
        if not 3 <= len(identifier) <= 5 or not identifier.isalnum():
            raise ValueError("Say a route fix identifier after direct")
        return f"DCT {identifier}"
    if words in (["RESUME", "ROUTE"], ["RESUME", "OWN", "NAVIGATION"]):
        return "RESUME"
    if words == ["RESUME", "FILED", "ALTITUDE"]:
        return "ALT CLR"
    raise ValueError("Unrecognized voice instruction")


def _traffic_reply(aircraft, aircraft_list):
    candidates = [
        (
            NavigationalCoordinateSystem.calculate_distance(
                aircraft.lat, aircraft.lon, other.lat, other.lon
            ),
            other,
        )
        for other in aircraft_list
        if other is not aircraft and is_airborne(other)
    ]
    if not candidates:
        return "No other airborne traffic."
    distance, other = min(candidates, key=lambda item: item[0])
    lat1, lat2 = math.radians(aircraft.lat), math.radians(other.lat)
    delta_lon = math.radians(other.lon - aircraft.lon)
    bearing = (
        math.degrees(
            math.atan2(
                math.sin(delta_lon) * math.cos(lat2),
                math.cos(lat1) * math.sin(lat2)
                - math.sin(lat1) * math.cos(lat2) * math.cos(delta_lon),
            )
        )
        % 360
    )
    clock = round(((bearing - aircraft.heading) % 360) / 30) % 12 or 12
    return (
        f"Nearest traffic {clock} o'clock, {distance:.1f} miles, "
        f"altitude {round(other.altitude * 100)} feet."
    )


def handle_transmission(text, aircraft_list, facility, transmitting_channels):
    aircraft, words = _address(_tokens(text), aircraft_list)
    channel = aircraft.radio_channel
    if channel is None or channel not in transmitting_channels:
        raise ValueError(f"{aircraft.callsign} is not on a transmitting frequency")
    error = clearance_control_error(aircraft, facility)
    if error is not None:
        raise ValueError(f"{aircraft.callsign}: {error}")
    callsign = _spoken_callsign(aircraft.callsign)
    if (words[:1] == ["TRAFFIC"] or words[:2] == ["RADAR", "CONTACT"]) and any(
        word
        in {
            "TURN",
            "TURNED",
            "FLY",
            "CLIMB",
            "CLIMBED",
            "DESCEND",
            "MAINTAIN",
            "DIRECT",
            "RESUME",
        }
        for word in words[1:]
    ):
        raise ValueError("Send the advisory and clearance separately")
    if words in (["SAY", "TRAFFIC"], ["REPORT", "TRAFFIC"]):
        response = _traffic_reply(aircraft, aircraft_list)
    elif words[:1] == ["TRAFFIC"] and len(words) > 1:
        response = "Looking for traffic."
    elif words[:2] == ["RADAR", "CONTACT"]:
        response = "Radar contact, roger."
    else:
        if words[:1] == ["TURNED"]:
            words = ["TURN", *words[1:]]
        turn_direction = None
        if words[:1] == ["TURN"] and words[1:2] in (["LEFT"], ["RIGHT"]):
            turn_direction = words[1]
            words = ["TURN", *words[2:]]
        command = _clearance(words)
        readback = execute_clearance(
            aircraft, facility, command, turn_direction=turn_direction
        )
        if command.startswith("HDG "):
            heading = f"{int(command.split()[1]):03d}"
            response = (
                (
                    f"Turn {turn_direction.lower()}, heading "
                    if turn_direction
                    else "Heading "
                )
                + " ".join(
                    (
                        "zero",
                        "one",
                        "two",
                        "three",
                        "four",
                        "five",
                        "six",
                        "seven",
                        "eight",
                        "niner",
                    )[int(digit)]
                    for digit in heading
                )
                + " true."
            )
        else:
            response = readback.replace(" FT", " feet").lower() + "."
    return PilotReply(aircraft.id, channel, f"{response} {callsign}.")
