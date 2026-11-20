# DATA SOURCES & ATTRIBUTION

This document provides attribution for all data files used in the ATC Simulator.

## Geospatial Data (GIS)

### Source: FAA Aeronautical Datasets

The following datasets are derived from or based on the **FAA's public geospatial data**:

**Availability**: https://www.faa.gov/air_traffic/publications/notices/index.cfm?xml=notices/dof/notice-dof-11

**License**: Public Domain (U.S. Government data)

**Included Datasets**:

| Dataset | File(s) | Description | Coverage |
|---------|---------|-------------|----------|
| **Airports** | `Airports.csv` / `Airports.geojson` | Airport locations, identifiers, elevation, operational status | Contiguous U.S., Alaska, Hawaii |
| **NAVAID System** | `NAVAID_System.csv` / `NAVAID_System.geojson` | Navigation aids (VORs, NDBs, DMEs) | U.S. airspace |
| **ATS Routes** | `ATS_Route.csv` / `ATS_Route.geojson` | Victor and Jet routes for instrument flight | U.S. airspace |
| **Class Airspace** | `Class_Airspace.csv` / `Class_Airspace.geojson` | Controlled airspace classes (A-E) | U.S. airspace |
| **Special Use Airspace** | `Special_Use_Airspace.csv` / `Special_Use_Airspace.geojson` | Restricted areas, MOAs, Warning areas | U.S. airspace |
| **Designated Points** | `Designated_Point.csv` / `Designated_Point.geojson` | Flight plan fixes and waypoints | U.S. airspace |
| **Route Airspace** | `Route_Airspace.csv` / `Route_Airspace.geojson` | Preferred routing corridors | U.S. airspace |
| **Holding Patterns** | `Holding_Pattern.csv` / `Holding_Pattern.geojson` | Standard instrument approach holds | U.S. airspace |
| **Frequencies** | `Frequency.csv` | Radio frequencies for navigation and communication | U.S. facilities |
| **Airspace Boundaries** | `Airspace_Boundary.csv` / `Airspace_Boundary.geojson` | Sector and regional boundaries | U.S. airspace |
| **Radial Bearing** | `Radial_Bearing.csv` / `Radial_Bearing.geojson` | Navigation radials from VORs and NDBs | U.S. airspace |
| **Pending Runway** | `Pending_Runway.csv` / `Pending_Runway.geojson` | Planned runway construction/modifications | U.S. airports |

### U.S. State Boundaries

**File(s)**: `us-state-boundaries.csv` / `us-state-boundaries.geojson`

**Source**: Public domain U.S. geographical data

**Purpose**: Map reference and airspace visualization

**License**: Public Domain

### Data Processing & Attribution

The FAA datasets have been:
- Filtered for geographic scope (focus on Southwest U.S., particularly Arizona)
- Converted between CSV and GeoJSON formats
- Used to populate navigation databases for flight planning and airspace visualization

**FAA Data Disclaimer**:
> This data is provided by the Federal Aviation Administration for public use. 
> While efforts are made to maintain accuracy, the FAA makes no warranty regarding 
> the completeness or accuracy of this data. Users should verify critical 
> information with current FAA publications and facilities.

**Citation Format**:
```
Data derived from FAA Aeronautical Datasets
https://www.faa.gov/air_traffic/publications/notices/index.cfm?xml=notices/dof/notice-dof-11
U.S. Government data - Public Domain
```

## Reference Documentation

### FAA Order 7110.65 (Air Traffic Control)

**File(s)**: `documentation/ATC_7110.65BB/`

**Source**: Federal Aviation Administration

**Edition**: 7110.65BB with changes 1-3 (effective July 9, 2026)

**License**: Public Domain (U.S. Government publication)

**Purpose**: ATC procedures, separation standards, and operational guidance

**Availability**: https://www.faa.gov/documentLibrary/media/Notice/N_JO_7110_65.pdf

**Citation Format**:
```
FAA Order 7110.65BB - Air Traffic Control
U.S. Federal Aviation Administration
Public Domain
https://www.faa.gov/documentLibrary/media/Notice/N_JO_7110_65.pdf
```

## Scenario Data

### Location Data

Location configuration files (`locations/Yuma/__init__.py`, etc.) include:
- Coordinates and elevation (derived from FAA airport data)
- Runway configurations
- Radio frequencies (from FAA frequency data)
- Magnetic declination (calculated using U.S. NOAA data)

**Sources**:
- FAA airport database (public domain)
- NOAA magnetic declination models (public domain)

## Data Usage Compliance

All data included in this project is used in accordance with applicable licenses:

1. **FAA Public Domain Data**: No restrictions on use or redistribution
2. **U.S. Government Data**: Public domain - no licensing requirements
3. **Scenario-Generated Data**: Original content created for simulation purposes

## Commercial Use of Data

This project may be commercialized. All included geospatial and reference data 
are from public domain sources with no commercial use restrictions.

---

## Summary Table

| Data Category | Source | License | Restrictions |
|---|---|---|---|
| Airports, NAVAIDs, Airspace | FAA | Public Domain | ✅ None |
| ATS Routes, Frequencies | FAA | Public Domain | ✅ None |
| State Boundaries | U.S. Government | Public Domain | ✅ None |
| FAA Order 7110.65 | FAA | Public Domain | ✅ None |
| Scenario Data | Original/FAA | Public Domain / Original | ✅ None |

---

**Last Updated**: 2026-11-16
**Maintained By**: ATC Simulator Project
