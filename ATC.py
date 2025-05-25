from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
from geopy.distance import distance
from geopy.point import Point
import numpy as np
from matplotlib.ticker import FixedLocator
import sys


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
    cruise_speed=1200,
    max_speed=2200,
    climb_rate=300.0,
    descent_rate=330.0,
    turn_rate=30,
    radar_cross_section=1.0,
    icon="✈"
)

boeing_737 = AircraftType(
    name="airliner",
    base_accel=2.0,  # Relatively slow acceleration
    cruise_speed=850,  # km/h
    max_speed=920,  # km/h
    climb_rate=55.77,  # ft/sec
    descent_rate=65.62,  # ft/sec
    turn_rate=5,  # degrees per second (shallow)
    radar_cross_section=25.0,  # m² (large and visible)
    icon="✈"
)

cessna_172 = AircraftType(
    name="cessna_172",
    base_accel=0.8,  # Very slow acceleration
    cruise_speed=226,  # km/h (~122 knots)
    max_speed=302,  # km/h (~163 knots Vne)
    climb_rate=11.81,  # ft/sec
    descent_rate=13.12,  # ft/sec
    turn_rate=10,  # degrees per second (gentle)
    radar_cross_section=5.0,  # m² (small plane)
    icon="✈"
)


class Aircraft:
    def __init__(self, aircraft_type, bearing_deg, velocity, aircraft_id, mode_a, mode_c, mode_s, ads_b):
        self.aircraft_type = aircraft_type
        self.bearing_deg = bearing_deg  # aircraft bearing
        self.velocity = velocity  # knots
        self.id = aircraft_id  # aircraft game id
        self.mode_a = mode_a  # 4-digit squawk code
        self.mode_c = mode_c  # Altitude (based on pressure altitude)
        self.mode_s = mode_s  # Selective
        self.ads_b = ads_b  # ADS-B: Position, altitude, velocity, ID.
        #   - Currently used in game for instantiation location (lat, long).

        self.assigned_altitude = mode_c
        self.assigned_speed = aircraft_type.cruise_speed
        self.assigned_bearing_deg = bearing_deg

        self.tick_duration_minutes = 0.05 / 60

    def __repr__(self):
        return (f"<Aircraft {self.id} | {self.aircraft_type.name} | "
                f"{self.velocity:.1f} kt | FL{int(self.mode_c / 100):03d} | "
                f"Hdg {self.bearing_deg:.1f}°>")

    @property
    def bearing_rad(self):
        """Return the bearing in radians for internal calculations."""
        return np.radians(self.bearing_deg % 360)

    @property
    def vertical_status(self):
        delta = self.assigned_altitude - self.mode_c
        if abs(delta) < 50:
            return "Level"
        return "Climbing" if delta > 0 else "Descending"

    @property
    def speed_status(self):
        delta = self.assigned_speed - self.velocity
        if abs(delta) < 5:
            return "Cruise"
        return "Accelerating" if delta > 0 else "Slowing"

    @property
    def heading_status(self):
        delta = (self.assigned_bearing_deg - self.bearing_deg + 360) % 360
        if delta > 180:
            delta -= 360
        return "Turning" if abs(delta) > 1 else "Steady"

    def update_position(self):
        origin = Point(self.ads_b["lat"], self.ads_b["lon"])
        bearing = self.bearing_deg % 360
        speed_kph = self.velocity * 1.852  # 1 knot = 1.852 km/h
        tick_duration_hours = self.tick_duration_minutes / 60  # 10-second tick
        distance_km = speed_kph * tick_duration_hours

        new_location = distance(kilometers=distance_km).destination(origin, bearing)
        self.ads_b["lat"] = new_location.latitude
        self.ads_b["lon"] = new_location.longitude

    def update_speed(self, target_speed=None):
        """
        Adjust velocity toward a target speed using acceleration/deceleration rates.
        If no target is given, assume the aircraft is trying to reach cruise speed.
        """
        type_profile = self.aircraft_type
        current_speed = self.velocity
        altitude = self.mode_c  # Assuming in feet, you could convert to meters

        if target_speed is None:
            target_speed = type_profile.cruise_speed

        if current_speed < target_speed:
            accel = type_profile.get_acceleration(altitude, current_speed)
            self.velocity = min(self.velocity + accel, type_profile.max_speed)
        elif current_speed > target_speed:
            decel = type_profile.get_deceleration(altitude, current_speed)
            self.velocity = max(self.velocity - decel, 0)

    def update_squawk(self, mode_a):
        """Simulate the update of the aircraft's data."""
        self.mode_a = str(int(self.mode_a) + 1).zfill(4)

    def update_altitude(self, assigned_altitude):
        """
        Adjust altitude toward the assigned target using aircraft type climb/descent rate.
        """
        assigned_altitude = max(0, assigned_altitude)  # Prevent going below ground level
        current_altitude = self.mode_c
        type_profile = self.aircraft_type
        delta = assigned_altitude - current_altitude

        if abs(delta) < 50:  # Close enough, stop climbing/descending
            self.mode_c = assigned_altitude
            return

        if delta > 0:
            # Climb
            climb = type_profile.climb_rate * self.tick_duration_minutes
            self.mode_c = min(current_altitude + climb, assigned_altitude)
        else:
            # Descend
            descent = type_profile.descent_rate * self.tick_duration_minutes
            self.mode_c = max(current_altitude - descent, assigned_altitude)

    def update_bearing(self, new_bearing_deg):
        delta = (new_bearing_deg - self.bearing_deg + 360) % 360
        if delta > 180:
            delta -= 360  # Shortest turn direction

        turn_amount = self.aircraft_type.turn_rate * self.tick_duration_minutes
        if abs(delta) <= turn_amount:
            self.bearing_deg = new_bearing_deg
        else:
            self.bearing_deg += turn_amount if delta > 0 else -turn_amount
            self.bearing_deg %= 360

    def update_mode_s(self, mode_s):
        self.mode_s = mode_s

    def update_flight_profile(self):
        self.update_speed(self.assigned_speed)
        self.update_altitude(self.assigned_altitude)
        self.update_bearing(self.assigned_bearing_deg)


