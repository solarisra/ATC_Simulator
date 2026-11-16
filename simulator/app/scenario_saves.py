"""In-app controls for named scenario saves."""

import arcade

from simulator.app.scenario_storage import saved_names

SAVE_X = 390
SAVE_Y = 210
SAVE_WIDTH = 860
SAVE_HEIGHT = 600
SAVE_ROW_TOP = 700
SAVE_ROW_HEIGHT = 32
SAVE_PAGE_SIZE = 10


class ScenarioSavesDialog:
    def __init__(self, mode):
        if mode not in ("save", "load"):
            raise ValueError("Invalid scenario save dialog")
        self.mode = mode
        self.names = saved_names()
        self.name = ""
        self.selected = 0
        self.error = ""
        self.confirm_overwrite = False

    def visible_names(self):
        page = self.selected // SAVE_PAGE_SIZE
        return self.names[page * SAVE_PAGE_SIZE : (page + 1) * SAVE_PAGE_SIZE]

    def key(self, symbol, modifiers):
        if self.mode == "load":
            if symbol == arcade.key.UP:
                self.selected = max(0, self.selected - 1)
            elif symbol == arcade.key.DOWN:
                self.selected = min(max(0, len(self.names) - 1), self.selected + 1)
            elif symbol == arcade.key.LEFT:
                self.selected = max(0, self.selected - SAVE_PAGE_SIZE)
            elif symbol == arcade.key.RIGHT:
                self.selected = min(
                    max(0, len(self.names) - 1), self.selected + SAVE_PAGE_SIZE
                )
        else:
            if symbol == arcade.key.BACKSPACE:
                self.name = self.name[:-1]
            elif arcade.key.A <= symbol <= arcade.key.Z:
                self.name += chr(symbol).upper()
            elif arcade.key.KEY_0 <= symbol <= arcade.key.KEY_9:
                self.name += chr(symbol)
            elif arcade.key.NUM_0 <= symbol <= arcade.key.NUM_9:
                self.name += str(symbol - arcade.key.NUM_0)
            elif symbol == arcade.key.SPACE:
                self.name += " "
            elif symbol == arcade.key.MINUS:
                self.name += "_" if modifiers & arcade.key.MOD_SHIFT else "-"
            self.name = self.name[:48]
        self.error = ""

    def click(self, x, y):
        if self.mode != "load" or not SAVE_X + 25 <= x < SAVE_X + SAVE_WIDTH - 25:
            return
        for index, _ in enumerate(self.visible_names()):
            center = SAVE_ROW_TOP - index * SAVE_ROW_HEIGHT
            if abs(y - center) <= 14:
                self.selected = self.selected // SAVE_PAGE_SIZE * SAVE_PAGE_SIZE + index
                return

    def selected_name(self):
        if self.mode == "save":
            return self.name
        if not self.names:
            raise ValueError("There are no saved scenarios")
        return self.names[self.selected]
