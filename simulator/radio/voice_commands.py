"""Strict, callsign-addressed voice commands for the simulator."""

import math
import re
from dataclasses import dataclass

from simulator.core.aircraft import display_callsign, is_heavy
from simulator.core.atc import RadarControlState, TrackingPosition
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
    "TO": "2",
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
SPOKEN_DIGITS = (
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
)
INSTRUCTION_STARTS = {
    "HEADING", "HITTING", "FLY", "TURN", "TURNED", "CLIMB", "CLIMBED",
    "DESCEND", "MAINTAIN", "ALTITUDE", "DIRECT", "RESUME", "SQUAWK",
    "IDENT", "IDENTITY", "IDENTICAL", "SAY", "REPORT", "TRAFFIC",
    "RADAR", "CONTACT",
}


@dataclass(frozen=True)
class PilotReply:
    aircraft_id: str
    channel: str
    text: str
    pilot_voice: str | None = None


def _tokens(text: str) -> list[str]:
    text = re.sub(r"(?<=\d)-(?=\d)", " ", text.upper())
    return re.findall(r"[A-Z0-9]+(?:-[A-Z0-9]+)?", text)


def _niner_tokens(words: list[str]) -> list[str]:
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


def spoken_callsign(aircraft):
    callsign = aircraft.callsign
    match = re.fullmatch(r"([A-Z]+)([0-9]+)([A-Z]*)", callsign.upper())
    if match is None:
        spoken = callsign
    else:
        prefix, number, suffix = match.groups()
        prefix = {"AAL": "American", "UAL": "United", "AMF": "Am Flight"}.get(
            prefix, prefix
        )
        if len(prefix) == 1:
            prefix = PHONETIC[prefix]
        digits = _spoken_digits(number)
        ending = " ".join(PHONETIC[letter] for letter in suffix)
        spoken = " ".join(part for part in (prefix, digits, ending) if part)
    return f"{spoken} heavy" if is_heavy(aircraft) else spoken


def _spoken_digits(digits: str) -> str:
    return " ".join(SPOKEN_DIGITS[int(digit)] for digit in digits)


def _spoken_heading(heading):
    return _spoken_digits(f"{heading:03d}")


def _squawk_code(words: list[str]) -> str:
    code = "".join(DIGITS.get(word, word) for word in words)
    if not re.fullmatch(r"[0-7]{4}", code):
        raise ValueError("Squawk code must be four digits from 0 to 7")
    return code


def _contact_frequency(words: list[str]) -> str:
    words = _niner_tokens(words)
    if "POINT" in words:
        point = words.index("POINT")
        left, right = words[:point], words[point + 1 :]
    elif len(words) == 2 and all(DIGITS.get(word, word).isdigit() for word in words):
        left, right = words[:1], words[1:]
    else:
        raise ValueError("Say the center frequency including the decimal point")
    integer = "".join(DIGITS.get(word, word) for word in left)
    fraction = "".join(DIGITS.get(word, word) for word in right)
    if (
        not integer.isdigit()
        or len(integer) != 3
        or not fraction.isdigit()
        or not 1 <= len(fraction) <= 3
    ):
        raise ValueError("Invalid center frequency")
    return f"{integer}.{fraction.ljust(3, '0')}"


def _center_contact(words, facility):
    contact_words = words[1:]
    if contact_words[:3] == ["LOS", "ANGELES", "CENTER"]:
        target, label, prefix = (
            TrackingPosition.LOS_ANGELES,
            "Los Angeles Center",
            "zla",
        )
        frequency_words = contact_words[3:]
    elif contact_words[:2] == ["ALBUQUERQUE", "CENTER"]:
        target, label, prefix = (
            TrackingPosition.ALBUQUERQUE,
            "Albuquerque Center",
            "zab",
        )
        frequency_words = contact_words[2:]
    else:
        raise ValueError("Say Los Angeles Center or Albuquerque Center")
    if frequency_words[:1] == ["ON"]:
        frequency_words = frequency_words[1:]
    frequency = _contact_frequency(frequency_words)
    matching = [
        channel.identifier
        for channel in facility.location.neighbor_frequencies
        if channel.identifier.startswith(prefix) and channel.frequency == frequency
    ]
    if len(matching) > 1:
        raise ValueError("Center frequency matches multiple channels")
    return target, label, frequency, matching[0] if matching else None


