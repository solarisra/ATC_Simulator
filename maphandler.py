import math

import arcade
import geopandas as gpd
import polars as pl

from navmath import NavigationalCoordinateSystem


class GeoDataProcessor:
    """
    Processes geospatial data from CSV or GeoJSON files based on a facility parameter and distance parameter.
    """

    NM_TO_DEG = (
        1 / 60
    )  # 1 nautical mile is approximately equal to 1/60 degree of latitude

    def __init__(self, file_path, facility_location, max_distance_nm=100):
        self.file_path = file_path
        self.facility_lat, self.facility_lon = facility_location
        self.max_distance_nm = max_distance_nm
        self.lat_bounds, self.lon_bounds = self.calculate_bounds()

    def calculate_bounds(self):
        """
        Calculate the latitude and longitude boundaries based on the facility and distance parameters.
        """
        lat_offset = self.max_distance_nm * self.NM_TO_DEG
        lon_offset = (
            self.max_distance_nm
            * self.NM_TO_DEG
            / math.cos(math.radians(self.facility_lat))
        )

        lat_min = self.facility_lat - lat_offset
        lat_max = self.facility_lat + lat_offset
        lon_min = self.facility_lon - lon_offset
        lon_max = self.facility_lon + lon_offset

        return (lat_min, lat_max), (lon_min, lon_max)

    def read_data(self):
        """
        Reads geospatial information from a CSV or GeoJSON file and returns it as a filtered polars DataFrame.
        """
        if self.file_path.endswith(".csv"):
            with open(self.file_path, encoding="utf-8-sig") as data_file:
                header = data_file.readline()
            separator = ";" if header.count(";") > header.count(",") else ","
            df = pl.read_csv(self.file_path, separator=separator)
            columns = {column.casefold(): column for column in df.columns}

            if "x" in columns and "y" in columns:
                longitude_column, latitude_column = columns["x"], columns["y"]
            elif "latitude" in columns and "longitude" in columns:
                latitude_column, longitude_column = (
                    columns["latitude"],
                    columns["longitude"],
                )
            elif "intptlat" in columns and "intptlon" in columns:
                latitude_column, longitude_column = (
                    columns["intptlat"],
                    columns["intptlon"],
                )
            else:
                raise ValueError(
                    f"CSV file {self.file_path!r} must contain X/Y, latitude/longitude, "
                    "or intptlat/intptlon coordinate columns."
                )

            df = df.with_columns(
                pl.col(latitude_column)
                .cast(pl.Float64, strict=False)
                .alias("latitude"),
                pl.col(longitude_column)
                .cast(pl.Float64, strict=False)
                .alias("longitude"),
            )
            has_coordinates = df.select(
                pl.col("latitude").is_not_null().any()
                & pl.col("longitude").is_not_null().any()
            ).item()
            if not has_coordinates:
                raise ValueError(
                    f"CSV file {self.file_path!r} has no numeric coordinates."
                )

            df = df.filter(
                pl.col("latitude").is_not_null()
                & pl.col("longitude").is_not_null()
                & pl.col("latitude").is_between(*self.lat_bounds)
                & pl.col("longitude").is_between(*self.lon_bounds)
            )
            distances = NavigationalCoordinateSystem.calculate_distance(
                self.facility_lat,
                self.facility_lon,
                df["latitude"].to_numpy(),
                df["longitude"].to_numpy(),
            )
            df = df.with_columns(pl.Series("distance", distances))
            df = df.filter(pl.col("distance") <= self.max_distance_nm)

        elif self.file_path.endswith(".geojson"):
            gdf = gpd.read_file(self.file_path)
            gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty]
            gdf = gdf.cx[
                self.lon_bounds[0] : self.lon_bounds[1],
                self.lat_bounds[0] : self.lat_bounds[1],
            ]
            representative_points = gdf.geometry.representative_point()
            gdf["latitude"] = representative_points.y
            gdf["longitude"] = representative_points.x
            gdf["distance"] = NavigationalCoordinateSystem.calculate_distance(
                self.facility_lat,
                self.facility_lon,
                gdf["latitude"].to_numpy(),
                gdf["longitude"].to_numpy(),
            )
            gdf = gdf[gdf["distance"] <= self.max_distance_nm]
            df = pl.from_pandas(gdf.drop(columns=gdf.geometry.name))

        else:
            raise ValueError(
                "Unsupported file format. Only .csv and .geojson files are supported."
            )

        return df


class MapOverlayGenerator:
    """
    Generates a map overlay from a polars DataFrame to be fed to the radar display.
    """

    def __init__(self, geodata_df, map_type="default"):
        self.geodata_df = geodata_df
        self.map_type = map_type

    def get_color(self):
        """
        Determine the color based on the map type.
        """
        color_mapping = {
            "default": arcade.color.DIM_GRAY,
            "boundary": arcade.color.YELLOW,
            "owned": arcade.color.WHITE,
            "unowned": arcade.color.GREEN,
            "search_fusion": arcade.color.BLUE,
            "beacon": arcade.color.GREEN,
            "history": arcade.color.BLUE,
            "predicted_track": arcade.color.WHITE,
            "minimum_separation": arcade.color.WHITE,
        }
        return color_mapping.get(self.map_type, arcade.color.DIM_GRAY)

    def draw_overlay(self, radar_display):
        """
        Draws the overlay on the given radar display.
        This implementation follows the specified color guidelines.
        """
        color = self.get_color()
        for row in self.geodata_df.iter_rows(named=True):
            lat = row["latitude"]
            lon = row["longitude"]

            # Convert lat/lon to radar display coordinates
            x, y = radar_display.convert_to_display_coordinates(lat, lon)
            # Draw the overlay element (e.g., point, line) on the radar display
            # Using specified colors for radar display
            radar_display.draw_point(x, y, color=color)
