# Drone-TurtleBot Bridge 🛸🤖

A ROS 2 + MAVLink framework for **drone-to-ground-robot coordination**. A Pixhawk flight controller (carried by a person or mounted on a drone) provides GPS position via MAVLink, and a TurtleBot3 ground robot autonomously follows the drone's position in real time.

The system also includes an **LLM-based telemetry supervisor** that uses OpenAI or Ollama to analyze drone health in real time, and a **turn-detection pipeline** that relays yaw changes from the drone to the TurtleBot.

---

## Architecture

```
┌─────────────┐   MAVLink/UDP   ┌──────────────────────┐   ROS 2 /cmd_vel   ┌────────────┐
│   Pixhawk    │ ──────────────► │  Bridge Script (PC)  │ ──────────────────► │ TurtleBot3 │
│  (GPS+IMU)   │                 │  drone_to_turtlebot  │                    │  (Burger)  │
└─────────────┘                 │     _bridge.py       │ ◄──────────────── │            │
                                └──────────────────────┘   ROS 2 /odom      └────────────┘
```

---

## File Descriptions

### Core Bridge

| File | Description |
|------|-------------|
| **`drone_to_turtlebot_bridge.py`** | **Main bridge script.** Runs on the TurtleBot's companion computer (or a networked PC). Reads Pixhawk GPS position via MAVLink, converts GPS coordinates (North/East) to TurtleBot odom frame (Forward/Left) using a reflection matrix, and publishes `cmd_vel` commands to drive the TurtleBot toward the drone. Supports GPS, LOCAL_POSITION_NED, ATTITUDE (tilt-to-drive), and simulated modes. Includes an optional LLM mission supervisor thread. |
| **`mavlink_forwarder.py`** | **MAVLink UDP forwarder.** Runs on a Windows PC connected to the Pixhawk via USB/serial (COM port). Reads MAVLink messages from the Pixhawk and forwards them over UDP to the TurtleBot's IP. Requests LOCAL_POSITION_NED, ATTITUDE, and SYS_STATUS streams at configurable rates. |

### LLM Telemetry Analysis

| File | Description |
|------|-------------|
| **`drone_llm.py`** | **Ollama-based telemetry analyzer.** Connects to the Pixhawk via serial, collects attitude, battery, and altitude data every 5 seconds, and sends it to a local Ollama LLM (LLaMA 3) for stability and health analysis. Lightweight, runs fully offline. |
| **`drone_llm_openai.py`** | **OpenAI-based telemetry analyzer with turn detection.** Same telemetry collection as above but uses OpenAI GPT-4o-mini for analysis via streaming. Also includes a **yaw change detector** that identifies left/right turns (threshold: ~15°) and sends turn commands to the TurtleBot via UDP. |
| **`drone_llm_openai_benchmark.py`** | **Benchmarking variant** of the OpenAI pipeline. Uses GPT-4.1 and measures detailed latency metrics: Time-to-First-Token (TTFT), tokens/second, and running average/min/max latency across all LLM calls. Used for evaluating real-time performance. |

### TurtleBot Nodes

| File | Description |
|------|-------------|
| **`turtlebot_sender.py`** | **ROS 2 odometry sender.** Runs on the TurtleBot. Subscribes to `/odom`, extracts the robot's position, and sends it to a PC via UDP. Also runs a background thread listening for drone turn commands (left/right) on a separate port. |

### Drone Control

| File | Description |
|------|-------------|
| **`pc_turtlebot_pixhawk_bridge.py`** | **PC-based drone position controller.** Receives TurtleBot position via UDP and optionally commands the Pixhawk drone to fly to that position using `SET_POSITION_TARGET_LOCAL_NED`. Supports GUIDED mode, arming, and takeoff. Used for the reverse scenario: drone follows the TurtleBot. |

### Utilities

| File | Description |
|------|-------------|
| **`test_drone_data.py`** | **MAVLink debug tool.** Connects to the Pixhawk and prints raw telemetry messages (HEARTBEAT, SYS_STATUS, ATTITUDE, GPS_RAW_INT, GLOBAL_POSITION_INT) for debugging and verifying the connection. |

---

## Setup & Configuration

### Prerequisites

- **Python 3.8+**
- **ROS 2 Humble/Iron** (for TurtleBot nodes)
- **Pixhawk flight controller** with GPS module
- **TurtleBot3 Burger** (or compatible differential-drive robot)

### Python Dependencies

```bash
pip install pymavlink openai python-dotenv
```

### Key Configuration (drone_to_turtlebot_bridge.py)

```python
# Connection
PIXHAWK_CONNECTION = "udp:0.0.0.0:14550"   # or "COM10" for direct serial

# Mode: "GPS", "LOCAL", "ATTITUDE", or "SIM"
DRONE_SOURCE = "GPS"

# TurtleBot heading (compass degrees from North)
# 0=North, 90=East, 180=South, 270=West
TURTLEBOT_FACING_DEG = 270   # Set to match your TurtleBot's facing direction

# Motion limits
MAX_LINEAR_SPEED = 0.22      # TurtleBot3 Burger max
MAX_ANGULAR_SPEED = 1.0      # rad/s
```

### GPS → Odom Frame Conversion

The bridge uses a **reflection matrix** (not rotation) to convert GPS coordinates to the TurtleBot's odom frame, because GPS (North/East) and odom (Forward/Left) have different handedness:

```
odom_x =  gps_x × cos(H) + gps_y × sin(H)
odom_y =  gps_x × sin(H) − gps_y × cos(H)
```

Where `H` is the compass heading the TurtleBot is facing (in radians).

---

## Usage

### Option 1: Direct Connection (TurtleBot has Pixhawk on its network)

```bash
# On the TurtleBot companion computer:
python3 drone_to_turtlebot_bridge.py
```

### Option 2: PC as MAVLink Forwarder

```bash
# On Windows PC (connected to Pixhawk via USB):
python mavlink_forwarder.py

# On the TurtleBot:
python3 drone_to_turtlebot_bridge.py
```

### Running the LLM Supervisor

```bash
# With Ollama (offline):
python drone_llm.py

# With OpenAI (cloud):
# Set OPENAI_API_KEY in .env first
python drone_llm_openai.py
```

---

## Environment Variables

Create a `.env` file (not tracked by git):

```
OPENAI_API_KEY=sk-your-key-here
```

---

## License

MIT
