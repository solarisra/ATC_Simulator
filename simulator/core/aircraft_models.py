from simulator.core.aircraft import AircraftModel

# Sample Aircraft Models
# Performance varies by configuration and flight conditions. Maneuver rates,
# fuel consumption, and any values not given by the linked sources are
# approximate simulation values, not operating limitations.
# For helicopters, wing_span is rotor diameter and stall_speed is not applicable.
# The V-22's wing_span is its width with rotors turning.
cessna_172 = AircraftModel(
    aircraft_type="C172",
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
    min_takeoff_distance=800,  # feet
)

boeing_737 = AircraftModel(
    aircraft_type="B737",
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
    min_takeoff_distance=8000,  # feet
)

f18e = AircraftModel(
    aircraft_type="F18E",
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
    fuel_consumption_rate=600,  # gallons per hour (typical)
    max_range=1100,  # nautical miles
    stall_speed=110,  # knots
    wing_span=44.9,  # feet
    length=60.3,  # feet
    max_takeoff_weight=29937,  # kg
    engine_type="Turbofan",
    passenger_capacity=1,
    landing_gear_type="Retractable",
    avionics_systems="Military",
    min_takeoff_distance=1000,  # feet
)

# Airbus A320-200: https://contentzone.eurocontrol.int/aircraftperformance/details.aspx?ICAO=A320
airbus_a320 = AircraftModel(
    aircraft_type="A320",
    climb_rate=33.3,
    turn_rate=2.5,
    air_braking_rate=2,
    thrust_rate=3,
    drag_rate=0.5,
    mass=42000,
    max_speed=490,
    cruise_speed=450,
    service_ceiling=39000,
    fuel_capacity=6300,
    fuel_consumption_rate=700,
    max_range=2700,
    stall_speed=120,
    wing_span=111.9,
    length=123.3,
    max_takeoff_weight=73900,
    engine_type="Turbofan",
    passenger_capacity=180,
    landing_gear_type="Retractable",
    avionics_systems="Advanced",
    min_takeoff_distance=7185,
)

# Boeing 767-300 freighter: https://www.boeing.com/commercial/767
boeing_767_freighter = AircraftModel(
    aircraft_type="B763",
    climb_rate=41.7,
    turn_rate=2,
    air_braking_rate=2,
    thrust_rate=2.5,
    drag_rate=0.5,
    mass=90000,
    max_speed=490,
    cruise_speed=460,
    service_ceiling=43000,
    fuel_capacity=23800,
    fuel_consumption_rate=1400,
    max_range=3255,
    stall_speed=130,
    wing_span=156.1,
    length=180.3,
    max_takeoff_weight=186880,
    engine_type="Turbofan",
    passenger_capacity=0,
    landing_gear_type="Retractable",
    avionics_systems="Advanced",
    min_takeoff_distance=9500,
)

# Grand Caravan EX: https://cessna.txtav.com/en/turboprop/grand-caravan-ex
cessna_208 = AircraftModel(
    aircraft_type="C208",
    climb_rate=21.25,
    turn_rate=3,
    air_braking_rate=1.5,
    thrust_rate=1.5,
    drag_rate=0.3,
    mass=2409,
    max_speed=185,
    cruise_speed=170,
    service_ceiling=25000,
    fuel_capacity=335,
    fuel_consumption_rate=55,
    max_range=912,
    stall_speed=61,
    wing_span=52.1,
    length=41.6,
    max_takeoff_weight=3995,
    engine_type="Turboprop",
    passenger_capacity=13,
    landing_gear_type="Fixed",
    avionics_systems="Advanced",
    min_takeoff_distance=2160,
)

