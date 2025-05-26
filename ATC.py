from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QSlider, QLabel, QHBoxLayout, QPushButton
from PyQt5.QtCore import Qt
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
        self._init_plot()

        self.primary_returns = []
        self.brightness = 1.0

    def _init_plot(self):
        self.ax.set_theta_zero_location('N')
        self.ax.set_theta_direction(-1)
        self.ax.set_ylim(0, 100)
        self.ax.set_facecolor('black')

        # Disable all default ticks and gridlines
        self.ax.grid(False)
        self.ax.set_xticks([])
        self.ax.set_yticks([])
        self.ax.set_xticklabels([])
        self.ax.set_yticklabels([])

    def set_brightness(self, value):
        self.brightness = value

    def update_frame(self, sweep_angle, aircraft_list):
        self.ax.clear()
        self._init_plot()

        base_orange = (1.0, 0.5, 0.0)  # Pure orange in RGB
        dim_orange = tuple(c * self.brightness for c in base_orange)

        # Draw radar range rings (every 10 km except outermost)
        for r in range(25, 100, 25):
            self.ax.plot(np.linspace(0, 2 * np.pi, 512), [r] * 512,
                         color=dim_orange,
                         linewidth=0.5)
        # Outermost ring full brightness
        self.ax.plot(np.linspace(0, 2 * np.pi, 512), [100] * 512,
                     color=base_orange, linewidth=2.0)

        # Draw radial lines (every 15 degrees)
        for t in np.deg2rad(np.arange(0, 360, 15)):
            self.ax.plot([t, t], [0, 100],
                         color=dim_orange,
                         linewidth=0.5)

        # Fade old primary returns
        FADE_RATE = 1.0 / 600.0  # fades over ~5 sweeps

        new_returns = []
        for blip in self.primary_returns:
            blip["alpha"] -= FADE_RATE
            if blip["alpha"] > 0:
                dist = blip["distance"]
                angle = blip["angle"]
                blip_len_km = max(0.1, 1.0 * (1 - dist / 100.0))
                if dist < 0.1:
                    continue
                else:
                    offset = blip_len_km / dist
                theta1 = angle - offset / 2
                theta2 = angle + offset / 2

                self.ax.plot([theta1, theta2], [dist, dist],
                             color='orange', alpha=blip["alpha"], linewidth=1.5)
                new_returns.append(blip)
        self.primary_returns = new_returns

        # Add new primary returns from current sweep
        for ac in aircraft_list:
            dx = ac.ads_b["lon"] - self.radar_origin[1]
            dy = ac.ads_b["lat"] - self.radar_origin[0]
            angle = np.arctan2(dy, dx)
            distance_km = np.hypot(dx, dy) * 111  # crude lat/lon deg to km

            if distance_km > 100:
                continue

            diff = abs((angle - sweep_angle + np.pi) % (2 * np.pi) - np.pi)
            if diff < np.deg2rad(2):  # about 1 deg tolerance
                self.primary_returns.append({
                    "angle": angle,
                    "distance": distance_km,
                    "alpha": 1.0
                })

            # Display secondary radar info (Mode S callsign)
            self.ax.plot(angle, distance_km, marker='o', markersize=4,
                         markerfacecolor='none', markeredgecolor='cyan')
            self.ax.text(angle, distance_km + 4,
                         f"{ac.mode_s}\n{ac.mode_a}\n{int(ac.mode_c / 100)} {int(ac.velocity)}",
                         color='lightblue', fontsize=7, ha='left')

        # Sweep arc with fading trail (e.g., 15 degrees wide, fading back)
        trail_width_deg = 15  # Total sweep width
        num_lines = 60  # Number of lines in the trail
        max_alpha = 0.75

        for i in range(num_lines):
            frac = i / num_lines
            angle = sweep_angle - np.deg2rad(trail_width_deg * frac)
            alpha = max_alpha * (1 - frac)
            self.ax.plot([angle, angle], [0, 100], color='orange', alpha=alpha, linewidth=1.0)

        self.draw()



class RadarWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ATC Radar Display (PyQt5)")
        self.setGeometry(100, 100, 1000, 800)

        # Radar origin (define this early so canvas can use it)
        self.radar_origin = (42.3736, -122.872)  # MFR

        # Create radar canvas (this must come before using self.canvas)
        self.canvas = RadarCanvas(self.radar_origin)

        # Left (radar display)
        radar_layout = QVBoxLayout()
        radar_layout.addWidget(self.canvas)

        # Right (control panel)
        control_panel = QVBoxLayout()
        self.brightness_slider = QSlider(Qt.Vertical)
        self.brightness_slider.setMinimum(0)
        self.brightness_slider.setMaximum(100)
        self.brightness_slider.setValue(100)
        self.brightness_slider.setTickInterval(10)
        self.brightness_slider.setTickPosition(QSlider.TicksRight)
        self.brightness_slider.valueChanged.connect(self.on_brightness_change)

        brightness_label = QLabel("Brightness")
        brightness_label.setAlignment(Qt.AlignHCenter)

        control_panel.addWidget(brightness_label)
        control_panel.addWidget(self.brightness_slider)

        # Combine both layouts
        main_layout = QHBoxLayout()
        main_layout.addLayout(radar_layout, stretch=4)
        main_layout.addLayout(control_panel, stretch=1)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

        # Initialize aircraft
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

        # Sweep and simulation timer
        self.sweep_angle = 0
        self.timer_id = self.startTimer(50)  # ~20 FPS

    def timerEvent(self, event):
        self.sweep_angle = (self.sweep_angle + np.pi / 60) % (2 * np.pi)

        for aircraft in self.aircraft_list:
            aircraft.update_flight_profile()
            aircraft.update_position()

        self.canvas.update_frame(self.sweep_angle, self.aircraft_list)


    def on_brightness_change(self, value: int):
        normalized = value / 100.0
        self.canvas.set_brightness(normalized)


if __name__ == "__main__":
    # app = RadarDisplay()
    # app.mainloop()
    app = QApplication(sys.argv)
    window = RadarWindow()
    window.show()
    sys.exit(app.exec_())
