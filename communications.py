"""Simulated radio and intrafacility communications panel."""

from dataclasses import dataclass
from enum import StrEnum

import arcade

from constants import SCREEN_HEIGHT, SCREEN_WIDTH
from flight_strips import PANEL_WIDTH

COMMUNICATIONS_HEIGHT = 120
WINDOW_WIDTH = SCREEN_WIDTH + PANEL_WIDTH
PANEL_COLUMNS = 9
PANEL_MARGIN = 8
PANEL_GAP = 6
BUTTON_WIDTH = (
    SCREEN_WIDTH - 2 * PANEL_MARGIN - (PANEL_COLUMNS - 1) * PANEL_GAP
) / PANEL_COLUMNS
BUTTON_HEIGHT = 36
ROW_TOPS = (SCREEN_HEIGHT + 94, SCREEN_HEIGHT + 50)
LINE_WIDTH = (PANEL_WIDTH - 2 * PANEL_MARGIN - PANEL_GAP) / 2


class RadioState(StrEnum):
    OFF = "OFF"
    LISTEN = "LISTEN"
    ON = "ON"


@dataclass
class RadioChannel:
    identifier: str
    label: str
    band: str
    frequency: str | None = None
    state: RadioState = RadioState.OFF

    def cycle(self):
        self.state = {
            RadioState.ON: RadioState.LISTEN,
            RadioState.LISTEN: RadioState.OFF,
            RadioState.OFF: RadioState.ON,
        }[self.state]


@dataclass
class IntrafacilityLine:
    identifier: str
    label: str
    hot: bool = False


def _button_rect(column, row):
    left = PANEL_MARGIN + column * (BUTTON_WIDTH + PANEL_GAP)
    return arcade.LBWH(left, ROW_TOPS[row] - BUTTON_HEIGHT, BUTTON_WIDTH, BUTTON_HEIGHT)


def _line_rect(column, row):
    left = SCREEN_WIDTH + PANEL_MARGIN + column * (LINE_WIDTH + PANEL_GAP)
    return arcade.LBWH(left, ROW_TOPS[row] - BUTTON_HEIGHT, LINE_WIDTH, BUTTON_HEIGHT)


