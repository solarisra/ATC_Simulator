from functools import cache

import arcade

from constants import SCREEN_HEIGHT, SCREEN_WIDTH
from flight_navigation import NavigationData

PANEL_WIDTH = 440
STRIP_HEIGHT = 76
LIST_TOP = SCREEN_HEIGHT - 60
LIST_BOTTOM = 220
VISIBLE_STRIPS = (LIST_TOP - LIST_BOTTOM) // STRIP_HEIGHT
STRIP_LEFT = SCREEN_WIDTH + 8
STRIP_COLUMNS = (0, 104, 159, 218, 344, 424)
STRIP_DRAW_HEIGHT = STRIP_HEIGHT - 6
TOOLTIP_WIDTH = 300
DRAG_THRESHOLD = 5
EDIT_FIELDS = {
    arcade.key.KEY_1: ("assigned_altitude", "ASSIGNED ALT FT", 6),
    arcade.key.KEY_2: ("fix_time", "FIX / TIME", 26),
    arcade.key.KEY_3: ("remarks", "CLEARANCE / REMARKS", 32),
    arcade.key.KEY_4: ("beacon_code", "STRIP BEACON", 4),
    arcade.key.KEY_5: ("operation_area", "STRIP RUNWAY / PAD", 3),
}


def display_airport_identifier(identifier):
    if identifier and len(identifier) == 4 and identifier.startswith("K"):
        return identifier[1:]
    return identifier


@cache
def _display_navigation_data():
    return NavigationData()


def _display_route(strip):
    route = strip.flight_plan.route
    if not route:
        return route
    tokens = route.split()
    if not any(len(token) == 4 and token.startswith("K") for token in tokens):
        return route
    guidance = getattr(strip.aircraft, "flight_guidance", None)
    navigation = guidance.navigation_data if guidance else _display_navigation_data()
    return " ".join(
        display_airport_identifier(token)
        if token in navigation.airports and token not in navigation.points
        else token
        for token in tokens
    )


def _display_route_to_destination(strip):
    plan = strip.flight_plan
    route = _display_route(strip) or "--"
    destination = plan.destination
    tokens = plan.route.split() if plan.route else []
    if destination and tokens and tokens[-1].upper() == destination.upper():
        return route
    return f"{route} {display_airport_identifier(destination) or '--'}"


def terminal_strip_fields(strip, airport_code):
    plan = strip.flight_plan
    if not airport_code or not plan.origin or not plan.destination:
        kind = "UNKNOWN"
    elif plan.origin == airport_code:
        kind = "DEPARTURE"
    elif plan.destination == airport_code:
        kind = "ARRIVAL"
    else:
        kind = "OVERFLIGHT"

    altitude = plan.altitude
    requested_altitude = (
        f"{altitude / 100:g}"
        if isinstance(altitude, (int, float))
        else str(altitude or "--")
    )
    assigned = (
        f"A {int(strip.assigned_altitude) / 100:g}" if strip.assigned_altitude else ""
    )
    if kind == "DEPARTURE":
        block7 = requested_altitude
        block8 = display_airport_identifier(plan.origin)
        block9 = (
            _display_route_to_destination(strip),
            assigned,
            f"FIX {strip.fix_time}" if strip.fix_time else "",
            strip.remarks,
        )
    else:
        block7 = "--"
        block8 = "--"
        block9 = (
            assigned or "--",
            f"FIX {strip.fix_time}" if strip.fix_time else "",
            strip.remarks,
            f"TO {display_airport_identifier(plan.destination)}"
            if plan.destination
            else "",
        )
    return kind, block7, block8, block9


