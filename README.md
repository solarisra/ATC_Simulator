# ATC Simulator

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and
Python 3.12 or 3.13 (Python 3.14 is not currently supported), then run:

```shell
uv sync
uv run python main.py
```

The application starts without a selected location or scenario.
Use **Location** to select an available facility; facilities with multiple
sectors show a sector submenu. The **Scenario** menu offers generation and
saved scenarios for Yuma; selecting **Cascade Approach** automatically selects
its currently configured Medford sector, a map-only location with no traffic
scenario. Selecting
another location while a scenario is running asks for confirmation before
ending it. For Yuma traffic, select **Location > Yuma**, wait for the default
map layers to load, then choose **Scenario > Generate Yuma...** or
**Scenario > Load saved scenario...**. A map loading error
is shown on screen; use **Scenario > Retry failed maps** after correcting the
cause. Replacing a running scenario asks for confirmation.
After a scenario loads, it starts paused with a controller handoff briefing.
Use Left and Right to review its pages and Enter to acknowledge it and start
the simulation. Weather is not yet simulated; the briefing assumes an
altimeter setting of 29.92 inHg.

Press Tab during a scenario to pause or resume, even with a menu or edit open.
While paused, simulation time and gameplay controls are stopped; pending voice
transmissions and any active strip drag are discarded. Escape continues to
close menus or cancel edits and prompts.

For generated traffic, choose **Scenario > Generate Yuma...**. Set the seed,
traffic volume, and relative weights for operations and aircraft types; zero
disables a category. Click the controls or use Up/Down to select a row and
Left/Right to adjust it. Select the seed row to enter digits, or press R for
a new seed. Enter generates the scenario; Escape cancels. The existing
scenario is preserved until replacement is confirmed. The generator selects
aircraft and suitable airports, checks approximate aircraft range, and builds
routes through the Yuma area using connected Victor airways and fixes from
the local navigation data. Generated small fixed-wing aircraft use fictional
U.S.-format N-numbers; they are not checked against the aircraft registry.
Direct airport connections are used; when an
airway route cannot be built, a safe direct fallback is identified in the
briefing and strip remarks. The briefing also reports unavailable combinations
and airports. Routes are fictional approximations, not operational flight
plans: airway altitudes, terrain, procedures, airspace restrictions and actual
airport suitability are not checked. Range missions are not yet implemented.

The menu bar shows UTC. Before a scenario starts it shows the current UTC;
on loading, the simulation clock is initialized from current UTC and pauses
with the briefing and generator dialog. Yuma uses UTC-7 for its simplified
day/night pattern: 06:00–22:00 local is daytime. Overnight, the departure
weight is halved relative to other operations. During daytime heavy traffic,
generated takeoff starts are scheduled 3–5 minutes apart; otherwise the first
departure is scheduled within 3–5 minutes and later departures are randomized
over the next 30 minutes. Scheduled UTC times appear in the briefing and
departure strips. The same seed, settings, and starting local-time period
reproduce the traffic and departure offsets; absolute departure times depend
on the starting UTC. This is a simplified simulation, not an assessment of
FAA separation requirements.

For light traffic, generated inbound aircraft enter one at a time: the first is
present at the start, and subsequent arrivals are scheduled five simulation
minutes apart. An arrival waits if its entry point is within five nautical miles
of an airborne aircraft, delaying later arrivals by the same amount. Pending
arrivals appear in the briefing but not on radar or the strip board, and their
remaining schedule is saved with the scenario. Other traffic levels and
departure schedules are unchanged.

Use **Scenario > Save scenario...** to name and save the current Yuma
scenario, or **Scenario > Load saved scenario...** to select a saved one.
Saves are stored as JSON in the user's `.atc_simulator/scenarios` directory.
Overwriting a name requires confirmation. Loading replaces the current
scenario only after confirmation and opens a paused handoff briefing; the
simulation clock, aircraft, flight plans, clearances, departure progress,
strip annotations and order, tracking, radar contact, coordination, radios and generator
settings are restored. Finish any in-progress edit before saving. Radar
trails, the selected aircraft and active audio transmissions are not saved.

