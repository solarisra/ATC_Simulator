import arcade
import numpy as np

# Constants
SCREEN_WIDTH = 1200
SCREEN_HEIGHT = 900
SCREEN_TITLE = "ATC RADAR Display"
ANGLE_TOLERANCE = np.pi / 60
FULL_ROTATION_TIME_SECONDS = 2
FPS = 60
SWEEP_SPEED = 2 * np.pi / (FULL_ROTATION_TIME_SECONDS * FPS)
RADAR_RADIUS = 100  # Radar radius in miles
DISPLAY_RADIUS = 400  # Radius for display purposes in pixels
MAX_DISTANCE_MILES = 100
DEGREE_INTERVAL = 15
CIRCLE_SEGMENTS = 128  # Increase the number of segments for smoother circles
KNOTS_TO_MILES_PER_FRAME = 1 / 3600 / FPS  # Convert knots to miles per frame

VFR_SQUAWK = "1200"
IFR_SQUAWK = "2000"


class AircraftModel:
    """
    Defines the specifications and performance characteristics of different aircraft models.

    :param aircraft_type: The type of the aircraft (e.g., 'C172', 'B737').
    :type aircraft_type: str
    :param climb_rate: Climb rate in feet per second.
    :type climb_rate: float
    :param turn_rate: Turn rate in degrees per second.
    :type turn_rate: float
    :param air_braking_rate: Air braking rate in knots per second.
    :type air_braking_rate: float
    :param thrust_rate: Thrust rate in knots per second.
    :type thrust_rate: float
    :param drag_rate: Drag rate in knots per second.
    :type drag_rate: float
    :param mass: Mass of the aircraft in kilograms.
    :type mass: float
    :param max_speed: Maximum speed in knots.
    :type max_speed: float
    :param cruise_speed: Cruise speed in knots.
    :type cruise_speed: float
    :param service_ceiling: Service ceiling in feet.
    :type service_ceiling: float
    :param fuel_capacity: Fuel capacity in gallons.
    :type fuel_capacity: float
    :param fuel_consumption_rate: Fuel consumption rate in gallons per hour.
    :type fuel_consumption_rate: float
    :param max_range: Maximum range in nautical miles.
    :type max_range: float
    :param stall_speed: Stall speed in knots.
    :type stall_speed: float
    :param wing_span: Wing span in feet.
    :type wing_span: float
    :param length: Length of the aircraft in feet.
    :type length: float
    :param max_takeoff_weight: Maximum takeoff weight in kilograms.
    :type max_takeoff_weight: float
    :param engine_type: Type of the engine (e.g., 'Piston', 'Turbofan').
    :type engine_type: str
    :param passenger_capacity: Passenger capacity.
    :type passenger_capacity: int
    :param landing_gear_type: Type of landing gear (e.g., 'Fixed', 'Retractable').
    :type landing_gear_type: str
    :param avionics_systems: Avionics systems installed.
    :type avionics_systems: str
    :param min_takeoff_distance: Minimum takeoff distance in feet.
    :type min_takeoff_distance: float
    """
    def __init__(self, aircraft_type, climb_rate, turn_rate, air_braking_rate, thrust_rate, drag_rate, mass, max_speed,
                 cruise_speed, service_ceiling, fuel_capacity, fuel_consumption_rate, max_range, stall_speed, wing_span, length,
                 max_takeoff_weight, engine_type, passenger_capacity, landing_gear_type, avionics_systems,
                 min_takeoff_distance):
        self.aircraft_type = aircraft_type
        self.climb_rate = climb_rate
        self.turn_rate = turn_rate
        self.air_braking_rate = air_braking_rate
        self.thrust_rate = thrust_rate
        self.drag_rate = drag_rate
        self.mass = mass
        self.max_speed = max_speed
        self.cruise_speed = cruise_speed
        self.service_ceiling = service_ceiling
        self.fuel_capacity = fuel_capacity
        self.fuel_consumption_rate = fuel_consumption_rate
        self.max_range = max_range
        self.stall_speed = stall_speed
        self.wing_span = wing_span
        self.length = length
        self.max_takeoff_weight = max_takeoff_weight
        self.engine_type = engine_type
        self.passenger_capacity = passenger_capacity
        self.landing_gear_type = landing_gear_type
        self.avionics_systems = avionics_systems
        self.min_takeoff_distance = min_takeoff_distance