class CommunicationsPanel:
    def __init__(self):
        self.channels = [
            RadioChannel(
                "emergency_low", "EMERGENCY", "VHF", "121.500", RadioState.LISTEN
            ),
            RadioChannel(
                "emergency_high", "EMERGENCY", "UHF", "243.000", RadioState.LISTEN
            ),
            RadioChannel("tower_low", "KNYL TWR", "VHF", "119.300"),
            RadioChannel("tower_high", "KNYL TWR", "UHF", "377.075"),
            RadioChannel("approach_low", "KNYL APP", "VHF", "124.700", RadioState.ON),
            RadioChannel("approach_high", "KNYL APP", "UHF", "371.975"),
            RadioChannel("departure_low", "KNYL DEP", "VHF", "125.500"),
            RadioChannel("departure_high", "KNYL DEP", "UHF", "282.325"),
            RadioChannel("enroute_low", "KNYL ENR", "VHF", "132.275"),
            RadioChannel("enroute_high", "KNYL ENR", "UHF", "292.200"),
            RadioChannel("zla9_low", "ZLA SEC 9", "VHF", "128.600"),
            RadioChannel("zla9_high", "ZLA SEC 9", "UHF", "291.700"),
            RadioChannel("zla10_low", "ZLA SEC 10", "VHF", "128.150"),
            RadioChannel("zla10_high", "ZLA SEC 10", "UHF", "285.600"),
            RadioChannel("zla31_low", "ZLA SEC 31", "VHF", "126.775"),
            RadioChannel("zla31_high", "ZLA SEC 31", "UHF", "307.800"),
            RadioChannel("zab42_low", "ZAB SEC 42", "VHF", "125.250"),
            RadioChannel("zab42_high", "ZAB SEC 42", "UHF", "307.300"),
        ]
        self.channel_positions = tuple(
            (index // 2, index % 2) for index in range(len(self.channels))
        )
        self.lines = [
            IntrafacilityLine("tower_local", "KNYL TWR (LOCAL)"),
            IntrafacilityLine("range_control", "KNYL RANGE CONTROL"),
            IntrafacilityLine("approach_departure", "KNYL APP/DEP"),
            IntrafacilityLine("enroute", "KNYL ENR"),
        ]
        self.mouse_ptt = False
        self.keyboard_ptt = False
        self.header = arcade.Text(
            "",
            PANEL_MARGIN,
            SCREEN_HEIGHT + COMMUNICATIONS_HEIGHT - 4,
            arcade.color.WHITE,
            11,
            anchor_y="top",
            font_name="Consolas",
        )
        self.labels = [
            arcade.Text(
                "",
                _button_rect(column, row).left + 5,
                _button_rect(column, row).top - 3,
                arcade.color.WHITE,
                8,
                anchor_y="top",
                multiline=True,
                width=int(BUTTON_WIDTH - 10),
                font_name="Consolas",
            )
            for column, row in self.channel_positions
        ]
        self.line_header = arcade.Text(
            "INTRAFACILITY (NON-RADIO)",
            SCREEN_WIDTH + PANEL_MARGIN,
            SCREEN_HEIGHT + COMMUNICATIONS_HEIGHT - 4,
            arcade.color.WHITE,
            11,
            anchor_y="top",
            font_name="Consolas",
        )
        self.line_labels = [
            arcade.Text(
                "",
                _line_rect(index % 2, index // 2).left + 6,
                _line_rect(index % 2, index // 2).top - 3,
                arcade.color.WHITE,
                9,
                anchor_y="top",
                multiline=True,
                width=int(LINE_WIDTH - 12),
                font_name="Consolas",
            )
            for index in range(len(self.lines))
        ]
        mic_rect = self.mic_rect
        self.mic_label = arcade.Text(
            "",
            mic_rect.center_x,
            mic_rect.center_y,
            arcade.color.WHITE,
            10,
            anchor_x="center",
            anchor_y="center",
            font_name="Consolas",
        )

    @property
    def monitored(self):
        return tuple(
            channel for channel in self.channels if channel.state != RadioState.OFF
        )

    @property
    def mic_hot(self):
        return self.mouse_ptt or self.keyboard_ptt

    @property
    def transmitting(self):
        if not self.mic_hot:
            return ()
        return tuple(
            channel for channel in self.channels if channel.state == RadioState.ON
        )

    @property
    def mic_rect(self):
        return arcade.LBWH(SCREEN_WIDTH - 190, SCREEN_HEIGHT + 98, 182, 20)

    def press(self, x, y):
        if (
            not 0 <= x < WINDOW_WIDTH
            or not SCREEN_HEIGHT <= y < SCREEN_HEIGHT + COMMUNICATIONS_HEIGHT
        ):
            return False
        if self.mic_rect.point_in_rect((x, y)):
            self.mouse_ptt = True
            return True
        for channel, (column, row) in zip(self.channels, self.channel_positions):
            if _button_rect(column, row).point_in_rect((x, y)):
                channel.cycle()
                return True
        for index, line in enumerate(self.lines):
            if _line_rect(index % 2, index // 2).point_in_rect((x, y)):
                line.hot = not line.hot
                return True
        return True

    def release(self):
        self.mouse_ptt = False

    def release_all(self):
        self.mouse_ptt = False
        self.keyboard_ptt = False

    def draw(self):
        arcade.draw_rect_filled(
            arcade.LBWH(0, SCREEN_HEIGHT, WINDOW_WIDTH, COMMUNICATIONS_HEIGHT),
            (25, 32, 38),
        )
        arcade.draw_rect_filled(
            arcade.LBWH(
                SCREEN_WIDTH, SCREEN_HEIGHT, PANEL_WIDTH, COMMUNICATIONS_HEIGHT
            ),
            (33, 40, 47),
        )
        self.header.text = (
            f"COMMUNICATIONS  |  SIMULATED ONLY  |  MIC {'HOT' if self.mic_hot else 'COLD'}"
            f"  |  TRANSMITTING: {len(self.transmitting)}"
        )
        self.header.draw()
        self.line_header.draw()
        colors = {
            RadioState.OFF: (65, 69, 73),
            RadioState.LISTEN: (46, 85, 116),
            RadioState.ON: (40, 108, 65),
        }
        for channel, position, label in zip(
            self.channels, self.channel_positions, self.labels
        ):
            rect = _button_rect(*position)
            arcade.draw_rect_filled(rect, colors[channel.state])
            arcade.draw_rect_outline(rect, arcade.color.LIGHT_GRAY, 1)
            frequency = (
                f"{channel.frequency} MHZ" if channel.frequency else "UNVERIFIED"
            )
            label.text = (
                f"{channel.label} ({channel.band})\n{frequency} | {channel.state}"
            )
            label.draw()
        for index, (line, label) in enumerate(zip(self.lines, self.line_labels)):
            rect = _line_rect(index % 2, index // 2)
            arcade.draw_rect_filled(rect, (150, 57, 48) if line.hot else (65, 69, 73))
            arcade.draw_rect_outline(rect, arcade.color.LIGHT_GRAY, 1)
            label.text = f"{line.label}\n{'HOT' if line.hot else 'COLD'}"
            label.draw()
        mic_rect = self.mic_rect
        arcade.draw_rect_filled(
            mic_rect, (150, 57, 48) if self.mic_hot else (75, 75, 80)
        )
        arcade.draw_rect_outline(mic_rect, arcade.color.LIGHT_GRAY, 1)
        self.mic_label.text = "MIC HOT" if self.mic_hot else "HOLD TO TALK [SPACE]"
        self.mic_label.draw()