class RadarCanvas(FigureCanvas):
    def __init__(self):
        self.fig, self.ax = plt.subplots(subplot_kw={'projection': 'polar'})
        super().__init__(self.fig)

        self.fig.patch.set_facecolor('black')
        self.ax.set_facecolor('black')
        self.ax.set_theta_zero_location('N')
        self.ax.set_theta_direction(-1)
        self.ax.set_ylim(0, 100)
        self.ax.set_yticklabels([])
        self.ax.set_xticks(np.deg2rad(np.arange(0, 360, 15)))
        self.ax.set_xticklabels([str(d) for d in range(0, 360, 15)], color='lightblue')
        self.ax.spines['polar'].set_color('lightblue')

        self.draw_radar_sweep(0)

    def draw_radar_sweep(self, angle_rad):
        self.ax.clear()
        self.setup_plot()
        self.ax.plot([angle_rad, angle_rad], [0, 100], color='orange')
        self.draw()

    def setup_plot(self):
        self.ax.set_theta_zero_location('N')
        self.ax.set_theta_direction(-1)
        self.ax.set_ylim(0, 100)
        self.ax.set_yticklabels([])
        self.ax.set_xticks(np.deg2rad(np.arange(0, 360, 15)))
        self.ax.set_xticklabels([str(d) for d in range(0, 360, 15)], color='lightblue')
        self.ax.spines['polar'].set_color('lightblue')
        self.ax.set_facecolor('black')


class RadarWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ATC Radar Display (PyQt5)")
        self.setGeometry(100, 100, 1000, 800)

        self.canvas = RadarCanvas()
        layout = QVBoxLayout()
        layout.addWidget(self.canvas)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        self.angle = 0
        self.timer_id = self.startTimer(50)  # 20 fps

        # Initialize aircraft
        self.aircraft_list = [
            Aircraft(boeing_737, 170, boeing_737.cruise_speed, 'A1',
                     '1200', 10000, 'ASA1046',
                     {"lat": 42.923, "lon": -123.283}),
            Aircraft(f16_type, 250, f16_type.cruise_speed, 'A2',
                     '1201', 15000, 'TBIRD16',
                     {"lat": 42.445, "lon": -122.321}),
            Aircraft(cessna_172, 350, cessna_172.cruise_speed, 'A3',
                     '1202', 5000, 'N914DK',
                     {"lat": 41.746, "lon": -122.631})
        ]

    def timerEvent(self, event):
        self.angle = (self.angle + np.pi / 60) % (2 * np.pi)
        self.canvas.draw_radar_sweep(self.angle)

        for aircraft in self.aircraft_list:
            aircraft.update_flight_profile()
            aircraft.update_position()



"""
class RadarDisplay(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("ATC RADAR Display")
        self.geometry("1200x900")

        # Set up the radar display
        self.radar_origin = {"lat": 42.3736, "lon": -122.872}  # MFR location
        self.fig, self.ax = plt.subplots(subplot_kw={'projection': 'polar'})
        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self.fig.patch.set_facecolor('black')
        self.ax.set_facecolor('black')
        self.ax.set_theta_zero_location('N')  # 0 degrees at the top (North)
        self.ax.set_theta_direction(-1)  # Clockwise direction

        # Initialize data
        self.aircraft_list = [
            Aircraft(boeing_737, 170, boeing_737.cruise_speed, 'A1',
                     '1200', 10000, 'ASA1046',
                     {"lat": 42.923, "lon": -123.283}),  # Canyonville
            Aircraft(f16_type, 250, f16_type.cruise_speed, 'A2',
                     '1201', 15000, 'TBIRD16',
                     {"lat": 42.445, "lon": -122.321}),  # Mt. McLoughlin
            Aircraft(cessna_172, 350, cessna_172.cruise_speed, 'A3',
                     '1202', 5000, 'N914DK',
                     {"lat": 41.746, "lon": -122.631})  # Yreka
        ]

        # Show decaying radar return for aircraft
        self.aircraft_visuals = {a.id: {"ping_alpha": 0.0} for a in self.aircraft_list}

        self.radar_sweep_angle = 0
        self.sweep_lines = []

        # Create control frame
        self.control_frame = ttk.Frame(self)
        self.control_frame.pack(fill=tk.X, side=tk.BOTTOM)

        self.update_button = ttk.Button(self.control_frame, text="Update RADAR", command=self.update_radar)
        self.update_button.pack(side=tk.LEFT, padx=5, pady=5)

        self.quit_button = ttk.Button(self.control_frame, text="Quit", command=self.quit)
        self.quit_button.pack(side=tk.RIGHT, padx=5, pady=5)

        # Initial plot setup
        self.setup_plot()

        # Start radar sweep
        self.after(50, self.update_sweep)

    @staticmethod
    def latlong_to_bearing_rad(dx, dy):
        return np.radians((np.degrees(np.arctan2(dx, dy)) + 360) % 360)

    def setup_plot(self):
        """"""Setup the initial plot with tick positions and labels.""""""
        self.ax.set_theta_zero_location('N')
        self.ax.set_theta_direction(-1)
        self.ax.set_ylim(0, 100)
        self.ax.set_yticklabels([])

        tick_positions = np.arange(0, 360, 15)  # Every 15 degrees
        tick_labels = [f"{pos}" for pos in tick_positions]
        tick_positions = np.deg2rad(tick_positions)
        self.ax.xaxis.set_major_locator(FixedLocator(tick_positions))
        self.ax.set_xticklabels(tick_labels, color='lightblue')

        self.ax.spines['polar'].set_color('lightblue')
        self.ax.xaxis.set_tick_params(color='lightblue')
        self.ax.yaxis.set_tick_params(color='lightblue')
        self.ax.grid(False)

        for spine in self.ax.spines.values():
            spine.set_edgecolor('lightblue')

    def plot_aircraft(self):
        """"""Plot the aircraft on the radar display.""""""
        for aircraft in self.aircraft_list:
            vis = self.aircraft_visuals[aircraft.id]

            # Convert lat/lon to polar from radar origin
            dy = aircraft.ads_b["lat"] - self.radar_origin["lat"]
            dx = aircraft.ads_b["lon"] - self.radar_origin["lon"]
            angle = self.latlong_to_bearing_rad(dx, dy)
            distance_val = np.sqrt(dx ** 2 + dy ** 2) * 111  # Approx degrees -> km

            if distance_val > 100:
                continue

            # Plot radar return
            if vis["ping_alpha"] > 0:
                self.ax.plot([angle, angle], [distance_val - 0.1, distance_val + 0.1],
                             color='orange', alpha=vis["ping_alpha"], linewidth=2)

            # Display transponder and ADS-B data
            self.ax.text(angle, distance_val + 5,
                         f"{aircraft.id}"
                         f"\n{aircraft.mode_a}"
                         f"\n{aircraft.mode_c}"
                         f"\n{aircraft.mode_s}"
                         f"\n{aircraft.ads_b['lat']:.2f}, {aircraft.ads_b['lon']:.2f}",
                         color='lightblue', fontsize=8, ha='center', va='bottom')

    @staticmethod
    def polar_to_cartesian(angle, distance):
        """"""Convert polar coordinates to cartesian for overlay placement.""""""
        x = distance * np.cos(angle)
        y = distance * np.sin(angle)
        return x, y

    def update_sweep(self):
        """"""Update the radar sweep.""""""
        self.ax.clear()
        self.ax.set_facecolor('black')
        self.setup_plot()

        # Advance the radar sweep angle
        self.radar_sweep_angle = (self.radar_sweep_angle + np.pi / 60) % (2 * np.pi)

        # Update radar returns
        for aircraft in self.aircraft_list:
            dy = aircraft.ads_b["lat"] - self.radar_origin["lat"]
            dx = aircraft.ads_b["lon"] - self.radar_origin["lon"]
            angle = self.latlong_to_bearing_rad(dx, dy)
            diff = abs((angle - self.radar_sweep_angle + np.pi) % (2 * np.pi) - np.pi)

            vis = self.aircraft_visuals[aircraft.id]
            if diff < np.pi / 60:
                vis["ping_alpha"] = 1.0
            elif vis["ping_alpha"] > 0:
                vis["ping_alpha"] -= 0.005
                if vis["ping_alpha"] < 0:
                    vis["ping_alpha"] = 0

        # Plot aircraft and data
        self.update_radar()

        # Draw the sweep line
        self.ax.plot([self.radar_sweep_angle, self.radar_sweep_angle], [0, 100], color='orange', alpha=0.75)

        # Fade out previous sweep lines
        for line in self.sweep_lines:
            line[1] -= 0.25
            if line[1] <= 0:
                self.sweep_lines.remove(line)
            else:
                self.ax.plot([line[0], line[0]], [0, 100], color='orange', alpha=line[1])

        # Add the new sweep line
        self.sweep_lines.append([self.radar_sweep_angle, 0.75])
        self.canvas.draw()

        # Schedule the next sweep update
        self.after(50, self.update_sweep)

    def update_radar(self):
        """"""Update the RADAR display with new data.""""""
        # Update positions and data for each aircraft
        for aircraft in self.aircraft_list:
            aircraft.update_flight_profile()
            aircraft.update_position()

        self.plot_aircraft()
"""

if __name__ == "__main__":
    # app = RadarDisplay()
    # app.mainloop()
    app = QApplication(sys.argv)
    window = RadarWindow()
    window.show()
    sys.exit(app.exec_())