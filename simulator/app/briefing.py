"""Build a controller handoff briefing from the current scenario."""

from simulator.core.aircraft import display_callsign


def briefing_pages(facility, strips, communications):
    channels = [
        f"{channel.label} {channel.frequency or '--'} {channel.state.value}"
        for channel in communications.channels
    ]
    lines = [
        f"{line.label}: {'HOT' if line.hot else 'COLD'}"
        for line in communications.lines + communications.interfacility_lines
    ]
    pages = [
        [
            f"Location: {facility.name}",
            f"Active runways: {', '.join(facility.active_runways) or 'none'}",
            f"Helicopter pads: {', '.join(facility.helicopter_pads) or 'none'}",
            "Weather: not simulated; altimeter 29.92 assumed",
            f"Traffic: {sum(strip.active for strip in strips)} active aircraft",
        ]
    ]
    for start in range(0, len(channels), 10):
        pages.append(["Radio frequencies:", *channels[start : start + 10]])
    if lines:
        pages.append(["Coordination lines:", *lines])

    active = [strip for strip in strips if strip.active]
    for start in range(0, len(active), 2):
        page = ["Traffic and clearances:"]
        for strip in active[start : start + 2]:
            aircraft = strip.aircraft
            plan = strip.flight_plan
            guidance = aircraft.flight_guidance
            departure = aircraft.departure
            heading = round(facility.location.true_to_magnetic(aircraft.heading)) % 360
            status = (
                f"departure {departure.state}"
                if departure is not None and not departure.airborne
                else "airborne"
            )
            if departure is not None and departure.scheduled_utc is not None:
                status += f"; scheduled {departure.scheduled_utc:%Y-%m-%d %H:%M:%S} UTC"
            assigned = (
                f"{guidance.assigned_altitude} FT"
                if guidance is not None and guidance.assigned_altitude is not None
                else "none"
            )
            vector = (
                f"{round(facility.location.true_to_magnetic(guidance.vector_heading)) % 360:03d}"
                if guidance is not None and guidance.vector_heading is not None
                else "route"
            )
            track = aircraft.track
            coordination = track.coordination
            page.extend(
                [
                    "",
                    f"{display_callsign(aircraft)} {aircraft.aircraft_model.aircraft_type} - {status}",
                    f"{plan.origin} to {plan.destination} via {plan.route}",
                    f"Position {aircraft.lat:.4f}, {aircraft.lon:.4f}",
                    f"Altitude {aircraft.altitude * 100:.0f} FT, heading {heading:03d} magnetic, speed {aircraft.speed:.0f} KT",
                    f"Filed {plan.altitude} FT, assigned {assigned}, heading clearance {vector}",
                    f"Target speed: {f'{aircraft.target_speed:.0f} KT' if aircraft.target_speed is not None else 'none'}",
                    f"Runway/pad {strip.operation_area or '--'}; track {track.owner.value}; communications {track.communications_owner.value}",
                    f"Handoff: {track.handoff_target.value if track.handoff_target else 'none'} {track.handoff_information}",
                    (
                        f"Coordination: {coordination.kind.value} to {coordination.target.value} "
                        f"({'approved' if coordination.approved else 'pending'}): {coordination.information}"
                        if coordination is not None
                        else "Coordination: none"
                    ),
                    f"Strip altitude: {strip.assigned_altitude or '--'}; fix/time: {strip.fix_time or '--'}",
                    f"Strip remarks: {strip.remarks or 'none'}",
                ]
            )
        pages.append(page)
    if not active:
        pages.append(["No active traffic."])
    return pages
