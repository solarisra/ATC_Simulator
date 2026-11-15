import arcade

from aircraft import Aircraft, AircraftList
from aircraft_models import (
    # Keep these imports for the commented-out sample aircraft below.
    airbus_a320,  # noqa: F401
    airbus_h135,
    av8b_harrier,  # noqa: F401
    bell_ah1w,  # noqa: F401
    bell_hh1n,  # noqa: F401
    boeing_737,  # noqa: F401
    boeing_767_freighter,  # noqa: F401
    boeing_b52,  # noqa: F401
    boeing_ch46e,  # noqa: F401
    cessna_172,
    cessna_208,
    cessna_citation_m2,
    f5_tiger_ii,
    f16,
    f18e,
    f35c,
    lockheed_c130j,
    piper_pa28,
    sikorsky_ch53d,  # noqa: F401
    sikorsky_uh60,
    v22_osprey,
)
from atc import ATCFacility
from radar import RadarDisplay

if __name__ == "__main__":
    # Default ATC Facility: MCAS Yuma (KNYL)
    knyl_atc = ATCFacility.get_atc_facility_by_name("KNYL")

    # Sample Aircraft List
    list_of_aircraft = AircraftList()
    list_of_aircraft.add_aircraft(
        [
            Aircraft(
                "A1",
                "1200",
                "ID1001",
                "N135TC",
                cessna_172,
                210,
                50,
                120,
                50,
                32.711,
                -113.966,
                flight_rules="VFR",
            ),
            # Aircraft('A2', '2000', 'ID1002', 'AMF2118', boeing_737,
            #          180, 150, 450, 75, 33.241, -114.703, flight_rules="IFR"),
            Aircraft(
                "A3",
                "2000",
                "ID1003",
                "DEVIL279",
                f18e,
                90,
                40,
                600,
                30,
                32.807,
                -115.264,
                flight_rules="IFR",
            ),
            # Aircraft('A4', '4301', 'ID1004', 'AAL381', airbus_a320,
            #          210, 180, 350, 0, 33.25, -114.12, flight_rules="IFR"),
            # Aircraft('A5', '4302', 'ID1005', 'FDX246', boeing_767_freighter,
            #          90, 150, 330, 0, 32.10, -114.20, flight_rules="IFR"),
            Aircraft(
                "A6",
                "1200",
                "ID1006",
                "N507EX",
                cessna_208,
                80,
                75,
                160,
                0,
                32.91,
                -114.35,
                flight_rules="VFR",
            ),
            Aircraft(
                "A7",
                "1200",
                "ID1007",
                "N712PA",
                piper_pa28,
                50,
                55,
                110,
                0,
                32.34,
                -114.97,
                flight_rules="VFR",
            ),
            Aircraft(
                "A8",
                "4303",
                "ID1008",
                "N380CJ",
                cessna_citation_m2,
                250,
                120,
                300,
                0,
                33.02,
                -115.12,
                flight_rules="IFR",
            ),
            Aircraft(
                "A9",
                "1200",
                "ID1009",
                "LIFE12",
                airbus_h135,
                180,
                25,
                110,
                0,
                32.77,
                -114.68,
                flight_rules="VFR",
            ),
            Aircraft(
                "A10",
                "4304",
                "ID1010",
                "VIPER21",
                f16,
                300,
                160,
                400,
                0,
                32.16,
                -115.12,
                flight_rules="IFR",
            ),
            Aircraft(
                "A11",
                "4305",
                "ID1011",
                "REACH47",
                lockheed_c130j,
                240,
                100,
                250,
                0,
                33.48,
                -114.90,
                flight_rules="IFR",
            ),
            Aircraft(
                "A12",
                "1200",
                "ID1012",
                "MERLIN28",
                sikorsky_uh60,
                30,
                15,
                120,
                0,
                32.42,
                -114.35,
                flight_rules="VFR",
            ),
            # Aircraft('A13', '4306', 'ID1013', 'DOOM31', boeing_b52,
            #          120, 190, 400, 0, 33.20, -115.40, flight_rules="IFR"),
            Aircraft(
                "A14",
                "4307",
                "ID1014",
                "SNIPER1",
                f5_tiger_ii,
                140,
                110,
                350,
                0,
                33.65,
                -115.65,
                flight_rules="IFR",
            ),
            Aircraft(
                "A15",
                "4310",
                "ID1015",
                "STORM1",
                v22_osprey,
                20,
                45,
                220,
                0,
                31.95,
                -114.80,
                flight_rules="IFR",
            ),
            Aircraft(
                "A16",
                "4311",
                "ID1016",
                "CAT31",
                f35c,
                230,
                160,
                400,
                0,
                33.45,
                -113.85,
                flight_rules="IFR",
            ),
            # Aircraft('A17', '1200', 'ID1017', 'STALL11', sikorsky_ch53d,
            #          60, 35, 120, 0, 32.25, -115.15, flight_rules="VFR"),
            # Aircraft('A18', '1200', 'ID1018', 'KNIGHT1', boeing_ch46e,
            #          90, 25, 110, 0, 32.90, -115.55, flight_rules="VFR"),
            # Aircraft('A19', '4312', 'ID1019', 'SHEEP19', av8b_harrier,
            #          330, 120, 350, 0, 31.80, -114.95, flight_rules="IFR"),
            # Aircraft('A20', '1200', 'ID1020', 'STORM2', bell_ah1w,
            #          180, 30, 140, 0, 33.50, -114.00, flight_rules="VFR"),
            # Aircraft('A21', '1200', 'ID1021', 'RESCUE1', bell_hh1n,
            #          270, 20, 100, 0, 32.35, -113.70, flight_rules="VFR"),
        ]
    )

    # Assign Aircraft to Default ATC Facility
    list_of_aircraft.assign_to_atc_facility(knyl_atc)

    # Start the radar display simulation with the chosen ATC facility
    app = RadarDisplay(list_of_aircraft, knyl_atc)
    app.setup()
    arcade.run()
