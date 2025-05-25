from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.projections.polar import PolarAxes
from typing import cast
import matplotlib.pyplot as plt
from geopy.distance import distance
from geopy.point import Point
import numpy as np
import sys

from AircraftType import boeing_737, cessna_172, f16_type
from Aircraft import Aircraft


class RadarCanvas(FigureCanvas):
    def __init__(self, radar_origin):
        self.radar_origin = radar_origin
        fig, ax = plt.subplots(subplot_kw={'projection': 'polar'})
        ax = cast(PolarAxes, ax)  # Tell the type checker this is a PolarAxes
        self.fig = fig
        self.ax = ax
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

    def update_frame(self, sweep_angle_rad, aircraft_list):
        self.ax.clear()
        self._setup_plot()

        # Radar sweep
        self.ax.plot([sweep_angle_rad, sweep_angle_rad], [0, 100], color='orange', alpha=0.75)

        for aircraft in aircraft_list:
            dy = aircraft.ads_b["lat"] - self.radar_origin[0]
            dx = aircraft.ads_b["lon"] - self.radar_origin[1]
            angle = np.radians((np.degrees(np.arctan2(dx, dy)) + 360) % 360)
            distance_val = np.sqrt(dx ** 2 + dy ** 2) * 111  # rough km

            if distance_val > 100:
                continue

            self.ax.plot(angle, distance_val, marker='o', color='cyan')
            self.ax.text(angle, distance_val + 4,
                         f"{aircraft.id}\n{aircraft.mode_a}\nFL{int(aircraft.mode_c / 100)}",
                         color='lightblue', fontsize=7, ha='center')

        self.draw()

    def _setup_plot(self):
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

        # Radar origin
        self.radar_origin = (42.3736, -122.872)  # MFR

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

        # Create radar canvas
        self.canvas = RadarCanvas(self.radar_origin)
        layout = QVBoxLayout()
        layout.addWidget(self.canvas)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        # Sweep and simulation timer
        self.sweep_angle = 0
        self.timer_id = self.startTimer(50)  # ~20 FPS

    def timerEvent(self, event):
        self.sweep_angle = (self.sweep_angle + np.pi / 60) % (2 * np.pi)

        # Update simulation
        for aircraft in self.aircraft_list:
            aircraft.update_flight_profile()
            aircraft.update_position()

        # Render the updated frame
        self.canvas.update_frame(self.sweep_angle, self.aircraft_list)


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
