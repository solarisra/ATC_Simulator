def knots_to_kmh(knots):
    return knots * 1.852


def kmh_to_knots(kmh):
    return kmh / 1.852


class AircraftType:
    def __init__(self, name, base_accel, cruise_speed, max_speed,
                 climb_rate, descent_rate, turn_rate, radar_cross_section, icon='✈'):
        self.name = name
        self.base_accel = base_accel
        self.cruise_speed = cruise_speed
        self.max_speed = max_speed
        self.climb_rate = climb_rate
        self.descent_rate = descent_rate
        self.turn_rate = turn_rate
        self.radar_cross_section = radar_cross_section
        self.icon = icon

    def __repr__(self):
        return f"<AircraftType {self.name}>"

    def get_acceleration(self, altitude, velocity):
        base_accel = self.base_accel
        cruise_speed = self.cruise_speed

        # Thrust drops as velocity nears cruise
        thrust_factor = max(0.2, 1 - (velocity / cruise_speed))

        # Altitude reduces efficiency
        altitude_factor = 1.0 if altitude < 10000 else 0.8 if altitude < 20000 else 0.6

        # Drag increases with velocity squared
        drag_factor = 1 / (1 + (velocity / cruise_speed) ** 2)

        return base_accel * thrust_factor * altitude_factor * drag_factor

    def get_deceleration(self, altitude, velocity):
        accel = self.get_acceleration(altitude, velocity)
        return min(accel * 1.5, 5.0)  # Cap to prevent excessive decel


f16_type = AircraftType(
    name="f16",
    base_accel=10.0,
    cruise_speed=kmh_to_knots(1500),
    max_speed=kmh_to_knots(2200),
    climb_rate=300.0,
    descent_rate=330.0,
    turn_rate=30,
    radar_cross_section=1.0,
    icon="✈"
)

boeing_737 = AircraftType(
    name="airliner",
    base_accel=2.0,  # Relatively slow acceleration
    cruise_speed=kmh_to_knots(850),
    max_speed=kmh_to_knots(920),  # km/h
    climb_rate=55.77,  # ft/sec
    descent_rate=65.62,  # ft/sec
    turn_rate=5,  # degrees per second (shallow)
    radar_cross_section=25.0,  # m² (large and visible)
    icon="✈"
)

cessna_172 = AircraftType(
    name="cessna_172",
    base_accel=0.8,  # Very slow acceleration
    cruise_speed=kmh_to_knots(226),  # km/h (~122 knots)
    max_speed=kmh_to_knots(302),  # km/h (~163 knots Vne)
    climb_rate=11.81,  # ft/sec
    descent_rate=13.12,  # ft/sec
    turn_rate=10,  # degrees per second (gentle)
    radar_cross_section=5.0,  # m² (small plane)
    icon="✈"
)