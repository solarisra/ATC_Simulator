import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import arcade

from Locations.Cascade.Sectors.medford import create_location as create_medford_location
from simulator.core.constants import SCREEN_HEIGHT
from simulator.core.location import RadioFrequency
from simulator.display.radar import RadarDisplay
from simulator.radio.communications import (
    COMMUNICATIONS_HEIGHT,
    CommunicationsPanel,
    RadioState,
    _button_rect,
    _interfacility_rect,
    _line_rect,
)


def make_panel():
    with patch(
        "simulator.radio.communications.arcade.Text",
        side_effect=lambda *args, **kwargs: Mock(),
    ):
        return CommunicationsPanel()


class CommunicationsTests(unittest.TestCase):
    def test_single_band_and_paired_channels_keep_their_own_columns(self):
        location = create_medford_location()
        with patch("simulator.radio.communications.arcade.Text"):
            panel = CommunicationsPanel(
                location.radio_frequencies, location.coordination_lines
            )
        positions = {
            channel.identifier: position
            for channel, position in zip(panel.channels, panel.channel_positions)
        }
        self.assertEqual(positions["approach_low"], (2, 0))
        self.assertEqual(positions["zse_king_low"], (3, 0))
        self.assertEqual(positions["zse_king_high"], (3, 1))
        self.assertEqual(panel.lines, [])

    def test_panel_uses_location_frequencies_without_mutating_configuration(self):
        frequencies = (
            RadioFrequency("custom", "TEST", "VHF", "123.450", RadioState.LISTEN),
        )
        with patch("simulator.radio.communications.arcade.Text"):
            panel = CommunicationsPanel(frequencies)
        channel = panel.channels[0]
        self.assertEqual((channel.identifier, channel.frequency), ("custom", "123.450"))
        self.assertEqual(channel.state, RadioState.LISTEN)
        channel.cycle()
        self.assertEqual(frequencies[0].initial_state, RadioState.LISTEN)
        self.assertEqual(panel.channels[0].state, RadioState.OFF)

    def test_draw_uses_compact_labels_and_identifies_each_radio_band(self):
        panel = make_panel()
        with (
            patch("simulator.radio.communications.arcade.draw_rect_filled"),
            patch("simulator.radio.communications.arcade.draw_rect_outline"),
        ):
            panel.draw()
        self.assertEqual(
            [label.text.split("\n")[0] for label in panel.labels],
            [
                f"{name} ({band})"
                for name in (
                    "EMERGENCY",
                    "KNYL TWR",
                    "KNYL APP",
                    "KNYL DEP",
                    "KNYL ENR",
                    "ZLA SEC 9",
                    "ZLA SEC 10",
                    "ZLA SEC 31",
                    "ZAB SEC 42",
                )
                for band in ("VHF", "UHF")
            ],
        )
        self.assertEqual(
            [label.text.rsplit("  ", 1)[0] for label in panel.line_labels],
            ["KNYL TWR (LOCAL)", "KNYL RANGE CONTROL", "KNYL APP/DEP", "KNYL ENR"],
        )

    def test_channels_cycle_independently_and_mic_transmits_to_all_on(self):
        panel = make_panel()
        channels = {channel.identifier: channel for channel in panel.channels}
        self.assertEqual(len(channels), 18)
        self.assertEqual(channels["emergency_low"].state, RadioState.LISTEN)
        self.assertEqual(channels["emergency_high"].state, RadioState.LISTEN)
        self.assertEqual(channels["approach_low"].state, RadioState.ON)
        tower = channels["tower_low"]
        rect = _button_rect(1, 0)
        panel.press(rect.center_x, rect.center_y)
        self.assertEqual(tower.state, RadioState.ON)
        self.assertIn(tower, panel.monitored)
        self.assertEqual(panel.transmitting, ())
        mic = panel.mic_rect
        panel.press(mic.center_x, mic.center_y)
        self.assertEqual(
            {channel.identifier for channel in panel.transmitting},
            {"tower_low", "approach_low"},
        )
        self.assertNotIn(channels["emergency_low"], panel.transmitting)
        panel.press(rect.center_x, rect.center_y)
        self.assertEqual(tower.state, RadioState.LISTEN)
        self.assertIn(tower, panel.monitored)
        self.assertEqual(
            [channel.identifier for channel in panel.transmitting], ["approach_low"]
        )
        panel.press(rect.center_x, rect.center_y)
        self.assertEqual(tower.state, RadioState.OFF)
        self.assertNotIn(tower, panel.monitored)
        self.assertEqual(
            [channel.identifier for channel in panel.transmitting], ["approach_low"]
        )
        panel.release()
        self.assertFalse(panel.mic_hot)
        self.assertEqual(panel.transmitting, ())

    def test_only_active_radio_buttons_brighten_during_transmissions(self):
        panel = make_panel()

        def channel_colors():
            with (
                patch("simulator.radio.communications.arcade.draw_rect_filled") as fill,
                patch("simulator.radio.communications.arcade.draw_rect_outline"),
            ):
                panel.draw()
            return {
                channel.identifier: fill.call_args_list[index + 2].args[1]
                for index, channel in enumerate(panel.channels)
            }

        idle = channel_colors()
        panel.keyboard_ptt = True
        transmitting = channel_colors()
        self.assertGreater(sum(transmitting["approach_low"]), sum(idle["approach_low"]))
        self.assertEqual(transmitting["emergency_low"], idle["emergency_low"])
        self.assertEqual(transmitting["enroute_low"], idle["enroute_low"])
        panel.keyboard_ptt = False
        panel.pilot_channel = "emergency_low"
        receiving = channel_colors()
        self.assertGreater(sum(receiving["emergency_low"]), sum(idle["emergency_low"]))
        self.assertEqual(receiving["approach_low"], idle["approach_low"])
        panel.pilot_channel = None
        self.assertEqual(channel_colors(), idle)

    def test_scenario_frequencies_and_sector_31_transmission(self):
        panel = make_panel()
        with (
            patch("simulator.radio.communications.arcade.draw_rect_filled"),
            patch("simulator.radio.communications.arcade.draw_rect_outline"),
        ):
            panel.draw()
        labels = {
            channel.identifier: label.text
            for channel, label in zip(panel.channels, panel.labels)
        }
        for identifier, frequency in {
            "enroute_low": "132.275",
            "enroute_high": "292.200",
            "zla9_low": "128.600",
            "zla9_high": "291.700",
            "zla10_low": "128.150",
            "zla10_high": "285.600",
            "zla31_low": "126.775",
            "zla31_high": "307.800",
            "zab42_low": "125.250",
            "zab42_high": "307.300",
        }.items():
            with self.subTest(channel=identifier):
                self.assertIn(f"{frequency} MHZ", labels[identifier])

        for row in (0, 1):
            rect = _button_rect(7, row)
            panel.press(rect.center_x, rect.center_y)
        mic = panel.mic_rect
        panel.press(mic.center_x, mic.center_y)
        self.assertEqual(
            {channel.identifier for channel in panel.transmitting},
            {"approach_low", "zla31_low", "zla31_high"},
        )

    def test_panel_clicks_do_not_change_radar_selection_and_release_mic(self):
        panel = make_panel()
        strip_panel = Mock()
        display = SimpleNamespace(
            communications_panel=panel,
            strip_panel=strip_panel,
            selected_aircraft_id="A1",
            scratchpad_edit_id="A1",
            handoff_choice_id=None,
            coordination_draft=None,
            clearance_draft=None,
            handoff_message="",
        )
        rect = _button_rect(1, 0)
        RadarDisplay.on_mouse_press(
            display, rect.center_x, rect.center_y, arcade.MOUSE_BUTTON_LEFT, 0
        )
        self.assertEqual(display.selected_aircraft_id, "A1")
        self.assertEqual(display.scratchpad_edit_id, "A1")
        strip_panel.cancel_edit.assert_not_called()
        mic = panel.mic_rect
        RadarDisplay.on_mouse_press(
            display, mic.center_x, mic.center_y, arcade.MOUSE_BUTTON_LEFT, 0
        )
        self.assertTrue(panel.mic_hot)
        RadarDisplay.on_mouse_release(display, 20, 20, arcade.MOUSE_BUTTON_LEFT, 0)
        self.assertFalse(panel.mic_hot)
        RadarDisplay.on_mouse_press(
            display, mic.center_x, mic.center_y, arcade.MOUSE_BUTTON_LEFT, 0
        )
        RadarDisplay.on_mouse_leave(display, 0, 0)
        self.assertFalse(panel.mic_hot)
        RadarDisplay.on_mouse_press(
            display, mic.center_x, mic.center_y, arcade.MOUSE_BUTTON_LEFT, 0
        )
        RadarDisplay.on_deactivate(display)
        self.assertFalse(panel.mic_hot)

    def test_spacebar_and_mouse_holds_are_independent(self):
        panel = make_panel()
        display = Mock(spec=RadarDisplay)
        display.communications_panel = panel
        display.strip_panel = Mock(drag_strip=None, edit_strip=None)
        display.scratchpad_edit_id = None

        RadarDisplay.on_key_press(display, arcade.key.SPACE, 0)
        RadarDisplay.on_key_press(display, arcade.key.SPACE, 0)
        self.assertTrue(panel.mic_hot)
        self.assertEqual(
            [channel.identifier for channel in panel.transmitting], ["approach_low"]
        )
        RadarDisplay.on_mouse_release(display, 20, 20, arcade.MOUSE_BUTTON_LEFT, 0)
        display.strip_panel.finish_drag.assert_called_once_with(20, 20)
        RadarDisplay.on_mouse_leave(display, 0, 0)
        self.assertTrue(panel.mic_hot)

        mic = panel.mic_rect
        panel.press(mic.center_x, mic.center_y)
        RadarDisplay.on_key_release(display, arcade.key.SPACE, 0)
        self.assertTrue(panel.mic_hot)
        RadarDisplay.on_mouse_release(display, 20, 20, arcade.MOUSE_BUTTON_LEFT, 0)
        self.assertFalse(panel.mic_hot)

        panel.press(mic.center_x, mic.center_y)
        RadarDisplay.on_key_press(display, arcade.key.SPACE, 0)
        RadarDisplay.on_mouse_release(display, 20, 20, arcade.MOUSE_BUTTON_LEFT, 0)
        self.assertTrue(panel.mic_hot)
        panel.press(mic.center_x, mic.center_y)
        RadarDisplay.on_deactivate(display)
        self.assertFalse(panel.mic_hot)
        self.assertFalse(panel.mouse_ptt)
        self.assertFalse(panel.keyboard_ptt)

    def test_spacebar_edits_text_without_transmitting(self):
        panel = make_panel()
        display = Mock(spec=RadarDisplay)
        display.communications_panel = panel
        display.strip_panel = Mock(drag_strip=None, edit_strip=object())
        display.selected_aircraft_id = "A1"
        display.scratchpad_edit_id = None
        RadarDisplay.on_key_press(display, arcade.key.SPACE, 0)
        display.strip_panel.on_key_press.assert_called_once_with(arcade.key.SPACE, "A1")
        self.assertFalse(panel.mic_hot)

        display.strip_panel.edit_strip = None
        RadarDisplay.on_key_press(display, arcade.key.SPACE, 0)
        self.assertTrue(panel.mic_hot)
        display.clearance_draft = SimpleNamespace(text="HDG")
        RadarDisplay.on_key_release(display, arcade.key.SPACE, 0)
        self.assertFalse(panel.mic_hot)
        RadarDisplay.on_key_press(display, arcade.key.SPACE, 0)
        self.assertEqual(display.clearance_draft.text, "HDG ")
        self.assertFalse(panel.mic_hot)

    def test_every_button_controls_its_own_channel(self):
        panel = make_panel()
        for index, position in enumerate(panel.channel_positions):
            with self.subTest(channel=panel.channels[index].identifier):
                before = [channel.state for channel in panel.channels]
                rect = _button_rect(*position)
                self.assertTrue(panel.press(rect.center_x, rect.center_y))
                changed = [
                    i
                    for i, channel in enumerate(panel.channels)
                    if channel.state != before[i]
                ]
                self.assertEqual(changed, [index])

    def test_intrafacility_lines_toggle_independently_of_radio(self):
        panel = make_panel()
        self.assertEqual(
            [line.identifier for line in panel.lines],
            ["tower_local", "range_control", "approach_departure", "enroute"],
        )
        self.assertFalse(any(line.hot for line in panel.lines))
        radio_states = [channel.state for channel in panel.channels]
        for index, line in enumerate(panel.lines):
            rect = _line_rect(index)
            self.assertTrue(panel.press(rect.center_x, rect.center_y))
            self.assertTrue(line.hot)
            self.assertFalse(panel.mic_hot)
        self.assertTrue(all(line.hot for line in panel.lines))
        self.assertEqual([channel.state for channel in panel.channels], radio_states)

        panel.release()
        self.assertTrue(all(line.hot for line in panel.lines))
        rect = _line_rect(0)
        panel.press(rect.center_x, rect.center_y)
        self.assertFalse(panel.lines[0].hot)
        self.assertTrue(all(line.hot for line in panel.lines[1:]))

        mic = panel.mic_rect
        panel.press(mic.center_x, mic.center_y)
        self.assertTrue(panel.mic_hot)
        self.assertFalse(panel.lines[0].hot)
        self.assertTrue(all(line.hot for line in panel.lines[1:]))

    def test_intrafacility_click_preserves_selection_and_survives_focus_loss(self):
        panel = make_panel()
        display = Mock(spec=RadarDisplay)
        display.communications_panel = panel
        display.selected_aircraft_id = "A1"
        display.strip_panel = Mock()
        rect = _line_rect(0)
        RadarDisplay.on_mouse_press(
            display, int(rect.center_x), int(rect.center_y), arcade.MOUSE_BUTTON_LEFT, 0
        )
        self.assertTrue(panel.lines[0].hot)
        self.assertEqual(display.selected_aircraft_id, "A1")
        RadarDisplay.on_deactivate(display)
        self.assertTrue(panel.lines[0].hot)

    def test_interfacility_lines_toggle_independently_and_fit_the_panel(self):
        panel = make_panel()
        self.assertEqual(
            [line.label for line in panel.interfacility_lines],
            ["ZLA SECTOR 9", "ZLA SECTOR 10", "ZLA SECTOR 31", "ZAB SECTOR 42"],
        )
        states = [channel.state for channel in panel.channels]
        for index, line in enumerate(panel.interfacility_lines):
            rect = _interfacility_rect(index)
            self.assertTrue(panel.press(rect.center_x, rect.center_y))
            self.assertTrue(line.hot)
            self.assertGreaterEqual(rect.bottom, SCREEN_HEIGHT)
            self.assertLessEqual(rect.top, SCREEN_HEIGHT + COMMUNICATIONS_HEIGHT)
        self.assertEqual([channel.state for channel in panel.channels], states)
        self.assertFalse(any(line.hot for line in panel.lines))
        self.assertFalse(panel.mic_hot)
        with (
            patch("simulator.radio.communications.arcade.draw_rect_filled"),
            patch("simulator.radio.communications.arcade.draw_rect_outline"),
        ):
            panel.draw()
        self.assertEqual(
            [label.text for label in panel.interfacility_labels],
            [f"{line.label}  HOT" for line in panel.interfacility_lines],
        )
        rect = _interfacility_rect(0)
        panel.press(rect.center_x, rect.center_y)
        self.assertFalse(panel.interfacility_lines[0].hot)
        self.assertTrue(all(line.hot for line in panel.interfacility_lines[1:]))

    def test_grouped_controls_are_compact_and_do_not_overlap(self):
        panel = make_panel()
        radio_rects = [_button_rect(*position) for position in panel.channel_positions]
        intra_rects = [_line_rect(i) for i in range(len(panel.lines))]
        inter_rects = [
            _interfacility_rect(i) for i in range(len(panel.interfacility_lines))
        ]
        rectangles = [*radio_rects, *intra_rects, *inter_rects, panel.mic_rect]
        for i, first in enumerate(rectangles):
            self.assertGreaterEqual(first.bottom, SCREEN_HEIGHT)
            self.assertLessEqual(first.top, SCREEN_HEIGHT + COMMUNICATIONS_HEIGHT)
            for second in rectangles[i + 1 :]:
                self.assertFalse(
                    first.left < second.right
                    and second.left < first.right
                    and first.bottom < second.top
                    and second.bottom < first.top
                )
        self.assertLess(max(rect.right for rect in radio_rects), intra_rects[0].left)
        self.assertLess(max(rect.right for rect in intra_rects), inter_rects[0].left)

    def test_scroll_above_radar_does_not_scroll_or_zoom(self):
        display = SimpleNamespace(strip_panel=Mock(), radar_viewport=Mock())
        RadarDisplay.on_mouse_scroll(display, 100, SCREEN_HEIGHT + 1, 0, 1)
        display.strip_panel.scroll.assert_not_called()
        display.radar_viewport.zoom_by.assert_not_called()


if __name__ == "__main__":
    unittest.main()
