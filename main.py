import arcade
import numpy as np
from constants import SCREEN_WIDTH, SCREEN_HEIGHT, SCREEN_TITLE, SWEEP_SPEED, ANGLE_TOLERANCE, DISPLAY_RADIUS, DEGREE_INTERVAL, CIRCLE_SEGMENTS
from aircraft import Aircraft, AircraftList
from radar import RadarDisplay
from aircraft_models import cessna_172, boeing_737, f18e


if __name__ == "__main__":
    # Sample Aircraft List
    list_of_aircraft = AircraftList()
    list_of_aircraft.add_aircraft(
        Aircraft('A1', '1200', 'ID1001', 'N135TC', cessna_172, np.pi / 6, 50, 120, 50, {"lat": 34.05, "lon": -118.25},
                 flight_rules="VFR"))
    list_of_aircraft.add_aircraft(
        Aircraft('A2', '2000', 'ID1002', 'AMF2118', boeing_737, np.pi / 3, 150, 450, 75, {"lat": 40.71, "lon": -74.00},
                 flight_rules="IFR"))
    list_of_aircraft.add_aircraft(
        Aircraft('A3', '2000', 'ID1003', 'CAP279', f18e, np.pi / 2, 40, 600, 30, {"lat": 51.51, "lon": -0.13},
                 flight_rules="None"))

    # Start the radar display simulation
    app = RadarDisplay(list_of_aircraft)
    app.setup()
    arcade.run()