# Piper PA-28: https://contentzone.eurocontrol.int/aircraftperformance/details.aspx?ICAO=P28A
piper_pa28 = AircraftModel(
    aircraft_type="P28A",
    climb_rate=11.7,
    turn_rate=3,
    air_braking_rate=1,
    thrust_rate=1.5,
    drag_rate=0.2,
    mass=700,
    max_speed=125,
    cruise_speed=110,
    service_ceiling=12000,
    fuel_capacity=48,
    fuel_consumption_rate=9,
    max_range=500,
    stall_speed=50,
    wing_span=35.1,
    length=23.6,
    max_takeoff_weight=1100,
    engine_type="Piston",
    passenger_capacity=3,
    landing_gear_type="Fixed",
    avionics_systems="Basic",
    min_takeoff_distance=985,
)

# Citation M2: https://cessna.txtav.com/en/citation/m2-gen2
cessna_citation_m2 = AircraftModel(
    aircraft_type="C25M",
    climb_rate=61.6,
    turn_rate=3,
    air_braking_rate=2,
    thrust_rate=2.5,
    drag_rate=0.4,
    mass=3171,
    max_speed=404,
    cruise_speed=390,
    service_ceiling=41000,
    fuel_capacity=492,
    fuel_consumption_rate=150,
    max_range=1550,
    stall_speed=90,
    wing_span=47.25,
    length=42.6,
    max_takeoff_weight=4853,
    engine_type="Turbofan",
    passenger_capacity=6,
    landing_gear_type="Retractable",
    avionics_systems="Advanced",
    min_takeoff_distance=3210,
)

# Airbus H135: https://www.airbus.com/en/products-services/helicopters/civil-helicopters/h135/h135-technical-information
airbus_h135 = AircraftModel(
    aircraft_type="EC35",
    climb_rate=25,
    turn_rate=3,
    air_braking_rate=2,
    thrust_rate=2,
    drag_rate=0.3,
    mass=1562,
    max_speed=136,
    cruise_speed=125,
    service_ceiling=20000,
    fuel_capacity=177,
    fuel_consumption_rate=60,
    max_range=342,
    stall_speed=None,
    wing_span=34.1,
    length=40.22,
    max_takeoff_weight=2980,
    engine_type="Turboshaft",
    passenger_capacity=6,
    landing_gear_type="Skids",
    avionics_systems="Advanced",
    min_takeoff_distance=0,
)

# F-16C: https://contentzone.eurocontrol.int/aircraftperformance/details.aspx?ICAO=F16
f16 = AircraftModel(
    aircraft_type="F16",
    climb_rate=83.3,
    turn_rate=5,
    air_braking_rate=4,
    thrust_rate=5,
    drag_rate=1,
    mass=8570,
    max_speed=1200,
    cruise_speed=480,
    service_ceiling=50000,
    fuel_capacity=1050,
    fuel_consumption_rate=700,
    max_range=2000,
    stall_speed=120,
    wing_span=32.8,
    length=49.2,
    max_takeoff_weight=19190,
    engine_type="Turbofan",
    passenger_capacity=0,
    landing_gear_type="Retractable",
    avionics_systems="Military",
    min_takeoff_distance=3280,
)

# C-130J-30: https://www.lockheedmartin.com/en-us/products/c130/c-130j-30-super-hercules.html
# https://contentzone.eurocontrol.int/aircraftperformance/details.aspx?ICAO=C30J
lockheed_c130j = AircraftModel(
    aircraft_type="C30J",
    climb_rate=25,
    turn_rate=2.5,
    air_braking_rate=2,
    thrust_rate=2,
    drag_rate=0.5,
    mass=38000,
    max_speed=356,
    cruise_speed=330,
    service_ceiling=33000,
    fuel_capacity=6300,
    fuel_consumption_rate=700,
    max_range=2100,
    stall_speed=100,
    wing_span=132.5,
    length=112.9,
    max_takeoff_weight=70300,
    engine_type="Turboprop",
    passenger_capacity=128,
    landing_gear_type="Retractable",
    avionics_systems="Military",
    min_takeoff_distance=3120,
)

