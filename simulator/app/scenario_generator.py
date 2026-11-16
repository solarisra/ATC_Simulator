"""Interactive settings for Yuma's scenario generator."""

import secrets

import arcade

from Locations.Yuma.Scenarios.generator import (
    AIRCRAFT_TYPES,
    OPERATIONS,
    TRAFFIC_LEVELS,
    GeneratorSettings,
)

DIALOG_X = 320
DIALOG_Y = 160
DIALOG_WIDTH = 1000
DIALOG_HEIGHT = 710
ROW_TOP = 770
ROW_HEIGHT = 45
MINUS_X = 950
PLUS_X = 1160


class ScenarioGeneratorDialog:
    def __init__(self):
        self.seed = str(secrets.randbits(32))
        self.volume = "moderate"
        self.operations: dict[str, int] = dict.fromkeys(OPERATIONS, 1)
        self.aircraft_types: dict[str, int] = dict.fromkeys(AIRCRAFT_TYPES, 1)
        self.selected = 0
        self.error = ""

    def rows(self):
        return [
            ("Random seed", self.seed or "(enter seed)"),
            (
                "Traffic volume",
                f"{self.volume.title()} ({TRAFFIC_LEVELS[self.volume]})",
            ),
            *[(name.title(), str(self.operations[name])) for name in OPERATIONS],
            *[
                (name.title(), str(self.aircraft_types[name]))
                for name in AIRCRAFT_TYPES
            ],
        ]

    def settings(self):
        if not self.seed:
            raise ValueError("Enter a random seed")
        settings = GeneratorSettings(
            seed=int(self.seed),
            volume=self.volume,
            operations=self.operations.copy(),
            aircraft_types=self.aircraft_types.copy(),
        )
        settings.validate()
        return settings

    def adjust(self, step):
        if self.selected == 1:
            levels = tuple(TRAFFIC_LEVELS)
            index = max(0, min(len(levels) - 1, levels.index(self.volume) + step))
            self.volume = levels[index]
        elif 2 <= self.selected < 2 + len(OPERATIONS):
            name = OPERATIONS[self.selected - 2]
            self.operations[name] = max(0, self.operations[name] + step)
        elif self.selected >= 2 + len(OPERATIONS):
            name = AIRCRAFT_TYPES[self.selected - 2 - len(OPERATIONS)]
            self.aircraft_types[name] = max(0, self.aircraft_types[name] + step)
        self.error = ""

    def key(self, symbol):
        if symbol == arcade.key.UP:
            self.selected = max(0, self.selected - 1)
        elif symbol == arcade.key.DOWN:
            self.selected = min(len(self.rows()) - 1, self.selected + 1)
        elif symbol == arcade.key.LEFT:
            self.adjust(-1)
        elif symbol == arcade.key.RIGHT:
            self.adjust(1)
        elif symbol == arcade.key.R:
            self.seed = str(secrets.randbits(32))
            self.error = ""
        elif self.selected == 0:
            if symbol == arcade.key.BACKSPACE:
                self.seed = self.seed[:-1]
            elif arcade.key.KEY_0 <= symbol <= arcade.key.KEY_9:
                self.seed = (self.seed + chr(symbol))[:18]
            elif arcade.key.NUM_0 <= symbol <= arcade.key.NUM_9:
                self.seed = (self.seed + str(symbol - arcade.key.NUM_0))[:18]
            self.error = ""

    def click(self, x, y):
        for index in range(len(self.rows())):
            center = ROW_TOP - index * ROW_HEIGHT
            if (
                DIALOG_X + 20 <= x <= DIALOG_X + DIALOG_WIDTH - 20
                and abs(y - center) <= 19
            ):
                self.selected = index
                if index > 0 and MINUS_X - 20 <= x <= MINUS_X + 20:
                    self.adjust(-1)
                elif index > 0 and PLUS_X - 20 <= x <= PLUS_X + 20:
                    self.adjust(1)
                return
