# ATC Simulator

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and
Python 3.12 or newer, then run:

```shell
uv sync
uv run python main.py
```

The project dependencies, including those used by the GIS data processor,
are recorded in `pyproject.toml` and `uv.lock`. Run the tests with
`uv run python -m unittest discover -s tests`.
Check lint and formatting with `uv run ruff check .` and
`uv run ruff format --check .`. Run `uv run ruff format .` to format files.

The ARTS sweep has a bright leading edge and an 18-degree fading sector.

The radar map has individually switchable GIS overlays. Press F1 through F12
to toggle the layers shown in the legend. Airports, navaids, state borders,
airspace, special-use airspace and ATS routes start enabled; other layers load
in the background when enabled. The legend
shows loading or errors. Airport, waypoint, navaid and holding-fix positions
come from `GIS_CSV`; state outlines come from the geometry in its state CSV.
Airspace, routes, radial bearings and pending runways use the corresponding
geometry files in `GIS_JSON`. Holding-pattern marks show their fixes, not
the shape of the holding circuit. CSV records without coordinates and the
nonspatial frequency table cannot be drawn.

`GIS_JSON/Class_Airspace.geojson` and `GIS_JSON/Route_Airspace.geojson` are
not distributed in the repository because of their size. Supply those files
locally to use their overlays; otherwise the legend reports a loading error.

Click an aircraft or its data block to select it. Use the numeric keypad
directions to position the selected aircraft's data block. The STARS-style
block shows the callsign, altitude in hundreds of feet with speed in tens of
knots, aircraft type, and scratchpad on four lines in both display modes. The selected
aircraft's heading, squawk, exact speed and range appear at the right. This
is a simplified full data block; flight-plan fields are not simulated.

The first line also shows simulated track ownership: `Y` for Yuma, `L` for
Los Angeles Center, and `A` for Albuquerque Center. These are illustrative
simulator identifiers, not verified operational position symbols. An offer
appears as `Y>L`, `Y>A`, `L>Y`, or `A>Y`. All startup tracks belong to Yuma.
For a selected Yuma-owned aircraft, press H and then L or A to offer a handoff;
the simulated center accepts after three seconds. Press X to cancel a pending
offer. To simulate an incoming offer for a center-owned aircraft, select it
and press I, then A to accept or X to reject. Escape cancels the destination
prompt. Handoffs are manual, with no geographic boundary checks or Mexican
handoffs. The track ownership model does not simulate radio communications or
the full operational transfer of control.

The data blocks remain white rather than using unverified ownership colors.
FAA Order 7110.65BB [5-14-4 and 5-14-5](documentation/ATC_7110.65BB/chapter_5/chap5_section_14.html)
calls for local procedures and directives; it does not specify a universal
ownership color scheme in those sections. Handoff procedures are described in
[5-4](documentation/ATC_7110.65BB/chapter_5/chap5_section_4.html).

Squawk 7700 flashes `EM` on the first line. To edit a selected aircraft's
scratchpad, press S, type up to 16 letters, digits, hyphens or slashes, and
press Enter to save or Escape to cancel. Backspace removes a character;
clicking elsewhere cancels editing. Clearing the text and saving removes it.

An altitude prefixed with `+` or `-` rose or fell since the previous
one-second secondary radar update. Level or newly detected aircraft have no
prefix.

Use the mouse wheel to zoom in 10% increments, the arrow keys to pan by
about 20 pixels, and Home to reset the view. The view stays within the
100-nautical-mile coverage area, so panning is available after zooming in.

Aircraft speeds are in knots and altitudes are in hundreds of feet. Aircraft
keep their supplied altitude and squawk; flight rules do not assign either.
The aircraft maneuver methods set targets that are approached over subsequent
updates using the model's rates and elapsed simulation time. Speeds are
limited to the model's maximum in this simplified, no-wind simulation.
`AircraftList.update_positions()` requires an assigned ATC facility to calculate
range. Aircraft model fuel-consumption values are in gallons per hour.
The model specifications are simplified examples, not operational data.

Startup traffic is a fictional mix of civilian, local military and exercise
visiting aircraft, not a live traffic feed. Less typical and historical samples
are commented out in `main.py` and can be re-enabled individually. Some military
callsigns use published Yuma-associated callwords with illustrative flight
numbers:

- SNIPER: VMFT-401 F-5 adversaries; the F-5E model is a simplified stand-in.
- STORM: Yuma-based VMX-1, which has operated MV-22s.
- SHEEP: VMA-214's historical Yuma Harriers (commented out by default).
- CAT: VMFA-311's F-35Cs, represented here as visiting aircraft; the squadron
  previously flew Harriers at Yuma and is now based at Miramar.

These callwords can change and are not guarantees of current assignments.
Sources: [military callsign list](https://henney.com/chm/callsign.htm) and
[VMX-1](https://en.wikipedia.org/wiki/VMX-1).

Additional aircraft models are defined in `aircraft_models.py`, with
links to reference data. Unspecified performance and maneuver rates are
estimates; the simulator does not model rotorcraft-specific flight dynamics.
For helicopters, the model's `wing_span` is rotor diameter and `stall_speed`
is not applicable. For the V-22, `wing_span` is its width with rotors turning
and no single stall speed is modeled. A zero takeoff distance represents
vertical takeoff under suitable conditions, not a guarantee at every weight
or altitude. The F-35 model is the carrier-capable F-35C used by the Navy and
Marine Corps. Tiltrotor conversion and Harrier vertical flight are not modeled.