class Aircraft:
    """
    Represents an instance of an aircraft with specific attributes and behaviors.

    :param aircraft_id: Unique identifier for the aircraft.
    :type aircraft_id: str
    :param squawk: Squawk code for the aircraft.
    :type squawk: str
    :param mode_s: Mode S transponder code.
    :type mode_s: str
    :param callsign: Callsign of the aircraft.
    :type callsign: str
    :param aircraft_model: Model of the aircraft.
    :type aircraft_model: AircraftModel
    :param angle: Current heading angle of the aircraft in radians.
    :type angle: float
    :param altitude: Current altitude of the aircraft in hundreds of feet.
    :type altitude: float
    :param speed: Current speed of the aircraft in knots.
    :type speed: float
    :param distance: Current distance of the aircraft from the radar in miles.
    :type distance: float
    :param ads_b: ADS-B (Automatic Dependent Surveillance-Broadcast) data.
    :type ads_b: dict
    :param flight_rules: Flight rules (e.g., 'VFR', 'IFR', 'None').
    :type flight_rules: str
    :param landed: Whether the aircraft has landed.
    :type landed: bool
    """
    def __init__(self, aircraft_id, squawk, mode_s, callsign, aircraft_model, angle, altitude, speed, distance, ads_b,
                 flight_rules="None", landed=False):
        self.id = aircraft_id
        self.squawk = squawk
        self.mode_s = mode_s
        self.callsign = callsign
        self.aircraft_model = aircraft_model
        self.angle = angle
        self.altitude = altitude  # Altitude in hundreds of feet
        self.speed = speed
        self.distance = distance
        self.ads_b = ads_b
        self.landed = landed

        # Set squawk code based on flight rules
        if flight_rules == "VFR":
            self.squawk = VFR_SQUAWK
        elif flight_rules == "IFR":
            self.squawk = IFR_SQUAWK

        # Adjust altitude based on heading
        if self.altitude >= 30:  # Considering altitude in hundreds of feet
            heading = np.degrees(self.angle)
            if 0 <= heading < 180:
                self.altitude = ((self.altitude // 20) * 20) + 50  # Odd intervals starting from 5000 feet
            else:
                self.altitude = ((self.altitude // 20) * 20) + 40  # Even intervals starting from 4000 feet

    def on_ground(self):
        """
        Update the distance of the aircraft if it is not landed.
        """
        if not self.landed:
            self.distance = (self.distance + self.speed * KNOTS_TO_MILES_PER_FRAME) % MAX_DISTANCE_MILES

    def update_heading(self, target_angle):
        """
        Update the heading of the aircraft towards the target angle.

        :param target_angle: The target angle to which the aircraft should turn.
        :type target_angle: float
        """
        current_angle_deg = np.degrees(self.angle)
        target_angle_deg = np.degrees(target_angle)
        angle_diff = (target_angle_deg - current_angle_deg + 360) % 360

        if angle_diff > 180:
            angle_diff -= 360

        if abs(angle_diff) < self.aircraft_model.turn_rate:
            self.angle = target_angle
        else:
            angle_change = np.radians(
                self.aircraft_model.turn_rate if angle_diff > 0 else -self.aircraft_model.turn_rate)
            self.angle = (self.angle + angle_change) % (2 * np.pi)

    def update_altitude(self, target_altitude):
        """
        Update the altitude of the aircraft towards the target altitude.

        :param target_altitude: The target altitude in hundreds of feet.
        :type target_altitude: float
        """
        if abs(target_altitude - self.altitude) < self.aircraft_model.climb_rate:
            self.altitude = target_altitude
        else:
            self.altitude += self.aircraft_model.climb_rate if target_altitude > self.altitude else -self.aircraft_model.climb_rate

    def update_speed(self, target_speed):
        """
        Update the speed of the aircraft towards the target speed.

        :param target_speed: The target speed in knots.
        :type target_speed: float
        """
        if abs(target_speed - self.speed) < self.aircraft_model.thrust_rate:
            self.speed = target_speed
        else:
            if target_speed > self.speed:
                self.speed += self.aircraft_model.thrust_rate
            else:
                self.speed -= self.aircraft_model.air_braking_rate

    def update_squawk(self, squawk):
        """
        Update the squawk code of the aircraft.

        :param squawk: The new squawk code.
        :type squawk: str
        """
        self.squawk = squawk


class AircraftList:
    """
    Manages a list of aircraft and updates their positions.
    """
    def __init__(self):
        self.aircraft_list = []

    def add_aircraft(self, aircraft):
        """
        Add an aircraft to the list.

        :param aircraft: The aircraft to be added.
        :type aircraft: Aircraft
        """
        self.aircraft_list.append(aircraft)

    def update_positions(self):
        """
        Update the positions of all aircraft in the list.
        """
        for aircraft in self.aircraft_list:
            aircraft.on_ground()


class RadarSweep:
    """
    Manages the radar sweep animation and logic.
    """
    def __init__(self):
        self.angle = 0
        self.sweep_speed = SWEEP_SPEED

    def update(self):
        """
        Update the radar sweep angle.
        """
        self.angle = (self.angle + self.sweep_speed) % (2 * np.pi)  # Clockwise rotation


class RadarReturnManager:
    """
    Manages the radar returns for aircraft.
    """
    def __init__(self):
        self.radar_returns = []

    def add_return(self, angle, distance):
        """
        Add a radar return at the specified angle and distance.

        :param angle: The angle of the radar return.
        :type angle: float
        :param distance: The distance of the radar return.
        :type distance: float
        """
        self.radar_returns.append([angle, distance, 1.0])  # Add new return with full opacity

    def update(self):
        """
        Update the opacity of radar returns, decreasing over time.
        """
        for radar_return in self.radar_returns:
            radar_return[2] -= 0.1 / 60  # Decrease opacity
        self.radar_returns = [r for r in self.radar_returns if r[2] > 0]  # Keep returns with positive opacity


class PrimaryRadarReturn:
    """
    Handles the primary radar returns based on the radar sweep angle.

    :param radar_return_manager: The manager handling radar returns.
    :type radar_return_manager: RadarReturnManager
    :param aircraft: The aircraft for which the radar return is generated.
    :type aircraft: Aircraft
    :param sweep_angle: The current angle of the radar sweep.
    :type sweep_angle: float
    """
    def __init__(self, radar_return_manager, aircraft, sweep_angle):
        self.radar_return_manager = radar_return_manager
        self.aircraft = aircraft
        self.sweep_angle = sweep_angle
        self.add_return()

    def add_return(self):
        """
        Add a radar return for the aircraft if it is within the sweep angle tolerance.
        """
        angle, distance = self.aircraft.angle, self.aircraft.distance
        if abs(angle - self.sweep_angle) < ANGLE_TOLERANCE:
            self.radar_return_manager.add_return(angle, distance)


class SecondaryRadarReturn:
    """
    Plots the secondary radar return information for an aircraft.

    :param aircraft: The aircraft for which the radar return is plotted.
    :type aircraft: Aircraft
    """
    def __init__(self, aircraft):
        self.aircraft = aircraft

    def plot(self, x, y):
        """
        Plot the secondary radar return on the display.

        :param x: The x-coordinate for the radar return.
        :type x: float
        :param y: The y-coordinate for the radar return.
        :type y: float
        """
        text = (f"{self.aircraft.callsign} {self.aircraft.squawk}\n"
                f"{round(np.degrees(self.aircraft.angle))} {self.aircraft.altitude}\n"
                f"{self.aircraft.aircraft_model.aircraft_type} {self.aircraft.speed}\n"
                f"{self.aircraft.distance:.1f}")

        heading_offset = np.pi  # 180 degrees in radians
        text_x = x + 40 * np.cos(self.aircraft.angle + heading_offset)
        text_y = y + 40 * np.sin(self.aircraft.angle + heading_offset)

        arcade.draw_line(x, y, text_x, text_y, arcade.color.LIGHT_BLUE, 1)
        arcade.draw_text(text, text_x, text_y, arcade.color.LIGHT_BLUE, 10, anchor_x="center", anchor_y="center",
                         multiline=True, width=200)


class RadarDisplay(arcade.Window):
    """
    Main class for managing the radar display window.

    :param aircraft_list: The list of aircraft to be displayed.
    :type aircraft_list: AircraftList
    """
    def __init__(self, aircraft_list):
        super().__init__(SCREEN_WIDTH, SCREEN_HEIGHT, SCREEN_TITLE)
        arcade.set_background_color(arcade.color.BLACK)

        self.aircraft_list = aircraft_list
        self.radar_return_manager = RadarReturnManager()
        self.radar_sweep = RadarSweep()
        self.center_x = SCREEN_WIDTH // 2
        self.center_y = SCREEN_HEIGHT // 2

    def setup(self):
        """
        Set up the radar display (placeholder for any setup operations).
        """
        pass

    def on_draw(self):
        """
        Render the radar display.
        """
        arcade.start_render()

        # Draw static radar overlay
        self.draw_static_overlay()

        # Draw radar sweep
        self.draw_sweep()

        # Draw aircraft
        self.draw_aircraft()

        # Update radar returns
        self.radar_return_manager.update()

    def draw_static_overlay(self):
        """
        Draw the static overlay for the radar display.
        """
        # Draw outer circle
        arcade.draw_circle_outline(self.center_x, self.center_y, DISPLAY_RADIUS, arcade.color.GREEN, 2,
                                   num_segments=CIRCLE_SEGMENTS)

        # Draw headings
        for degree in range(0, 360, DEGREE_INTERVAL):
            radian = np.radians(90 - degree)  # Adjust to navigational coordinates
            x = self.center_x + (DISPLAY_RADIUS + 30) * np.cos(radian)
            y = self.center_y + (DISPLAY_RADIUS + 30) * np.sin(radian)
            arcade.draw_text(f"{degree}", x, y, arcade.color.LIGHT_BLUE, 12, anchor_x="center", anchor_y="center")

    def draw_sweep(self):
        """
        Draw the radar sweep line.
        """
        sweep_angle_radian = np.radians(90 - np.degrees(self.radar_sweep.angle))  # Adjust to navigational coordinates
        end_x = self.center_x + DISPLAY_RADIUS * np.cos(sweep_angle_radian)
        end_y = self.center_y + DISPLAY_RADIUS * np.sin(sweep_angle_radian)
        arcade.draw_line(self.center_x, self.center_y, end_x, end_y, arcade.color.ORANGE, 2)
        self.radar_sweep.update()

    def draw_aircraft(self):
        """
        Draw all aircraft on the radar display.
        """
        for aircraft in self.aircraft_list.aircraft_list:
            aircraft_angle_radian = np.radians(90 - np.degrees(aircraft.angle))  # Adjust to navigational coordinates
            distance_in_pixels = DISPLAY_RADIUS * (aircraft.distance / MAX_DISTANCE_MILES)
            x = self.center_x + distance_in_pixels * np.cos(aircraft_angle_radian)
            y = self.center_y + distance_in_pixels * np.sin(aircraft_angle_radian)
            if distance_in_pixels <= DISPLAY_RADIUS:
                arcade.draw_circle_filled(x, y, 5, arcade.color.BLUE)
                PrimaryRadarReturn(self.radar_return_manager, aircraft, self.radar_sweep.angle)
                SecondaryRadarReturn(aircraft).plot(x, y + 10)

    def update(self, delta_time):
        """
        Update the positions of all aircraft and refresh the display.

        :param delta_time: Time passed since the last update.
        :type delta_time: float
        """
        self.aircraft_list.update_positions()


class ATCFacility:
    """
    Represents an ATC (Air Traffic Control) facility.

    :param name: The name of the facility.
    :type name: str
    :param location: The location of the facility.
    :type location: dict
    :param facilities: List of facilities within this ATC facility.
    :type facilities: list
    """
    def __init__(self, name, location, facilities=None):
        self.name = name
        self.location = location
        self.facilities = facilities if facilities is not None else []


class ATCFacilityFrequencies:
    """
    Represents the frequencies used by an ATC facility.

    :param facility: The ATC facility.
    :type facility: ATCFacility
    :param frequencies: List of frequencies used by the facility.
    :type frequencies: list
    """
    def __init__(self, facility, frequencies=None):
        self.facility = facility
        self.frequencies = frequencies if frequencies is not None else []


class ATC:
    """
    Represents an ATC role within a facility.

    :param role: The role of the ATC.
    :type role: str
    :param facility: The facility in which the ATC operates.
    :type facility: ATCFacility
    """
    def __init__(self, role, facility):
        self.role = role
        self.facility = facility


class FlightPlate:
    """
    Represents a flight plate for navigation procedures.

    :param plate_type: The type of the plate (e.g., 'Approach', 'Departure').
    :type plate_type: str
    :param airport: The airport associated with the plate.
    :type airport: str
    :param procedure: The navigation procedure.
    :type procedure: str
    """
    def __init__(self, plate_type, airport, procedure):
        self.plate_type = plate_type  # Approach, Departure, etc.
        self.airport = airport
        self.procedure = procedure


class RadarMap:
    """
    Represents a radar map for a specific area.

    :param area: The area covered by the radar map.
    :type area: str
    :param map_data: The data of the map.
    :type map_data: dict
    """
    def __init__(self, area, map_data):
        self.area = area
        self.map_data = map_data


class AirportDiagram:
    """
    Represents an airport diagram.

    :param airport: The airport for which the diagram is created.
    :type airport: str
    :param diagram_data: The data of the airport diagram.
    :type diagram_data: dict
    """
    def __init__(self, airport, diagram_data):
        self.airport = airport
        self.diagram_data = diagram_data


class NavigationAid:
    """
    Represents a navigation aid.

    :param name: The name of the navigation aid.
    :type name: str
    :param navaid_type: The type of the navigation aid (e.g., 'VOR', 'NDB', 'ILS').
    :type navaid_type: str
    :param location: The location of the navigation aid.
    :type location: dict
    :param frequency: The frequency of the navigation aid.
    :type frequency: float
    """
    def __init__(self, name, navaid_type, location, frequency):
        self.name = name
        self.navaid_type = navaid_type  # VOR, NDB, ILS, etc.
        self.location = location
        self.frequency = frequency


class FlightStrip:
    """
    Represents a flight strip for tracking flight information.

    :param flight_id: The unique identifier for the flight.
    :type flight_id: str
    :param aircraft: The aircraft associated with the flight.
    :type aircraft: Aircraft
    :param flight_plan: The flight plan for the flight.
    :type flight_plan: FlightPlan
    """
    def __init__(self, flight_id, aircraft, flight_plan):
        self.flight_id = flight_id
        self.aircraft = aircraft
        self.flight_plan = flight_plan


class FlightPlan:
    """
    Represents a flight plan.

    :param flight_id: The unique identifier for the flight.
    :type flight_id: str
    :param origin: The origin airport.
    :type origin: str
    :param destination: The destination airport.
    :type destination: str
    :param route: The route of the flight.
    :type route: str
    :param altitude: The planned altitude in hundreds of feet.
    :type altitude: float
    :param speed: The planned speed in knots.
    :type speed: float
    """
    def __init__(self, flight_id, origin, destination, route, altitude, speed):
        self.flight_id = flight_id
        self.origin = origin
        self.destination = destination
        self.route = route
        self.altitude = altitude
        self.speed = speed


class Weather:
    """
    Represents weather information for a specific location.

    :param location: The location of the weather report.
    :type location: dict
    :param temperature: The temperature in degrees Celsius.
    :type temperature: float
    :param wind: The wind speed and direction.
    :type wind: dict
    :param visibility: The visibility in miles.
    :type visibility: float
    :param conditions: The weather conditions (e.g., 'Clear', 'Rain').
    :type conditions: str
    """
    def __init__(self, location, temperature, wind, visibility, conditions):
        self.location = location
        self.temperature = temperature
        self.wind = wind
        self.visibility = visibility
        self.conditions = conditions


if __name__ == "__main__":
    # Sample Aircraft Models
    cessna_172 = AircraftModel(
        aircraft_type='C172',
        climb_rate=7.5,  # feet per second (450 feet per minute)
        turn_rate=3,  # degrees per second
        air_braking_rate=1,  # knots per second
        thrust_rate=1.5,  # knots per second
        drag_rate=0.2,  # knots per second
        mass=767,  # kg
        max_speed=122,  # knots
        cruise_speed=110,  # knots
        service_ceiling=14000,  # feet
        fuel_capacity=56,  # gallons
        fuel_consumption_rate=8.5,  # gallons per hour
        max_range=518,  # nautical miles
        stall_speed=48,  # knots
        wing_span=36.1,  # feet
        length=27.2,  # feet
        max_takeoff_weight=1049,  # kg
        engine_type="Piston",
        passenger_capacity=4,
        landing_gear_type="Fixed",
        avionics_systems="Basic",
        min_takeoff_distance=800  # feet
    )

    boeing_737 = AircraftModel(
        aircraft_type='B737',
        climb_rate=30,  # feet per second (1800 feet per minute)
        turn_rate=2.5,  # degrees per second
        air_braking_rate=2,  # knots per second
        thrust_rate=3,  # knots per second
        drag_rate=0.5,  # knots per second
        mass=41413,  # kg
        max_speed=485,  # knots
        cruise_speed=460,  # knots
        service_ceiling=41000,  # feet
        fuel_capacity=6840,  # gallons
        fuel_consumption_rate=800,  # gallons per hour
        max_range=2900,  # nautical miles
        stall_speed=125,  # knots
        wing_span=112.5,  # feet
        length=129.5,  # feet
        max_takeoff_weight=70308,  # kg
        engine_type="Turbofan",
        passenger_capacity=160,
        landing_gear_type="Retractable",
        avionics_systems="Advanced",
        min_takeoff_distance=8000  # feet
    )

    f18e = AircraftModel(
        aircraft_type='F18E',
        climb_rate=60,  # feet per second (3600 feet per minute)
        turn_rate=10,  # degrees per second
        air_braking_rate=5,  # knots per second
        thrust_rate=5,  # knots per second
        drag_rate=1,  # knots per second
        mass=14752,  # kg
        max_speed=1190,  # knots
        cruise_speed=1050,  # knots
        service_ceiling=50000,  # feet
        fuel_capacity=1100,  # gallons
        fuel_consumption_rate=10,  # gallons per minute (typical)
        max_range=1100,  # nautical miles
        stall_speed=110,  # knots
        wing_span=44.9,  # feet
        length=60.3,  # feet
        max_takeoff_weight=23543,  # kg
        engine_type="Turbofan",
        passenger_capacity=1,
        landing_gear_type="Retractable",
        avionics_systems="Military",
        min_takeoff_distance=1000  # feet
    )

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