The menu bar centers the selected location. Voice status appears in the
radar display's lower-right corner. Map and other application messages appear
just below the radar's top edge.
**Options > Display** selects the radar scope: ARTS IIE is available, while
FDAD and ACD are not yet implemented.
The window can be resized or maximized; the interface scales proportionally.
**Pubs** browses the selected location or sector's `pubs` folder. Choose a
folder to enter it, use **Back** to return, and select a PDF to open it in
the system's default viewer. Reopen the menu to refresh its contents.
FAA Order JO 7110.65BB (including changes 1–3, effective July 9, 2026) is
available in Pubs even without a location selected; its local PDF must be
updated when the FAA publishes a newer edition.

Medford uses KMFR runway 32 as the simulator's initial active runway. The map
shows nearby airports from the GIS dataset; it does not define which airports
are controlled by the Medford sector or depict verified sector boundaries.
Medford's published airport and frequency data and procedure names are based
on the [FAA-derived airport listing](https://www.airnav.com/airport/KMFR),
effective 29 October 2026. Seattle Center's King Mountain frequencies are
published for use when Cascade Approach is closed; operating hours are not
simulated. The stored diagram link is for the chart cycle ending 26 November
2026, and procedure names and diagrams are not yet displayed or simulated.
No Medford interfacility coordination lines have been configured.

`simulator/core/location.py` defines location coordinates, elevation in feet MSL, active
runways and pads, airport diagram, procedures, and emergency, internal and
neighbor radio frequencies. Yuma's location data is in `locations/Yuma/`;
its scenario is in `locations/Yuma/Scenarios/`. The Yuma scenario sets the
active runways and pads when loaded. Diagram and procedure data are not yet
provided, and weather is not generated or retrieved.
Medford's sector data is in `locations/Cascade/Sectors/Medford/`; its
publications can be placed in that folder's `pubs` subfolder.
Locations also specify magnetic declination, positive east. The simulator uses
the configured fixed variation throughout each coverage area: Yuma 10°14′E
and Medford 13°15′E. These values do not update automatically or vary with
aircraft position.
Controller-facing headings, position bearings and radar azimuth markings are
magnetic. The radar and its map overlays are magnetic-north-up; geographic
movement and navigation continue to use true bearings internally.

`main.py` remains the launcher. Shared application code is organized under
`simulator/` by application, core models, display, navigation and radio.
`sample_scenario.py` retains compatibility imports for the Yuma scenario.

The Arcade-drawn menu follows the system light/dark app preference on Windows
and macOS, and the GNOME color-scheme or GTK theme on Linux. It checks for
changes periodically. Other Linux desktops and accessibility themes may not
be reflected. If detection fails, the menu retains its last appearance (dark
at startup) and logs a warning; the simulator remains usable. This is a
custom-styled menu, not a native operating-system menu.

The project dependencies, including those used by the GIS data processor,
are recorded in `pyproject.toml` and `uv.lock`. Run the tests with
`uv run python -m unittest discover -s tests`.
Check lint and formatting with `uv run ruff check .` and
`uv run ruff format --check .`. Run `uv run ruff format .` to format files.

The ARTS sweep has a bright leading edge and an 18-degree fading sector.
Range rings are centered on the radar origin at 10-nautical-mile intervals.
Use **Options > Range rings** to select their brightness from 10% to 100%,
or turn them off. The default is 30%.

The radar map has individually switchable GIS overlays. Press F1 through F12
to toggle the layers shown in the legend; Shift+F9, Shift+F10 and Shift+F11
toggle T routes, Q routes and J routes, respectively. Airports, navaids, state borders,
airspace, special-use airspace and V routes (Victor airways) start enabled;
other layers load in the background when enabled. The legend
shows loading or errors. Airport, waypoint, navaid and holding-fix positions
come from `GIS_CSV`; state outlines come from the geometry in its state CSV.
Airspace, routes, radial bearings and pending runways use the corresponding
geometry files in `GIS_JSON`. V, T, Q and J routes have separate overlays;
only V routes start enabled. Other ATS route designations are not shown.
Holding-pattern marks show their fixes, not
the shape of the holding circuit. CSV records without coordinates and the
nonspatial frequency table cannot be drawn.

`GIS_JSON/Class_Airspace.geojson` and `GIS_JSON/Route_Airspace.geojson` are
not distributed in the repository because of their size. Supply those files
locally to use their overlays; otherwise the legend reports a loading error.

Click an aircraft or its data block to select it. Use the numeric keypad
directions to position the selected aircraft's data block. Near the circular
scope edge, blocks are repositioned to keep them inside the perimeter. The STARS-style
block shows the callsign, altitude in hundreds of feet with speed in tens of
knots, aircraft type and current squawk, and scratchpad on four lines in both
display modes. A squawk change appears on the next secondary radar update; it
does not automatically establish radar contact. The selected aircraft's heading,
squawk, exact speed and range appear at the right of the radar. This is a
simplified full data block.

The communications panel is above the radar, with radio, intrafacility and
interfacility controls grouped side by side. Click a frequency button to cycle
it through On, Listen and Off. Multiple frequencies can be monitored at
once. Hold the `HOLD TO TALK` button or the spacebar to make the simulated
mic hot: all On frequencies transmit, while Listen frequencies do not.
Buttons brighten while their frequency carries a controller transmission or
an audible aircraft readback.
Releasing a control stops its transmission; the mic remains hot while either
control is held. Leaving the window releases the mouse control, and losing
window focus releases both. Spacebar enters text instead of transmitting
when supported during text entry; push-to-talk is disabled while editing a
strip, scratchpad, clearance or coordination.
Emergency frequencies initially listen. Loading the Yuma scenario sets both
VHF and UHF for APP, DEP and ENR to On; tower and center frequencies start
Off. Buttons use TWR, APP, DEP, ENR and SEC for tower, approach, departure,
enroute and sector.

The separate intrafacility section has lines for KNYL Tower (Local), Range
Control, Approach/Departure and Enroute. Click a line to toggle it between
Cold and Hot; all start Cold and can be Hot independently. A Hot line stays
Hot without push-to-talk, regardless of the radio mic state.
The interfacility section provides separate Hot/Cold lines for ZLA sectors 9,
10 and 31 and ZAB sector 42. These are independent of the sector radio channels
and, like the intrafacility lines, do not yet carry audio.

The panel displays separate Yuma approach/departure and VHF/UHF tower buttons.
Its emergency, tower, approach and departure values are from the
[FAA-derived Yuma listing](https://www.airnav.com/airport/KNYL), effective
29 October 2026. KNYL enroute, ZLA sectors 9, 10 and 31 and ZAB sector 42
use frequencies supplied for this scenario; the enroute values are provisional.
Sector 31 represents airspace above FL230, but does not automate sector
assignment or handoffs. These values may change and are not for operational use.

[RadioReference's Yuma airport listing](https://www.radioreference.com/db/aid/10632)
lists departure VHF as 125.550 MHz, while the FAA-derived listing above gives
125.500 MHz, which the simulator retains. RadioReference also lists an
additional 336.400 MHz approach UHF frequency.

### Voice radio

Voice is optional and requires default microphone and speaker devices.
An NVIDIA GPU is **not required**: speech recognition and synthesis automatically
use CUDA when `torch.cuda.is_available()` is true and otherwise use the CPU.

- **CPU:** Supported without an NVIDIA GPU, but voice processing is slower.
  The application displays a CPU-performance warning during initialization.
- **GPU:** NVIDIA CUDA acceleration is recommended for faster voice processing.
  On Windows, `uv sync` selects the CUDA 12.8 PyTorch build automatically. It
  requires a compatible NVIDIA driver and the CUDA runtime libraries required
  by the speech dependencies.
- **Other GPUs:** The current voice implementation does not select Apple MPS,
  DirectML, or other non-CUDA acceleration backends.

Device selection is automatic; there is currently no CPU/GPU selector in the
menu or command line. CPU fallback occurs when CUDA is unavailable to PyTorch;
a later CUDA initialization or model-loading failure is reported as an error,
not automatically retried on the CPU. Minimum CPU, RAM, and GPU memory
requirements have not yet been benchmarked.

Voice dependencies are included in the standard installation; no `voice` extra
is defined. For example, install with Python 3.12 and start the application with:

```shell
uv sync --python 3.12
uv run --python 3.12 python main.py
```

Select **Options > Audio > Enable voice** and wait for voice initialization before
loading a scenario. **Options > Audio > Disable voice** turns it off. Alternatively,
pass `--voice` to initialize voice automatically at startup.

Dependency downloads can be large, especially for CUDA-enabled PyTorch.
The Whisper and Kokoro models
and pilot voice packs download on first use. Speech recognition and synthesis
run locally. Voice initialization and errors appear in the window title and
communications panel. Pilot audio uses an explicit pronunciation for Los
Angeles; the displayed readback text is unchanged.
Hugging Face model downloads work without a token but may be rate-limited; to
authenticate, use `uv run --python 3.12 hf auth login` or set
`HF_TOKEN` in your environment. Do not put tokens in project files.
PyTorch and Kokoro may emit platform, model-configuration, or deprecation
warnings during initialization; these originate in those dependencies.
The microphone stream is open while voice is enabled, but audio is captured in
memory only while push-to-talk is held. A transmission over 60 seconds is
rejected. Only frequencies that remain On for the entire transmission can
receive the resulting instruction.

Each generated aircraft is assigned one frequency by flight role: arrivals use
APP, departures DEP and overflights ENR. Civilian aircraft use VHF and military
aircraft use UHF. Select an aircraft to see its assigned frequency. These
assignments do not automatically change on handoff. To reach a pilot, turn
that frequency On and begin with the full callsign, for example:

* `Devil two seven niner, fly heading two seven zero`
* `November one three five tango charlie, turn right heading zero one zero`
* `Devil two seven niner, climb and maintain thirteen thousand`
* `Devil two seven niner, maintain bearing two six five`
* `Devil two seven niner, maintain bearing two six five to Imperial, contact Los Angeles Center 291.7`
* `Devil two seven niner, contact Los Angeles Center on 291.7`
* `Devil two seven niner, direct BZA`
* `Devil two seven niner, resume route` or `resume filed altitude`
* `Devil two seven niner, traffic twelve o'clock five miles`
* `Devil two seven niner, say traffic`
* `Devil two seven niner, ident`
* `Devil two seven niner, squawk three zero zero zero`
* `Devil two seven niner, heading two seven zero, correction two eight zero`
* `Devil two seven niner, radar contact bearing 240 altitude 13000 speed 400`
* `American Airlines three eight one heavy, squawk three zero zero zero`

The existing clearance restrictions still apply; headings are magnetic and direct
fixes must be on the remaining route. Heading instructions may specify a left
or right turn; otherwise the aircraft takes the shorter turn. Rejected voice
instructions, including their recognized text, are logged to the terminal.
The parser recognizes the observed transcription variants "hitting" for
"heading", "climbed" for "climb", and "turned" for "turn" in instruction
positions. It also recognizes the observed callsign transcription "double"
for "Devil", but rejects the call if it could address more than one aircraft.
In a callsign, it also accepts the observed "mic" transcription for "Mike"
while retaining literal callsign matching and rejecting ambiguity.
In callsigns and center frequencies, "niner" is also accepted when transcribed
as "9er" or "9 or".
It accepts the observed "identity", "identical", and "I dent" transcriptions
as `ident` and handles "two"/"to" swaps in numeric values and supported
instruction phrases. Within one transmission, "correction" can replace a
callsign, a complete instruction, or the value in a heading, altitude, bearing,
squawk, direct-fix or center-frequency instruction. Repeat the full instruction
if a partial correction is ambiguous; only the corrected instruction executes.
`AAL` callsigns may be spoken as "American" or "American Airlines", `UAL`
as "United", and `AMF` as "Am Flight". Pilot readbacks and departure check-ins
use those names. Aircraft with a model maximum takeoff weight of at least
300,000 pounds show an `H` after
the callsign on radar and strips and use "heavy" in radio calls. This weight-based
classification is simplified; the saved callsign itself is unchanged.
Squawk instructions require four octal digits and change the aircraft's
transponder; the strip's independently editable beacon annotation is unchanged.
A pilot acknowledges an advisory without claiming to see traffic.
An IDENT request shows `ID` and flashes the entire data block, leader line,
and secondary return for 18 simulation seconds. A pending handoff also flashes
the secondary return.
After a callsign-addressed `radar contact`, the secondary return and data block
turn green.
`Maintain bearing` assigns a magnetic heading; an optional `to` location is
informational and does not change the route. Initiate the radar handoff and
wait for acceptance before telling the pilot to contact the center, either
alone or with a bearing instruction. Until the frequency change, Yuma retains
communications and may issue instructions subject to its control limits.
A valid contact instruction transfers communications to the accepted center's
configured frequency and queues the readback on the original frequency. A wrong
frequency or one for a different selected sector prompts the pilot to ask for
verification instead.
On `say traffic`, the simulated pilot reports the nearest airborne aircraft
using simulator positions, not a visual-detection model. Pilot audio is heard
only while its frequency is monitored (On or Listen), and stops if the
controller transmits. The window title displays recognized speech and errors.
Recognition can be wrong; this is not for real-world ATC. Departure check-ins
are also spoken when voice is enabled and their assigned frequency is
monitored. Intrafacility lines do not yet have audio.
Pilot voices are assigned randomly when a scenario loads and remain associated
with their aircraft, including after saving and reloading or disabling and
reenabling voice. After 20 aircraft, voice presets are reused.

The right-hand flight progress strip panel lists active scenario plans. Scroll
over the panel to see additional strips; clicking a strip selects its radar
track, and selecting a radar track also highlights its visible strip. Drag a
strip above or below another to reorder it; use the wheel while dragging to
reach other strips. Release within the board outside a strip or press Escape to
cancel. After both radar handoff and radio-frequency transfer are complete,
drag a strip off the board (for example, onto the radar area) to discard it.
Press `R` to show discarded strips, select one and press Enter to restore it;
press `R` or Escape to return to the board. Discarding does not remove the
aircraft or flight plan, and discarded strips remain discarded when saved.
Drag a strip horizontally to offset it right or return it left; the offset is
approximately 64 logical pixels, so its physical size depends on display
scaling. Offsets are saved with the scenario.
Hover over a field for its purpose and the simulator's simplified annotations.
With a strip selected, press `1` for assigned altitude in feet, `2` for a
fix/time annotation, `3` for clearance/control remarks, `4` for its beacon
code, or `5` for its runway/pad. Type letters, digits, spaces, hyphens, slashes or periods; Backspace
edits, Enter saves, and Escape cancels. Beacon codes must be four octal digits
(`0`-`7`). An empty field clears the annotation. Clicking elsewhere cancels
an edit. The strip code starts as the aircraft's beacon code, but subsequent
edits change only the strip, not the simulated radar return. Annotations and
strip ordering do not change the filed plan and do not
command aircraft. A simulated landing deactivates the strip and removes the
secondary radar return; existing ARTS primary traces fade normally. This does
not represent actual flight-plan closure.

The legacy sample scenario, no longer offered in the Scenario menu, has ten
fictional plans: three IFR and one VFR
overflight, three arrivals and three departures. Flight type is inferred from
the plan endpoints relative to KNYL, not actual aircraft position or phase.
Across sample constructions, 80% use only primary non-medical civilian
airports (SAN, LAX and PHX), 15% have one occasional airport (LAS or ABQ),
and 5% have one rare airport (SFO, PDX, SEA, ONT, SNA or DEN). In the latter
two cases, other civilian choices remain primary. The airport is assigned to
a flight suitable for its aircraft range and overflight corridor. The local
medical helicopter is an exception. No additional traffic is generated during
a session.
The three KNYL departures begin stationary at field elevation and automatically
begin takeoff after 30, 60, and 90 seconds, without a controller takeoff command. Their
strips remain active while they wait. A simulated pilot check-in to Yuma
Departure, including the pilot's frequency, appears above the flight strips
15 seconds after liftoff; the most
recent three check-ins remain visible. This assumes one person staffs approach, departure
and enroute. Ground positions and runway headings are approximate, with no
taxi, runway conflict or tower coordination.
The startup tracks and route legs are kept north of the U.S.–Mexico border
using the included state boundary data; this is not a general border-monitoring
or airspace-avoidance system.
The aircraft and plan definitions are in `locations/Yuma/Scenarios/sample_data.py`;
`locations/Yuma/Scenarios/yuma.py` constructs the scenario. Additional inactive
aircraft remain in the data file.
Inactive local training and search examples use BZA as a placeholder route and
retain their mission descriptions as strip remarks; they do not simulate
restricted-area training or search operations.
Routes use three- to five-character alphanumeric identifiers for airports,
navaids, fixes and Victor airways, or `DCT` for a direct leg. VFR samples use
airport identifiers and navigation fixes without implying a landing at each
airport. For example, KIPL is an airport, while BZA and IPL are
different VORTACs; KIPL and IPL are not interchangeable. The samples do not
assert that these are charted visual reporting points.
Strips omit the leading K from U.S. airport identifiers for display only; the
underlying plans retain it. Consequently, an airport and a navaid can have
the same displayed identifier, such as KIPL and the IPL VORTAC.
The selected-strip route includes the destination airport after the listed
enroute fixes, matching the route followed by the aircraft.

The simulator assumes these plans are cleared and guides each aircraft from
its nearest remaining route leg through the listed fixes toward the destination.
Airway segments are expanded using the local navigation CSVs, and unsupported
or disconnected routes raise an error instead of silently flying direct.
Guidance uses aircraft turn and climb rates, flies toward the filed altitude,
and retains the current speed until the simplified landing phase. It then
descends and slows for an automatic landing at destination field elevation.
IFR sample cruise altitudes use the odd/even convention for the overall
magnetic direction of the flight. A flight has one filed cruise altitude;
changes of direction along its route do not automatically change it. Local
round-trip training has no single overall direction. ATC altitude exceptions
and their required coordination are not simulated. See FAA Order 7110.65
[4-5](documentation/ATC_7110.65BB/chapter_4/chap4_section_5.html).
This is not a runway approach, terrain-avoidance system, or operational
clearance. Route edits to the underlying plan are resolved again; strip
annotations do not change the route.

To issue a simulated clearance, select an airborne aircraft and press `G`. Enter
`HDG 090` for a magnetic heading, `ALT 6000` for an altitude in feet, `DCT FIX`
for a fix on the remaining expanded route, `RESUME` to fly to the next
remaining route fix after a vector, or `ALT CLR` to release the assigned
altitude and return to normal filed-altitude guidance. Press Enter to issue
the instruction or Escape to cancel. A text readback appears on the scope.
Use the full internal airport code for a direct-to airport (for example
`KIPL`), to distinguish it from a navaid with the same displayed code.
Direct-to skips earlier fixes but does not change the filed plan. A heading
vector suspends route guidance; an assigned altitude persists across route
changes and vectors. While either is active, automatic descent and landing
are inhibited; release the altitude and resume route guidance to restore
them. Assigned altitudes are separate from editable strip annotations.
Clearances require an airborne aircraft with Yuma track and communications
ownership, no pending handoff, and an altitude within Yuma's control limit.
These are simplified text interactions; they do not model voice, separation,
terrain, airspace restrictions, or coordination approvals.

The Yuma scenario initially assumes 03L, 03R and 35 are active. The active
runways appear in the top bar. Use Options > Runways to select one parallel
pair (03L/03R or 21L/21R) and independently select one of 08, 17, 26 or 35.
Waiting departures assigned to a runway being replaced are reassigned and
aligned with the new runway; a change is blocked while an affected departure
is taking off. Existing arrival strip assignments are not changed automatically.
Active runways are saved with the scenario.
Yuma-bound or departing military and commercial samples, including the
Citation M2 and V-22, alternate between 03L/03R; small civilian fixed-wing
samples use 35. Helicopter strips
rotate through `P1`, `P2`, `P3` and `P5`, denoting the VTOL pads on the
provided airport diagram; `PAD` means an unspecified pad. Pad 4 is excluded
because the [FAA-derived Yuma listing](https://www.airnav.com/airport/KNYL)
states that rotary-wing recovery there is unavailable. Overflights are not
automatically assigned. Key `5` accepts an active runway, an included pad,
`PAD`, or an empty field; it only changes the strip, not aircraft movement or
clearance. The provided diagram depicts runway 17/35, while the online listing
does not list it. This configuration is a simulator assumption, not current
operational availability, and assignments are not suitability checks.

The strip grid follows the terminal form in FAA Figure 2-3-4/5/6: the
identity, type, beacon code and departure-specific requested altitude and
airport occupy their corresponding fields. Field 10 shows the simulator's
runway/pad annotation. Other unavailable operational fields remain blank or
`--`. Field 8 shows `ENR` for overflights. Routes, annotations and destinations use a
simplified field 9; long entries are abbreviated there but shown in full in
the selected-strip details below. Strip altitudes are in hundreds of feet;
the editor and detailed view use feet. A plan originating at the facility,
including a local round trip, is displayed as a departure; otherwise a plan
ending there is an arrival, and other plans are overflights. This is not a
determination of actual flight phase.

These are simplified simulator strips, not operational FAA forms. Their
fictional plans and annotations are not suitable for navigation or control.
The sample routes are illustrative, not verified filings or operational
clearances. Airway and procedure currency, terrain, equipment, and airspace
availability are not checked. Times are not invented. Military examples include simulated arrivals and departures at
El Centro (KNJK), North Island (KNZY), Miramar (KNKX), Camp Pendleton
(KNFG), Fallon (KNFL), Luke (KLUF), and Yuma restricted areas. Plans do not
represent actual restricted-area clearance or availability.
Flight plan and control information guidance appears in FAA
[2-2](documentation/ATC_7110.65BB/chapter_2/chap2_section_2.html), with strip
guidance in [2-3](documentation/ATC_7110.65BB/chapter_2/chap2_section_3.html).

The first line also shows simulated track ownership: `Y` for Yuma, `L` for
Los Angeles Center, and `A` for Albuquerque Center. These are illustrative
simulator identifiers, not verified operational position symbols. An offer
appears as `Y>L`, `Y>A`, `L>Y`, or `A>Y`. Sample and generated inbound IFR
aircraft start under center track and communications ownership and automatically
offer a handoff to Yuma when they appear. The simplified center selection uses
Los Angeles for aircraft west of or on Yuma's longitude, and Albuquerque for
aircraft east of it; above FL230, Los Angeles is used regardless of longitude.
This is not a representation of actual sector boundaries. Other startup tracks
belong to Yuma.
The secondary return and data block are white for uncontrolled aircraft, gold for incoming
center-controlled aircraft, green after Yuma says `radar contact`, and blue
after an outgoing handoff is accepted. An incoming handoff remains gold until
Yuma establishes radar contact. These colors are simulator conventions.
For a selected Yuma-owned aircraft, press H and then L or A to offer a radar
handoff. Enter pertinent coordination information and restrictions (or `NONE`
if there are none), press Enter, review the target and coordination, and press
Y to confirm. The simulated center accepts after three seconds. For a selected
Yuma-owned aircraft, alternatively press H, type sector 9, 10, 31 or 42, then
press Enter to offer an automated handoff to that sector without entering
coordination details. The return flashes until the simulated center accepts;
communications remain with Yuma until transferred separately.
For a selected center-owned aircraft without a pending offer, press I and enter
the simulated incoming information to create one manually. Press A, review the
target and restrictions, and press Y to accept an incoming offer. X cancels or
rejects a pending offer; rejected automatic offers are not repeated. Escape
cancels a prompt.

Radar identification and communications are separate in this simulation.
After accepting a handoff, press C, review the coordination reminder, and press
Y to record the communications transfer. Following an incoming handoff, V
records the controller's confirmation of identification; this does not
automatically establish the green radar-contact indication. Complete both
steps before initiating another radar handoff.
After accepting the incoming IFR handoff and transferring communications, the
pilot checks in with Yuma Approach once within 30 nautical miles of NYL,
including for overflights. The check-in uses the aircraft's VHF or UHF approach
frequency and occurs once, even across a saved and reloaded scenario. Monitor
that approach frequency to hear the call; it also appears in the pilot check-ins
area above the flight strips.

For a point-out, select the aircraft and press P; for traffic coordination,
press T. A Yuma-owned track prompts for L or A; a center-owned track simulates
an incoming request. Enter the pertinent information, review and confirm with
Y. Traffic coordination requires a restriction, including the affected
traffic where appropriate. Simulated centers respond after three seconds;
for an incoming request, A then Y records approval or traffic observed, and X
rejects it. D closes an approved coordination; its information remains in
memory for the session. A point-out or traffic coordination does not transfer
track or communications ownership. Only one such coordination can be open per
aircraft at a time.

These are simplified, controller-attested interactions informed by
[5-4-3](documentation/ATC_7110.65BB/chapter_5/chap5_section_4.html#5-4-3),
[5-4-4](documentation/ATC_7110.65BB/chapter_5/chap5_section_4.html#5-4-4),
[5-4-5](documentation/ATC_7110.65BB/chapter_5/chap5_section_4.html#5-4-5),
[5-4-6](documentation/ATC_7110.65BB/chapter_5/chap5_section_4.html#5-4-6),
and [5-4-7](documentation/ATC_7110.65BB/chapter_5/chap5_section_4.html#5-4-7),
not proof that coordination, identification, separation, or radio transfer
actually occurred. The simulator does not verify conflicts or enforce entered
restrictions, changes requiring receiving-controller approval, facility
directives, AIT, or prearranged coordination. It has no geographic boundary
checks or Mexican handoffs.

The simulated Yuma control limit is FL230 inclusive; LA Center controls above
it. Yuma-owned tracks above the limit produce a persistent warning until they
descend to FL230 or are handed off. Offer the handoff manually to LA with H,
then L; the simulated acceptance still takes three seconds. Above the limit,
Yuma cannot accept incoming handoffs and outgoing handoffs must be to LA.
An Albuquerque offer pending when the aircraft crosses the limit is canceled.
Center-owned tracks do not automatically return to Yuma after descending.
Aircraft are not prevented from climbing, and the simulator compares its
altitude value in hundreds of feet directly with the flight level; it does not
model pressure-altitude conversion or geographic airspace boundaries.

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

Additional aircraft models are defined in `simulator/core/aircraft_models.py`, with
links to reference data. Unspecified performance and maneuver rates are
estimates; the simulator does not model rotorcraft-specific flight dynamics.
For helicopters, the model's `wing_span` is rotor diameter and `stall_speed`
is not applicable. For the V-22, `wing_span` is its width with rotors turning
and no single stall speed is modeled. A zero takeoff distance represents
vertical takeoff under suitable conditions, not a guarantee at every weight
or altitude. The F-35 model is the carrier-capable F-35C used by the Navy and
Marine Corps. Tiltrotor conversion and Harrier vertical flight are not modeled.

## Licensing & Commercial Use

**Copyright © 2024-2026. All rights reserved.**

This software is proprietary. Unauthorized copying, distribution, or commercial 
use without an explicit commercial license is prohibited.

For commercial licensing inquiries or questions about permitted use, contact the 
copyright holder.

### Third-Party Licenses

This project incorporates open-source libraries licensed under MIT, BSD, and 
Apache 2.0 licenses. All third-party components are used in compliance with 
their respective licenses.

See [ATTRIBUTION.md](ATTRIBUTION.md) for complete attribution and license details 
for all third-party dependencies.
