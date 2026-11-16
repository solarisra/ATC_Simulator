import argparse

import arcade

from locations.Yuma.Scenarios.sample_data import (
    HELICOPTER_SAMPLES,
    RUNWAY_03_SAMPLES,
    SAMPLE_PLANS,
    SMALL_CIVILIAN_SAMPLES,
)
from locations.Yuma.Scenarios.yuma import create_sample_strips
from simulator.app.application import ApplicationWindow

__all__ = [
    "HELICOPTER_SAMPLES",
    "RUNWAY_03_SAMPLES",
    "SAMPLE_PLANS",
    "SMALL_CIVILIAN_SAMPLES",
    "create_sample_strips",
    "main",
]


def main():
    parser = argparse.ArgumentParser(description="Run the ATC simulator")
    parser.add_argument("--voice", action="store_true", help="enable local voice radio")
    args = parser.parse_args()
    app = ApplicationWindow()
    app.setup()
    if args.voice:
        app.enable_voice()
    arcade.run()


if __name__ == "__main__":
    main()