def _bearing_destination(bearing):
    return next(
        (
            index
            for index, word in enumerate(bearing)
            if word in ("TO", "TWO", "2")
            and index > 0
            and index + 1 < len(bearing)
            and bearing[index + 1] not in DIGITS
            and bearing[index + 1] not in NUMBER_WORDS
            and bearing[index + 1] not in ("HUNDRED", "THOUSAND", "AND")
            and not bearing[index + 1].isdigit()
        ),
        None,
    )


def _bearing_instruction(words, facility):
    if words[:2] != ["MAINTAIN", "BEARING"]:
        return None
    remainder = words[2:]
    contact = remainder.index("CONTACT") if "CONTACT" in remainder else len(remainder)
    bearing = remainder[:contact]
    destination = _bearing_destination(bearing)
    if destination is not None:
        if any(
            word
            in {"TURN", "CLIMB", "ASCEND", "DESCEND", "MAINTAIN", "DIRECT", "RESUME"}
            for word in bearing[destination + 1 :]
        ):
            raise ValueError("Invalid bearing destination")
        bearing = bearing[:destination]
    heading = _number(bearing)
    if not 1 <= heading <= 360:
        raise ValueError("Heading must be 001 to 360")
    contact_instruction = (
        _center_contact(remainder[contact:], facility)
        if contact < len(remainder)
        else None
    )
    return heading, contact_instruction


def _address(words, aircraft_list):
    matches = []
    alternatives = [words]
    if words and re.fullmatch(r"DOUBLE(?:[0-9]+[A-Z]*)?", words[0]):
        alternatives.append(["DEVIL" + words[0][len("DOUBLE") :], *words[1:]])
    if (
        len(words) >= 2
        and words[0] == "AM"
        and re.fullmatch(r"FLIGHT(?:[0-9]+[A-Z]*)?", words[1])
    ):
        alternatives.append(["AMF" + words[1][len("FLIGHT") :], *words[2:]])
    for spoken, prefix in (
        ("AMERICAN", "AAL"),
        ("UNITED", "UAL"),
        ("AMFLIGHT", "AMF"),
    ):
        if words and re.fullmatch(rf"{spoken}(?:[0-9]+[A-Z]*)?", words[0]):
            rest = words[1:]
            if (
                spoken in ("AMERICAN", "UNITED")
                and words[0] == spoken
                and rest[:1] == ["AIRLINES"]
            ):
                rest = rest[1:]
            alternatives.append([prefix + words[0][len(spoken) :], *rest])
        # Handle airline name followed by separate number words (e.g., "AMERICAN FOUR")
        if words and words[0] == spoken and len(words) > 1 and words[1] in DIGITS:
            rest = words[2:]
            if (
                spoken in ("AMERICAN", "UNITED")
                and rest[:1] == ["AIRLINES"]
            ):
                rest = rest[1:]
            alternatives.append([prefix + words[1], *rest])
    for candidate_words in alternatives:
        for aircraft in aircraft_list:
            callsign = aircraft.callsign.upper()
            for end in range(1, len(candidate_words) + 1):
                callsign_words = _niner_tokens(candidate_words[:end])
                candidates = {_identifier(callsign_words)}
                if "MIC" in callsign_words:
                    candidates.add(
                        _identifier(
                            [
                                "MIKE" if word == "MIC" else word
                                for word in callsign_words
                            ]
                        )
                    )
                if callsign in candidates or (
                    callsign + "H" in candidates and is_heavy(aircraft)
                ):
                    if (
                        candidate_words[end : end + 1] == ["OR"]
                        and candidate_words[end - 1].isdigit()
                        and candidate_words[end - 1].endswith("9")
                    ):
                        end += 1
                    if (
                        callsign in candidates
                        and candidate_words[end : end + 1]
                        in (["HEAVY"], ["H"], ["HOTEL"])
                        and is_heavy(aircraft)
                    ):
                        end += 1
                    matches.append((aircraft, candidate_words[end:]))
                    break
                if not any(callsign.startswith(candidate) for candidate in candidates):
                    break
    if len(matches) != 1:
        raise ValueError("Say one unambiguous aircraft callsign first")
    return matches[0]


