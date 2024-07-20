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
