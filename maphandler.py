import polars as pl
import math
from navmath import NavigationalCoordinateSystem


class RadarMapOverlay:
    """
    Generates radar map overlays by reading geospatial information from CSV files.
    """
    NM_TO_DEG = 1 / 60  # 1 nautical mile is approximately equal to 1/60 degree of latitude

    def __init__(self, csv_file_path, radar_origin_lat, radar_origin_lon, max_distance_nm=100):
        self.csv_file_path = csv_file_path
        self.radar_origin_lat = radar_origin_lat
        self.radar_origin_lon = radar_origin_lon
        self.max_distance_nm = max_distance_nm
        self.lat_bounds, self.lon_bounds = self.calculate_bounds()
        self.overlay_data = self.read_csv()

    def calculate_bounds(self):
        """
        Calculate the latitude and longitude boundaries 100 NM away from the origin.
        """
        lat_offset = self.max_distance_nm * self.NM_TO_DEG
        lon_offset = self.max_distance_nm * self.NM_TO_DEG / math.cos(math.radians(self.radar_origin_lat))

        lat_min = self.radar_origin_lat - lat_offset
        lat_max = self.radar_origin_lat + lat_offset
        lon_min = self.radar_origin_lon - lon_offset
        lon_max = self.radar_origin_lon + lon_offset

        return (lat_min, lat_max), (lon_min, lon_max)

    def read_csv(self):
        """
        Reads geospatial information from a CSV file and stores it in a DataFrame.
        Filters data points within the specified boundaries.
        """
        df = pl.read_csv(self.csv_file_path)
        df = df.filter(
            (df['latitude'] >= self.lat_bounds[0]) & (df['latitude'] <= self.lat_bounds[1]) &
            (df['longitude'] >= self.lon_bounds[0]) & (df['longitude'] <= self.lon_bounds[1])
        )

        df = df.with_columns(
            (NavigationalCoordinateSystem.calculate_distance(
                self.radar_origin_lat, self.radar_origin_lon, pl.col('latitude'), pl.col('longitude'))
            ).alias('distance')
        )

        df = df.filter(df['distance'] <= self.max_distance_nm)
        data = df.select(['latitude', 'longitude', df.columns[2:]]).to_numpy()

        return data

    def get_overlay_data(self):
        """
        Returns the geospatial overlay data.
        """
        return self.overlay_data

    def draw_overlay(self, radar_display):
        """
        Draws the overlay on the given radar display.
        This implementation follows the specified color guidelines.
        """
        for lat, lon, additional_info in self.overlay_data:
            # Convert lat/lon to radar display coordinates
            x, y = radar_display.convert_to_display_coordinates(lat, lon)
            # Draw the overlay element (e.g., point, line) on the radar display
            # Using specified colors for radar display
            radar_display.draw_point(x, y, color=arcade.color.DIM_GRAY)