# UH-60M: https://www.lockheedmartin.com/en-us/products/sikorsky-uh-60m-black-hawk-helicopter.html
sikorsky_uh60 = AircraftModel(
    aircraft_type="H60",
    climb_rate=21.7,
    turn_rate=3,
    air_braking_rate=2,
    thrust_rate=2,
    drag_rate=0.3,
    mass=5600,
    max_speed=160,
    cruise_speed=140,
    service_ceiling=19000,
    fuel_capacity=360,
    fuel_consumption_rate=120,
    max_range=320,
    stall_speed=None,
    wing_span=53.7,
    length=64.8,
    max_takeoff_weight=9979,
    engine_type="Turboshaft",
    passenger_capacity=12,
    landing_gear_type="Fixed",
    avionics_systems="Military",
    min_takeoff_distance=0,
)

# B-52H: https://www.boeing.com/defense/fighters-and-bombers/b-52
boeing_b52 = AircraftModel(
    aircraft_type="B52",
    climb_rate=25,
    turn_rate=2,
    air_braking_rate=2,
    thrust_rate=2,
    drag_rate=0.5,
    mass=83915,
    max_speed=565,
    cruise_speed=415,
    service_ceiling=50000,
    fuel_capacity=46500,
    fuel_consumption_rate=2500,
    max_range=7647,
    stall_speed=140,
    wing_span=185,
    length=159.3,
    max_takeoff_weight=221353,
    engine_type="Turbofan",
    passenger_capacity=0,
    landing_gear_type="Retractable",
    avionics_systems="Military",
    min_takeoff_distance=9840,
)

# F-5E Tiger II: https://contentzone.eurocontrol.int/aircraftperformance/details.aspx?ICAO=F5
f5_tiger_ii = AircraftModel(
    aircraft_type="F5",
    climb_rate=80,
    turn_rate=5,
    air_braking_rate=4,
    thrust_rate=5,
    drag_rate=1,
    mass=4349,
    max_speed=917,
    cruise_speed=480,
    service_ceiling=51000,
    fuel_capacity=677,
    fuel_consumption_rate=500,
    max_range=1300,
    stall_speed=120,
    wing_span=26.6,
    length=47.6,
    max_takeoff_weight=11187,
    engine_type="Turbojet",
    passenger_capacity=0,
    landing_gear_type="Retractable",
    avionics_systems="Military",
    min_takeoff_distance=5905,
)

# MV-22B: https://www.navair.navy.mil/product/MV-22B-Osprey
# https://www.boeing.com/defense/military-rotorcraft/v-22-osprey
v22_osprey = AircraftModel(
    aircraft_type="V22",
    climb_rate=38,
    turn_rate=3,
    air_braking_rate=2,
    thrust_rate=2,
    drag_rate=0.4,
    mass=15000,
    max_speed=305,
    cruise_speed=250,
    service_ceiling=25000,
    fuel_capacity=1700,
    fuel_consumption_rate=250,
    max_range=880,
    stall_speed=None,
    wing_span=84.6,
    length=57.3,
    max_takeoff_weight=23859,
    engine_type="Turboshaft",
    passenger_capacity=24,
    landing_gear_type="Retractable",
    avionics_systems="Military",
    min_takeoff_distance=0,
)

# F-35C carrier variant, operated by the Navy and Marine Corps:
# https://contentzone.eurocontrol.int/aircraftperformance/details.aspx?ICAO=F35
f35c = AircraftModel(
    aircraft_type="F35",
    climb_rate=83.3,
    turn_rate=5,
    air_braking_rate=4,
    thrust_rate=5,
    drag_rate=1,
    mass=15785,
    max_speed=1035,
    cruise_speed=520,
    service_ceiling=50000,
    fuel_capacity=2900,
    fuel_consumption_rate=700,
    max_range=1200,
    stall_speed=120,
    wing_span=43,
    length=51.5,
    max_takeoff_weight=31751,
    engine_type="Turbofan",
    passenger_capacity=0,
    landing_gear_type="Retractable",
    avionics_systems="Military",
    min_takeoff_distance=1500,
)

