# ATTRIBUTION & THIRD-PARTY LICENSES

This project incorporates the following open-source libraries, each governed by its own license:

## Core Dependencies

### Arcade Game Engine
- **Library**: arcade
- **Version**: >=3.3.3,<4
- **License**: MIT License
- **URL**: https://arcade.academy/
- **Purpose**: 2D game framework for rendering radar display and UI
- **Attribution**: © 2024 Simpson

### Pyglet
- **Library**: pyglet
- **Version**: >=2.1.19,<3
- **License**: BSD 3-Clause License
- **URL**: https://pyglet.readthedocs.io/
- **Purpose**: Low-level graphics and window management
- **Attribution**: © Pyglet contributors

### PyTorch
- **Library**: torch
- **Version**: >=2.0,<3
- **License**: BSD License
- **URL**: https://pytorch.org/
- **Purpose**: Machine learning framework for speech processing
- **Attribution**: © Meta Platforms, Inc.

## Speech & Audio Processing

### Faster Whisper
- **Library**: faster-whisper
- **Version**: >=1.2.1,<2
- **License**: MIT License
- **URL**: https://github.com/guillaumekln/faster-whisper
- **Purpose**: Speech-to-text recognition
- **Attribution**: © Guillaume Klein

### Kokoro TTS
- **Library**: kokoro
- **License**: Apache License 2.0
- **URL**: https://github.com/hexgrad/kokoro
- **Purpose**: Text-to-speech synthesis for pilot voice generation
- **Attribution**: © Hexgrad contributors
- **Note**: Requires attribution in documentation

### Spacy (en-core-web-sm)
- **Library**: en-core-web-sm
- **Version**: 3.8.0
- **License**: MIT License
- **URL**: https://spacy.io/
- **Purpose**: Natural language processing for voice command parsing
- **Attribution**: © Explosion AI

### Misaki
- **Library**: misaki
- **Version**: >=0.1.0
- **License**: MIT License
- **URL**: https://github.com/tamuhey/misaki
- **Purpose**: Text pronunciation conversion
- **Attribution**: © tamuhey

### SoundDevice
- **Library**: sounddevice
- **Version**: >=0.5.1,<1
- **License**: MIT License
- **URL**: https://python-sounddevice.readthedocs.io/
- **Purpose**: Audio input/output for voice communication
- **Attribution**: © Christoph Gohlke

## Geospatial & Data Processing

### GeoPandas
- **Library**: geopandas
- **Version**: >=1.2.0
- **License**: BSD 3-Clause License
- **URL**: https://geopandas.org/
- **Purpose**: Geographic data processing for airport locations and airspace
- **Attribution**: © GeoPandas contributors

### Shapely
- **Library**: shapely
- **Version**: >=2.0
- **License**: BSD 3-Clause License
- **URL**: https://shapely.readthedocs.io/
- **Purpose**: Geometric operations for distance calculations and airspace boundaries
- **Attribution**: © Shapely contributors

### Polars
- **Library**: polars
- **Version**: >=2.1.0
- **License**: MIT License
- **URL**: https://www.pola-rs.com/
- **Purpose**: Fast data frame processing for flight data
- **Attribution**: © Polars contributors

### PyArrow
- **Library**: pyarrow
- **Version**: >=26.0.1
- **License**: Apache License 2.0
- **URL**: https://arrow.apache.org/docs/python/
- **Purpose**: Data serialization and columnar storage
- **Attribution**: © Apache Software Foundation

### NumPy
- **Library**: numpy
- **Version**: >=2.5.4,<3
- **License**: BSD 3-Clause License
- **URL**: https://numpy.org/
- **Purpose**: Numerical computing and array operations
- **Attribution**: © NumPy contributors

## Utility

### DarkDetect
- **Library**: darkdetect
- **Version**: >=0.8.0,<1
- **License**: MIT License
- **URL**: https://github.com/albertosottile/darkdetect
- **Purpose**: Detect system dark mode preference for UI theming
- **Attribution**: © Alberto Sottile

## Development Tools

### Ruff
- **Library**: ruff
- **Version**: 0.17.5
- **License**: MIT License
- **URL**: https://docs.astral.sh/ruff/
- **Purpose**: Python linter and formatter (development only)
- **Attribution**: © Astral Software

## License Compliance

All third-party components are used in accordance with their respective licenses. 
Derivative works maintain compatibility with these licenses.

For detailed license texts, see the LICENSE files in each package's source repository 
or install directory.

## Data Attribution

This project also incorporates public domain geospatial data from the FAA and 
U.S. Government sources. See [DATA_ATTRIBUTION.md](DATA_ATTRIBUTION.md) for 
comprehensive attribution of all datasets including:

- FAA Airport and Navigation Data
- Airspace Boundaries and Frequencies
- ATS Routes and Designated Points
- U.S. State Boundary Data
- FAA Order 7110.65 Reference Documentation

---

**Last Updated**: 2026-11-16
