import numpy as np


class NavigationalCoordinateSystem:
    @staticmethod
    def to_radians(navigation_degrees):
        """
        Convert navigational degrees (0° at North, clockwise) to radians (0 rad at East, counterclockwise).

        :param navigation_degrees: Angle in degrees using navigational coordinates.
        :type navigation_degrees: float
        :return: Angle in radians using mathematical coordinates.
        :rtype: float
        """
        return np.radians((90 - navigation_degrees) % 360)

    @staticmethod
    def to_navigation_degrees(math_radians):
        """
        Convert radians (0 rad at East, counterclockwise) to navigational degrees (0° at North, clockwise).

        :param math_radians: Angle in radians using mathematical coordinates.
        :type math_radians: float
        :return: Angle in degrees using navigational coordinates.
        :rtype: float
        """
        return (90 - np.degrees(math_radians)) % 360

    @staticmethod
    def get_opposite_heading(navigation_degrees):
        """
        Get the opposite heading (180 degrees opposite) in navigational coordinates.

        :param navigation_degrees: Current heading in degrees using navigational coordinates.
        :type navigation_degrees: float
        :return: Opposite heading in degrees using navigational coordinates.
        :rtype: float
        """
        return (navigation_degrees + 180) % 360

    @staticmethod
    def calculate_distance(lat1, lon1, lat2, lon2):
        """
        Calculate the distance between two points given their latitudes and longitudes.

        :param lat1: Latitude of the first point.
        :type lat1: float
        :param lon1: Longitude of the first point.
        :type lon1: float
        :param lat2: Latitude of the second point.
        :type lat2: float
        :param lon2: Longitude of the second point.
        :type lon2: float
        :return: Distance in nautical miles.
        :rtype: float
        """
        # Haversine formula to calculate the great-circle distance
        R = 3440.065  # Radius of the Earth in nautical miles
        dlat = np.radians(lat2 - lat1)
        dlon = np.radians(lon2 - lon1)
        a = (
            np.sin(dlat / 2) ** 2
            + np.cos(np.radians(lat1))
            * np.cos(np.radians(lat2))
            * np.sin(dlon / 2) ** 2
        )
        c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
        distance = R * c
        return distance

    @staticmethod
    def calculate_new_position(lat, lon, speed, heading, delta_time):
        """
        Calculate the new latitude and longitude after moving at speed for delta_time seconds.

        :param lat: Starting latitude.
        :type lat: float
        :param lon: Starting longitude.
        :type lon: float
        :param speed: Speed in nautical miles per hour.
        :type speed: float
        :param heading: Heading in degrees.
        :type heading: float
        :param delta_time: Elapsed time in seconds.
        :type delta_time: float
        :return: New latitude and longitude.
        :rtype: tuple(float, float)
        """
        R = 3440.065  # Radius of the Earth in nautical miles
        distance = speed * delta_time / 3600  # Distance traveled in nautical miles
        heading_radians = np.radians(heading)
        lat1 = np.radians(lat)
        lon1 = np.radians(lon)

        lat2 = np.arcsin(
            np.sin(lat1) * np.cos(distance / R)
            + np.cos(lat1) * np.sin(distance / R) * np.cos(heading_radians)
        )
        lon2 = lon1 + np.arctan2(
            np.sin(heading_radians) * np.sin(distance / R) * np.cos(lat1),
            np.cos(distance / R) - np.sin(lat1) * np.sin(lat2),
        )

        return np.degrees(lat2), np.degrees(lon2)
