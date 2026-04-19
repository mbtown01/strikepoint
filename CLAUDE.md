# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

StrikePoint is a dual-camera golf strike detection system for Raspberry Pi. It captures simultaneous thermal (FLIR Lepton) and visual (PiCamera2) footage, ties the two images together, and shows the user where their club hit the ground.  When used in practice, this feedback can help a golfer understand their strike pattern, adjust their swing, and quickly iterate in an effort to improve their game.  

## Commands

### Build the C++ Driver Library

```bash
cd cpp
./compile Debug       # or Release
# Outputs: cpp/Debug/libstrikepoint.so
```

### Run the Application

```bash
# Live device capture (requires Raspberry Pi hardware)
python main.py

# Playback from a recorded binary file (works on any machine)
python main.py --input-recording dev/data/recording.bin

# Open browser at http://localhost:8050
```

### Run Tests

```bash
# All tests
python -m pytest test/

# Single test file
python -m pytest test/test_frames.py

# Single test case
python -m pytest test/test_frames.py::FrameWriterReaderTests::test_write_read_roundtrip
```

Tests that require `libstrikepoint.so` (e.g., `test_driver.py`) need the C++ library compiled first. All other tests run without hardware.

## Architecture

### Three-Tier System

**1. Hardware Layer (C/C++)**
- `cpp/` — FLIR Lepton SDK + audio event detection compiled into `libstrikepoint.so`
- Exposes SPLIB_* C functions for frame capture, audio strike detection, and memory-based logging
- Wrapped in Python via ctypes in `strikepoint/driver.py`

**2. Frame Capture Layer**
- `strikepoint/frames.py` — `FrameInfo` (thermal + visual + metadata), binary serialization with msgpack+JPEG (`FrameInfoWriter`/`FrameInfoReader`)
- Two provider implementations in `main.py`: `DeviceBasedFrameInfoProvider` (live cameras) and `FileBasedFrameInfoProvider` (recording playback)
- The driver thread in `StrikePointDashApp` loops ~30–60 FPS: get frame → register with ContentManager → publish `FrameEvent` → pump EventBus

**3. Application Layer (Dash Web UI)**
- `strikepoint/dash/app.py` — `StrikePointDashApp`: main orchestrator, owns the capture driver thread
- `strikepoint/dash/content.py` — `ContentManager`: MJPEG streaming and image serving via Flask routes
- `strikepoint/dash/calibrate.py` — `CalibrationDashUi`: 3-point calibration modal
- `strikepoint/dash/strike.py` — `StrikeDetectionDashUI`: strike result history cards
- `strikepoint/dash/events.py` — `DashEventQueueManager`: bridges async Dash UI to synchronous EventBus via 250ms polling interval

### EventBus Design

`strikepoint/events.py` — synchronous, pumped event bus. No dedicated dispatcher thread.

- Subscribers register by event type; publishers enqueue events
- `pump()` drains the queue on the **capture driver thread** — subscribers run there too
- Consequence: slow subscribers block the frame loop; keep them fast
- Key events: `FrameEvent`, `CalibrationProgressEvent`, `CalibrationUpdatedEvent`, `StrikeDetectedEvent`, `LogBatchEvent`

### Threading Model

- **Main thread**: Dash/Flask web server
- **Capture driver thread** (daemon): frame loop — blocks on camera I/O, pumps EventBus, drains log queue
- **No other threads** — the EventBus synchronous design intentionally avoids additional threads

### Processing Engines

- `strikepoint/engine/calibrate.py` — `CalibrationEngine`: collects 3 ball positions in both thermal and visual frames, computes affine transform via `cv2.getAffineTransform()`, saves matrix to SQLite
- `strikepoint/engine/strike.py` — `StrikeDetectionEngine`: triggered by audio flag from C driver; compares thermal frames before/after impact, computes temperature delta and heat asymmetry score
- `strikepoint/engine/util.py` — Hough circle detection helpers for both frame types

### Database

SQLite (`strikepoint.db`), managed by `strikepoint/database.py` via SQLAlchemy. Stores calibration transform matrices as JSON-serialized 2×3 numpy arrays.

## Key Design Decisions

- **Synchronous EventBus on capture thread**: deterministic control flow, simpler debugging, no cross-thread race conditions. Tradeoff: all subscribers must be fast.
- **`FileBasedFrameInfoProvider`**: enables full-stack development and testing without Raspberry Pi hardware — use `dev/data/recording.bin` recordings.
- **Thermal-to-visual overlay**: calibration affine transform maps thermal heat signatures into visual frame space for overlay rendering.
- **`DashEventQueueManager` 250ms poll**: decouples the synchronous capture thread from Dash's async callback system without blocking either side.
