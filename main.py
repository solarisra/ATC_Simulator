import arcade

from radar import RadarDisplay
from sample_data import (
    HELICOPTER_SAMPLES,
    RUNWAY_03_SAMPLES,
    SAMPLE_PLANS,
    SMALL_CIVILIAN_SAMPLES,
)
from sample_scenario import create_sample_strips, create_yuma_scenario

__all__ = [
    "HELICOPTER_SAMPLES",
    "RUNWAY_03_SAMPLES",
    "SAMPLE_PLANS",
    "SMALL_CIVILIAN_SAMPLES",
    "create_sample_strips",
    "main",
]


def main():
    aircraft_list, facility, strips = create_yuma_scenario()
    app = RadarDisplay(aircraft_list, facility, flight_strips=strips)
    app.setup()
    arcade.run()


if __name__ == "__main__":
    main()
