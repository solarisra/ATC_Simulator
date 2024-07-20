from aircraft import AircraftModel

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