def _corrected_instruction(words: list[str], replacement: list[str]) -> list[str]:
    if replacement[0] in INSTRUCTION_STARTS or replacement[:2] == ["I", "DENT"]:
        return replacement
    if words[:1] == ["CONTACT"] or (
        words[:2] == ["MAINTAIN", "BEARING"] and "CONTACT" in words
    ):
        contact = words.index("CONTACT")
        if "CENTER" in words[contact + 1 :]:
            end = words.index("CENTER", contact + 1) + 1
            if words[end : end + 1] == ["ON"]:
                end += 1
            return [*words[:end], *replacement]
    if words[:2] == ["MAINTAIN", "BEARING"]:
        if _bearing_destination(words[2:]) is not None:
            raise ValueError("Repeat the full bearing instruction after correction")
        return [*words[:2], *replacement]
    if words[:1] in (["HEADING"], ["HITTING"], ["FLY"], ["TURN"], ["TURNED"]):
        for index, word in enumerate(words):
            if word in ("HEADING", "HITTING"):
                return [*words[: index + 1], *replacement]
    if words[:1] == ["SQUAWK"]:
        return [words[0], *replacement]
    if words[:1] == ["DIRECT"]:
        end = 2 if words[1:2] in (["TO"], ["TWO"], ["2"]) else 1
        return [*words[:end], *replacement]
    if words[:1] in (["CLIMB"], ["CLIMBED"], ["DESCEND"], ["MAINTAIN"], ["ALTITUDE"]):
        end = 1
        if words[0] in ("CLIMB", "CLIMBED", "DESCEND"):
            if words[1:3] == ["AND", "MAINTAIN"]:
                end = 3
            elif words[1:2] in (["TO"], ["TWO"], ["2"]):
                end = 2
        if words[end : end + 2] == ["FLIGHT", "LEVEL"]:
            end += 2
        return [*words[:end], *replacement]
    raise ValueError("Repeat the full instruction after correction")