class FlightStripPanel:
    def __init__(
        self,
        strips,
        aircraft_list,
        airport_code=None,
        active_runways=(),
        helicopter_pads=(),
    ):
        self.strips = strips
        self.aircraft_list = aircraft_list
        self.airport_code = airport_code
        self.active_runways = active_runways
        self.helicopter_pads = helicopter_pads
        self.offset = 0
        self.edit_strip = None
        self.edit_field = None
        self.edit_text = ""
        self.error = ""
        self.hover_position = None
        self.drag_strip = None
        self.drag_start = None
        self.drag_position = None
        self.dragging = False
        self.text = arcade.Text(
            "",
            SCREEN_WIDTH + 12,
            0,
            arcade.color.BLACK,
            10,
            font_name="Consolas",
            anchor_y="top",
        )
        self.header = arcade.Text(
            "",
            SCREEN_WIDTH + 12,
            SCREEN_HEIGHT - 14,
            arcade.color.WHITE,
            11,
            font_name="Consolas",
            anchor_y="top",
            multiline=True,
            width=PANEL_WIDTH - 24,
        )
        self.footer = arcade.Text(
            "",
            SCREEN_WIDTH + 12,
            205,
            arcade.color.WHITE,
            11,
            font_name="Consolas",
            anchor_y="top",
            multiline=True,
            width=PANEL_WIDTH - 24,
        )
        self.tooltip = arcade.Text(
            "",
            0,
            0,
            arcade.color.WHITE,
            11,
            font_name="Consolas",
            anchor_y="top",
            multiline=True,
            width=TOOLTIP_WIDTH - 16,
        )

    def active_strips(self):
        active_aircraft = {
            id(aircraft) for aircraft in self.aircraft_list.aircraft_list
        }
        return [
            strip
            for strip in self.strips
            if strip.active and id(strip.aircraft) in active_aircraft
        ]

    def visible_strips(self):
        strips = self.active_strips()
        self.offset = min(max(self.offset, 0), max(0, len(strips) - VISIBLE_STRIPS))
        return strips[self.offset : self.offset + VISIBLE_STRIPS]

    def scroll(self, amount):
        self.offset -= int(amount)
        self.visible_strips()

    def select_at(self, y):
        visible = self.visible_strips()
        index = int((LIST_TOP - y) // STRIP_HEIGHT)
        if LIST_BOTTOM <= y < LIST_TOP and 0 <= index < len(visible):
            return visible[index].aircraft.id
        return None

    def selected_strip(self, aircraft_id):
        return next(
            (
                strip
                for strip in self.active_strips()
                if strip.aircraft.id == aircraft_id
            ),
            None,
        )

    def drag_target_at(self, x, y):
        if not STRIP_LEFT <= x < STRIP_LEFT + STRIP_COLUMNS[-1]:
            return None
        if not LIST_BOTTOM <= y < LIST_TOP:
            return None
        index = int((LIST_TOP - y) // STRIP_HEIGHT)
        visible = self.visible_strips()
        if index >= len(visible):
            return None
        top = LIST_TOP - index * STRIP_HEIGHT - 2
        bottom = top - STRIP_DRAW_HEIGHT
        if not bottom <= y <= top:
            return None
        after = y < (top + bottom) / 2
        return visible[index], after, bottom if after else top

    def start_drag(self, x, y):
        self.cancel_drag()
        target = self.drag_target_at(x, y)
        if target is not None:
            self.drag_strip = target[0]
            self.drag_start = (x, y)
            self.drag_position = (x, y)

    def move_drag(self, x, y):
        if self.drag_start is None:
            return
        self.drag_position = (x, y)
        if (x - self.drag_start[0]) ** 2 + (
            y - self.drag_start[1]
        ) ** 2 >= DRAG_THRESHOLD**2:
            self.dragging = True

    def cancel_drag(self):
        self.drag_strip = None
        self.drag_start = None
        self.drag_position = None
        self.dragging = False

    def finish_drag(self, x, y):
        source = self.drag_strip
        dragging = self.dragging
        self.cancel_drag()
        if not dragging or source is None:
            return
        if source not in self.active_strips():
            self.error = "STRIP NO LONGER ACTIVE"
            return
        target = self.drag_target_at(x, y)
        if target is None or target[0] is source:
            return
        self.strips.remove(source)
        self.strips.insert(self.strips.index(target[0]) + int(target[1]), source)

    def tooltip_at(self, x, y):
        relative_x = x - STRIP_LEFT
        if not 0 <= relative_x < STRIP_COLUMNS[-1] or not LIST_BOTTOM <= y < LIST_TOP:
            return None
        index = int((LIST_TOP - y) // STRIP_HEIGHT)
        visible = self.visible_strips()
        if index >= len(visible):
            return None
        top = LIST_TOP - index * STRIP_HEIGHT - 2
        from_top = top - y
        if not 0 <= from_top < STRIP_DRAW_HEIGHT:
            return None
        strip = visible[index]
        kind = terminal_strip_fields(strip, self.airport_code)[0]
        if relative_x < STRIP_COLUMNS[1]:
            row = min(int(from_top * 4 / STRIP_DRAW_HEIGHT), 3)
            if row == 1 and relative_x >= STRIP_COLUMNS[1] / 2:
                return "Field 2A: Strip request originator (FDIO). Not simulated."
            return (
                "Field 1: Aircraft identification (callsign).",
                "Field 2: Revision number at FDIO facilities. Not simulated.",
                "Field 3: Aircraft type; may also include formation count, wake category and equipment suffix.",
                "Field 4: Computer identification number when required. Not simulated.",
            )[row]
        if relative_x < STRIP_COLUMNS[2]:
            row = min(int(from_top * 3 / STRIP_DRAW_HEIGHT), 2)
            if row == 0:
                return (
                    "Field 5: Beacon code recorded on the strip. Press 4 to edit; "
                    "the aircraft's radar code is unchanged."
                )
            descriptions = {
                "DEPARTURE": (
                    "Field 6: Proposed departure time. Not simulated.",
                    "Field 7: Requested altitude, in hundreds of feet.",
                ),
                "ARRIVAL": (
                    "Field 6: Previous fix (FDIO) or inbound airway (non-FDIO). Not simulated.",
                    "Field 7: Coordination fix. Not simulated.",
                ),
                "OVERFLIGHT": (
                    "Field 6: Coordination fix. Not simulated.",
                    "Field 7: Facility coordination indicator (FDIO). Not simulated.",
                ),
                "UNKNOWN": (
                    "Field 6: Meaning depends on flight type; not simulated.",
                    "Field 7: Meaning depends on flight type.",
                ),
            }
            return descriptions[kind][row - 1]
        if relative_x < STRIP_COLUMNS[3]:
            row = min(int(from_top * 3 / STRIP_DRAW_HEIGHT), 2)
            if row == 1:
                return (
                    "Field 8A: Optional use under a facility directive. Not simulated."
                )
            if row == 2:
                return (
                    "Field 8B: Resolution advisory report when required; optional "
                    "when voice recording is operational. Not simulated."
                )
            return {
                "DEPARTURE": "Field 8: Departure airport.",
                "ARRIVAL": "Field 8: Estimated arrival time at the coordination fix or destination. Not simulated.",
                "OVERFLIGHT": "Field 8: Estimated arrival time at the coordination fix. Not simulated.",
                "UNKNOWN": "Field 8: Meaning depends on flight type.",
            }[kind]
        if relative_x < STRIP_COLUMNS[4]:
            row = min(max(int((from_top - 2) // 16), 0), 3)
            assigned = (
                "Field 9: Assigned altitude annotation in hundreds of feet. "
                "Editing it does not command the aircraft."
            )
            fix = "Field 9: Fix/time note, a simulator annotation."
            remarks = "Field 9: Clearance or control remarks, a simulator annotation."
            if kind == "DEPARTURE":
                return (
                    "Field 9: Filed route and destination; select the strip for the full route.",
                    assigned,
                    fix,
                    remarks,
                )[row]
            return (
                assigned,
                fix,
                remarks,
                "Field 9A area: Destination shown here by the simulator. FAA use depends on flight type.",
            )[row]
        column = min(
            int(
                (relative_x - STRIP_COLUMNS[4])
                * 3
                / (STRIP_COLUMNS[5] - STRIP_COLUMNS[4])
            ),
            2,
        )
        row = min(int(from_top * 3 / STRIP_DRAW_HEIGHT), 2)
        field = 10 + row * 3 + column
        if field == 10:
            return (
                "Field 10: Simulator runway or pad (PAD means unspecified). "
                "Press 5 to edit. This does not move the aircraft."
            )
        return f"Field {field}: Facility-defined entry. Not simulated."

    def cancel_edit(self):
        self.edit_strip = None
        self.edit_field = None
        self.error = ""

    def on_key_press(self, symbol, selected_id):
        if self.edit_strip is not None:
            if self.edit_strip not in self.active_strips():
                self.cancel_edit()
                self.error = "STRIP NO LONGER ACTIVE"
                return True
            if symbol == arcade.key.ESCAPE:
                self.cancel_edit()
            elif symbol in (arcade.key.ENTER, arcade.key.NUM_ENTER):
                if (
                    self.edit_field == "assigned_altitude"
                    and self.edit_text
                    and not self.edit_text.isdigit()
                ):
                    self.error = "ALTITUDE MUST BE FEET IN DIGITS"
                elif (
                    self.edit_field == "beacon_code"
                    and self.edit_text
                    and (
                        len(self.edit_text) != 4
                        or any(char not in "01234567" for char in self.edit_text)
                    )
                ):
                    self.error = "USE 4 OCTAL DIGITS (0-7) OR EMPTY"
                elif (
                    self.edit_field == "operation_area"
                    and self.edit_text
                    and self.edit_text
                    not in (*self.active_runways, *self.helicopter_pads, "PAD")
                ):
                    self.error = f"USE {' '.join((*self.active_runways, *self.helicopter_pads, 'PAD'))} OR CLEAR"
                else:
                    setattr(self.edit_strip, self.edit_field, self.edit_text.strip())
                    self.cancel_edit()
            elif symbol == arcade.key.BACKSPACE:
                self.edit_text = self.edit_text[:-1]
                self.error = ""
            else:
                if arcade.key.A <= symbol <= arcade.key.Z:
                    char = chr(symbol).upper()
                elif ord("0") <= symbol <= ord("9") or symbol in (
                    ord(" "),
                    ord("-"),
                    ord("/"),
                    ord("."),
                ):
                    char = chr(symbol)
                elif arcade.key.NUM_0 <= symbol <= arcade.key.NUM_9:
                    char = str(symbol - arcade.key.NUM_0)
                else:
                    self.error = "USE A-Z, 0-9, SPACE, - / ."
                    return True
                limit = next(
                    field[2]
                    for field in EDIT_FIELDS.values()
                    if field[0] == self.edit_field
                )
                if len(self.edit_text) >= limit:
                    self.error = f"MAX {limit} CHARACTERS"
                else:
                    self.edit_text += char
                    self.error = ""
            return True
        if symbol in EDIT_FIELDS:
            strip = self.selected_strip(selected_id)
            if strip is not None:
                field, _, _ = EDIT_FIELDS[symbol]
                self.edit_strip = strip
                self.edit_field = field
                self.edit_text = getattr(strip, field)
                self.error = ""
                return True
        return False

    def draw_field(self, text, x, y, width):
        text = str(text)
        self.text.text = text
        if self.text.content_width > width:
            low, high = 0, len(text)
            while low < high:
                middle = (low + high + 1) // 2
                self.text.text = text[:middle] + "..."
                if self.text.content_width <= width:
                    low = middle
                else:
                    high = middle - 1
            self.text.text = text[:low] + "..."
        self.text.position = (x, y)
        self.text.draw()

    def draw(self, selected_id):
        arcade.draw_rect_filled(
            arcade.LBWH(SCREEN_WIDTH, 0, PANEL_WIDTH, SCREEN_HEIGHT),
            (32, 38, 42),
        )
        strips = self.active_strips()
        visible = self.visible_strips()
        self.header.text = (
            f"FLIGHT PROGRESS STRIPS   {len(strips)} ACTIVE\n"
            f"SIM RWY {' '.join(self.active_runways) or '--'} / DRAG / SCROLL"
        )
        self.header.draw()
        for index, strip in enumerate(visible):
            top = LIST_TOP - index * STRIP_HEIGHT
            selected = strip.aircraft.id == selected_id
            left = STRIP_LEFT
            bottom = top - STRIP_HEIGHT + 4
            height = STRIP_DRAW_HEIGHT
            columns = STRIP_COLUMNS
            arcade.draw_rect_filled(
                arcade.LBWH(left, bottom, PANEL_WIDTH - 16, height),
                (255, 246, 196) if selected else (220, 221, 205),
            )
            for x in columns:
                arcade.draw_line(
                    left + x, bottom, left + x, bottom + height, arcade.color.BLACK, 1
                )
            for y in (bottom, bottom + height):
                arcade.draw_line(left, y, left + columns[-1], y, arcade.color.BLACK, 1)
            for row in (1, 2):
                y = bottom + height * row / 3
                arcade.draw_line(
                    left + columns[1], y, left + columns[2], y, arcade.color.BLACK, 1
                )
                arcade.draw_line(
                    left + columns[4], y, left + columns[5], y, arcade.color.BLACK, 1
                )
            for x in (
                columns[4] + (columns[5] - columns[4]) / 3,
                columns[4] + 2 * (columns[5] - columns[4]) / 3,
            ):
                arcade.draw_line(
                    left + x, bottom, left + x, bottom + height, arcade.color.BLACK, 1
                )

            plan = strip.flight_plan
            aircraft = strip.aircraft
            _, block7, block8, block9 = terminal_strip_fields(strip, self.airport_code)
            entries = (
                (columns[0] + 4, 5, aircraft.callsign, columns[1] - columns[0] - 8),
                (
                    columns[0] + 4,
                    37,
                    aircraft.aircraft_model.aircraft_type,
                    columns[1] - columns[0] - 8,
                ),
                (
                    columns[1] + 4,
                    5,
                    strip.beacon_code or "--",
                    columns[2] - columns[1] - 8,
                ),
                (columns[1] + 4, 28, "--", columns[2] - columns[1] - 8),
                (columns[1] + 4, 51, block7, columns[2] - columns[1] - 8),
                (columns[2] + 4, 5, block8, columns[3] - columns[2] - 8),
                (
                    columns[4] + 2,
                    5,
                    strip.operation_area,
                    (columns[5] - columns[4]) / 3 - 4,
                ),
                *(
                    (
                        columns[3] + 4,
                        5 + row * 16,
                        text,
                        columns[4] - columns[3] - 8,
                    )
                    for row, text in enumerate(block9)
                ),
            )
            for x, y, text, width in entries:
                self.draw_field(text, left + x, bottom + height - y, width)
        if self.dragging and self.drag_position is not None:
            target = self.drag_target_at(*self.drag_position)
            if target is not None and target[0] is not self.drag_strip:
                arcade.draw_line(
                    STRIP_LEFT,
                    target[2],
                    STRIP_LEFT + STRIP_COLUMNS[-1],
                    target[2],
                    arcade.color.LIGHT_BLUE,
                    3,
                )
        if self.edit_strip is not None:
            label = next(
                field[1]
                for field in EDIT_FIELDS.values()
                if field[0] == self.edit_field
            )
            footer = (
                f"EDIT {self.edit_strip.aircraft.callsign}: {label}\n"
                f"{self.edit_text}_\nENTER SAVE / ESC CANCEL\n{self.error}"
            )
        else:
            strip = self.selected_strip(selected_id)
            if strip:
                plan = strip.flight_plan
                kind = terminal_strip_fields(strip, self.airport_code)[0]
                footer = (
                    f"SELECTED: {strip.aircraft.callsign}  {kind}\n"
                    f"PLAN {display_airport_identifier(plan.origin) or '?'} > {display_airport_identifier(plan.destination) or '?'}  {strip.aircraft.flight_rules}\n"
                    f"ROUTE {_display_route_to_destination(strip)}\n"
                    f"FILED {plan.altitude if plan.altitude is not None else '?'} FT / {plan.speed if plan.speed is not None else '?'} KT\n"
                    f"ASSIGNED {strip.assigned_altitude or '?'} FT  FIX {strip.fix_time or '?'}\n"
                    f"REMARKS {strip.remarks or '-'}\n"
                    "1 ALT  2 FIX  3 RMK  4 SQ  5 RWY/PAD\n"
                    "ANNOTATIONS ONLY - NO AIRCRAFT COMMAND"
                )
                departure = getattr(strip.aircraft, "departure", None)
                if departure is not None and departure.state == "waiting":
                    footer += "\nAWAITING AUTOMATIC DEPARTURE"
                elif departure is not None and departure.state == "takeoff":
                    footer += "\nDEPARTURE IN PROGRESS"
            else:
                footer = "CLICK A STRIP TO SELECT\nNO STRIP FOR SELECTED AIRCRAFT"
            if self.error:
                footer += f"\n{self.error}"
        self.footer.text = footer
        self.footer.draw()
        self.draw_tooltip()

    def draw_tooltip(self):
        if self.hover_position is None or self.dragging:
            return
        x, y = self.hover_position
        description = self.tooltip_at(x, y)
        if description is None:
            return
        self.tooltip.text = description
        height = self.tooltip.content_height + 16
        left = min(
            max(x + 14, SCREEN_WIDTH + 4),
            SCREEN_WIDTH + PANEL_WIDTH - TOOLTIP_WIDTH - 4,
        )
        top = y - 14 if y >= height + 18 else y + height + 14
        top = min(top, SCREEN_HEIGHT - 4)
        arcade.draw_rect_filled(
            arcade.LBWH(left, top - height, TOOLTIP_WIDTH, height), (32, 38, 42, 255)
        )
        arcade.draw_rect_outline(
            arcade.LBWH(left, top - height, TOOLTIP_WIDTH, height),
            arcade.color.LIGHT_GRAY,
            1,
        )
        self.tooltip.position = (left + 8, top - 8)
        self.tooltip.draw()
