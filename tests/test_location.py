import unittest

from Locations.Yuma.Scenarios.yuma import create_yuma_scenario
from simulator.core.atc import ATCFacility
from simulator.core.location import AirportDiagram, FlightPlate, Location


class LocationTests(unittest.TestCase):
    def test_yuma_scenario_uses_fresh_location_and_scenario_runways(self):
        _, facility, _ = create_yuma_scenario()
        other = ATCFacility.get_atc_facility_by_name("KNYL")
        self.assertIsNotNone(other)
        location = facility.location
        self.assertEqual((location.latitude, location.longitude), (32.6566, -114.6056))
        self.assertEqual(location["lat"], location.latitude)
        self.assertEqual(location["lon"], location.longitude)
        self.assertEqual(location.elevation_ft, 213.3)
        self.assertEqual(location.active_runways, ("03L", "03R", "35"))
        self.assertEqual(location.helicopter_pads, ("P1", "P2", "P3", "P5"))
        self.assertEqual(other.location.active_runways, ())
        self.assertIn(
            "approach_low", {f.identifier for f in location.internal_frequencies}
        )
        self.assertIn(
            "zla31_low", {f.identifier for f in location.neighbor_frequencies}
        )

    def test_location_can_hold_airport_diagram_and_procedures(self):
        diagram = AirportDiagram("TEST", "diagram data")
        approach = FlightPlate("approach", "TEST", "approach data")
        departure = FlightPlate("departure", "TEST", "departure data")
        location = Location(
            "Test",
            1.0,
            2.0,
            airport_diagram=diagram,
            approach_procedures=(approach,),
            departure_procedures=(departure,),
        )
        self.assertIs(location.airport_diagram, diagram)
        self.assertEqual(location.approach_procedures, (approach,))
        self.assertEqual(location.departure_procedures, (departure,))


if __name__ == "__main__":
    unittest.main()