def _corrected_address(words, aircraft_list):
    if "CORRECTION" not in words:
        return _address(words, aircraft_list)
    segments = [[]]
    for word in words:
        if word == "CORRECTION":
            segments.append([])
        else:
            segments[-1].append(word)
    if any(not segment for segment in segments):
        raise ValueError("Say the correction after the word correction")

    try:
        aircraft, instruction = _address(segments[0], aircraft_list)
        address_error = None
    except ValueError as error:
        aircraft, instruction, address_error = None, [], error
    for segment in segments[1:]:
        if segment[0] in INSTRUCTION_STARTS or segment[:2] == ["I", "DENT"]:
            corrected_aircraft, corrected_words = None, []
        else:
            try:
                corrected_aircraft, corrected_words = _address(segment, aircraft_list)
            except ValueError:
                corrected_aircraft, corrected_words = None, []
        if corrected_aircraft is not None and (not instruction or corrected_words):
            aircraft, instruction = corrected_aircraft, corrected_words
            address_error = None
        elif aircraft is None:
            if address_error is not None:
                raise address_error
            raise ValueError("Say one unambiguous aircraft callsign first")
        else:
            instruction = _corrected_instruction(instruction, segment)
    if aircraft is None:
        raise ValueError("Say one unambiguous aircraft callsign first")
    return aircraft, instruction


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
    elif (
        len(words) >= 3
        and words[0] in ("CLIMB", "DESCEND")
        and words[1] in ("TO", "TWO", "2")
    ):
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
        if len(fix) > 1 and fix[0] in ("TO", "TWO", "2"):
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
    available = [
        aircraft
        for aircraft in aircraft_list
        if getattr(aircraft, "entry_remaining", None) is None
    ]
    aircraft, words = _corrected_address(_tokens(text), available)
    normalized = []
    index = 0
    while index < len(words):
        if words[index : index + 2] == ["I", "DENT"]:
            normalized.append("IDENT")
            index += 2
        else:
            normalized.append(
                "IDENT" if words[index] in ("IDENTITY", "IDENTICAL") else words[index]
            )
            index += 1
    words = normalized
    channel = aircraft.radio_channel
    if channel is None or channel not in transmitting_channels:
        raise ValueError(
            f"{display_callsign(aircraft)} is not on a transmitting frequency"
        )
    callsign = spoken_callsign(aircraft)
    bearing_instruction = _bearing_instruction(words, facility)
    contact_instruction = (
        _center_contact(words, facility)
        if words[:1] == ["CONTACT"]
        else bearing_instruction[1]
        if bearing_instruction is not None
        else None
    )
    if contact_instruction is not None:
        track = aircraft.track
        if (
            not is_airborne(aircraft)
            or track.communications_owner != TrackingPosition.YUMA
            or track.owner == TrackingPosition.YUMA
            or track.handoff_target is not None
            or track.radar_control_state != RadarControlState.HANDED_OFF
        ):
            raise ValueError("Complete an outgoing handoff before directing contact")
        target, center, frequency, destination_channel = contact_instruction
        if track.owner != target:
            raise ValueError("Contact the center that accepted the handoff")
        sector = next(
            (
                identifier
                for identifier, label in facility.location.interfacility_lines
                if label == track.handoff_information
            ),
            None,
        )
        if (
            sector is not None
            and destination_channel is not None
            and not destination_channel.startswith(sector.replace("_sector_", "") + "_")
        ):
            destination_channel = None
        contact_instruction = target, center, frequency, destination_channel
    else:
        error = clearance_control_error(aircraft, facility)
        if error is not None:
            raise ValueError(f"{display_callsign(aircraft)}: {error}")
    if (words[:1] == ["TRAFFIC"] or words[:2] == ["RADAR", "CONTACT"]) and any(
        word
        in {
            "TURN",
            "TURNED",
            "FLY",
            "CLIMB",
            "CLIMBED",
            "DESCEND",
            "DESCENDED",
            "ASCEND",
            "ASCENDED",
            "MAINTAIN",
            "DIRECT",
            "RESUME",
            "IDENT",
            "SQUAWK",
        }
        for word in words[1:]
    ):
        raise ValueError("Send the advisory and clearance separately")
    if bearing_instruction is not None:
        heading, _ = bearing_instruction
        execute_clearance(aircraft, facility, f"HDG {heading}")
        response = f"Maintain bearing {_spoken_heading(heading)}."
    elif contact_instruction is not None:
        response = ""
    elif words == ["IDENT"]:
        aircraft.activate_ident()
        response = "Ident."
    elif words[:1] == ["SQUAWK"] and words[1:] != ["IDENT"]:
        code = _squawk_code(words[1:])
        aircraft.update_squawk(code)
        response = f"Squawk {_spoken_digits(code)}."
    elif words in (["SAY", "TRAFFIC"], ["REPORT", "TRAFFIC"]):
        response = _traffic_reply(aircraft, aircraft_list)
    elif words[:1] == ["TRAFFIC"] and len(words) > 1:
        response = "Looking for traffic."
    elif words[:2] == ["RADAR", "CONTACT"]:
        if aircraft.track.owner != TrackingPosition.YUMA:
            raise ValueError("Yuma does not own this track")
        aircraft.track.radar_control_state = RadarControlState.CONTROLLED
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
                + _spoken_heading(int(heading))
                + "."
            )
        else:
            response = readback.replace(" FT", " feet").lower() + "."
    if contact_instruction is not None:
        _, center, frequency, destination_channel = contact_instruction
        if destination_channel is None:
            response += f" Verify {center} frequency {frequency}."
        else:
            aircraft.track.transfer_communications()
            aircraft.radio_channel = destination_channel
            response += f" Contact {center} on {frequency}."
    return PilotReply(
        aircraft.id, channel, f"{response.strip()} {callsign}.", aircraft.pilot_voice
    )