# CH-53D Sea Stallion: https://www.helis.com/database/model/CH-53D-Sea-Stallion/
sikorsky_ch53d = AircraftModel(
    aircraft_type="H53",
    climb_rate=25,
    turn_rate=2.5,
    air_braking_rate=2,
    thrust_rate=2,
    drag_rate=0.4,
    mass=10740,
    max_speed=150,
    cruise_speed=130,
    service_ceiling=18000,
    fuel_capacity=1500,
    fuel_consumption_rate=300,
    max_range=540,
    stall_speed=None,
    wing_span=72.2,
    length=88.3,
    max_takeoff_weight=19050,
    engine_type="Turboshaft",
    passenger_capacity=37,
    landing_gear_type="Retractable",
    avionics_systems="Military",
    min_takeoff_distance=0,
)

# CH-46E Sea Knight: https://www.navair.navy.mil/product/MV-22B-Osprey
boeing_ch46e = AircraftModel(
    aircraft_type="H46",
    climb_rate=20,
    turn_rate=3,
    air_braking_rate=2,
    thrust_rate=2,
    drag_rate=0.4,
    mass=7000,
    max_speed=145,
    cruise_speed=120,
    service_ceiling=14000,
    fuel_capacity=400,
    fuel_consumption_rate=150,
    max_range=330,
    stall_speed=None,
    wing_span=51,
    length=84.3,
    max_takeoff_weight=11022,
    engine_type="Turboshaft",
    passenger_capacity=25,
    landing_gear_type="Fixed",
    avionics_systems="Military",
    min_takeoff_distance=0,
)

# AV-8B Harrier II: https://www.navair.navy.mil/product/AV-8B-Harrier
av8b_harrier = AircraftModel(
    aircraft_type="AV8B",
    climb_rate=70,
    turn_rate=5,
    air_braking_rate=4,
    thrust_rate=4,
    drag_rate=0.8,
    mass=6336,
    max_speed=585,
    cruise_speed=450,
    service_ceiling=50000,
    fuel_capacity=920,
    fuel_consumption_rate=500,
    max_range=1200,
    stall_speed=110,
    wing_span=30.3,
    length=46.3,
    max_takeoff_weight=14060,
    engine_type="Turbofan",
    passenger_capacity=0,
    landing_gear_type="Retractable",
    avionics_systems="Military",
    min_takeoff_distance=0,
)

# AH-1W Super Cobra: https://www.navair.navy.mil/product/AH-1W-Super-Cobra
bell_ah1w = AircraftModel(
    aircraft_type="AH1W",
    climb_rate=27,
    turn_rate=3,
    air_braking_rate=2,
    thrust_rate=2,
    drag_rate=0.4,
    mass=4899,
    max_speed=190,
    cruise_speed=150,
    service_ceiling=12000,
    fuel_capacity=295,
    fuel_consumption_rate=120,
    max_range=320,
    stall_speed=None,
    wing_span=48,
    length=58,
    max_takeoff_weight=6690,
    engine_type="Turboshaft",
    passenger_capacity=0,
    landing_gear_type="Skids",
    avionics_systems="Military",
    min_takeoff_distance=0,
)

# HH-1N Huey SAR, a twin-engine H-1 variant:
# https://contentzone.eurocontrol.int/aircraftperformance/details.aspx?ICAO=UH1
bell_hh1n = AircraftModel(
    aircraft_type="UH1N",
    climb_rate=16.7,
    turn_rate=3,
    air_braking_rate=2,
    thrust_rate=2,
    drag_rate=0.3,
    mass=2400,
    max_speed=140,
    cruise_speed=110,
    service_ceiling=15000,
    fuel_capacity=223,
    fuel_consumption_rate=80,
    max_range=275,
    stall_speed=None,
    wing_span=48,
    length=57.1,
    max_takeoff_weight=4763,
    engine_type="Turboshaft",
    passenger_capacity=6,
    landing_gear_type="Skids",
    avionics_systems="Military",
    min_takeoff_distance=0,
)
