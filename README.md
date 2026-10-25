# iPhone 6 (iOS 12) as a stationary sensor node

> **Notice: AI-assisted ("vibe-coded") project.** The code and documentation in this repo were written mostly by an
> AI coding assistant (Claude Code) working interactively with the phone's owner, who ran the hardware steps and
> tested everything on one phone. The code has **not** been audited or reviewed by a security professional, several
> results were observed only a few times, and parts of it run as root and modify system files on a jailbroken
> device. Read the code before you run it, and keep a backup.

Turn an old **checkra1n-jailbroken iPhone 6 (A8, iOS 12.0.1)** into a sensor that streams to your own server:
accelerometer, gyroscope, magnetometer, barometer, ambient light, temperatures, charger/battery power readings,
and a **sound level** (a loudness number, never audio), over **MQTT**, through **Tailscale**, into a small
dashboard with 7 days of history.

```
 iPhone 6 (jailbroken, iOS 12)                 homelab server
 ┌──────────────────────────────┐              ┌───────────────────────────────────────┐
 │ sensor_mqtt.py (Python 3.9)  │  MQTT over   │ Mosquitto broker (login required,     │
 │  HID sensors + mic level     ├─ Tailscale ─►│  listens on tailnet + localhost only) │
 │  via the local SOCKS5 proxy  │              │      │                                │
 │ tailscaled (userspace mode)  │              │      ▼                                │
 └──────────────────────────────┘              │ sensor_hub.py: SQLite + dashboard :8088│
                                               └───────────────────────────────────────┘
```

This builds on **[ios12-tailscale](https://github.com/sodapop1s/ios12-tailscale)**, which gets Tailscale running on
the phone. Do that first.

## What it reads, and how

Everything is read from plain Python with `ctypes`: **nothing is compiled** (the phone has no compiler).
The sensors are exposed through iOS's private HID event system; details and the discovery method are in
[`docs/SENSORS.md`](docs/SENSORS.md).

| Reading | Source on the iPhone 6 | Notes |
|---|---|---|
| Accelerometer (g), peak and vibration level | HID, usage 0xFF00/3 | ~10 samples/s, summarised once a second |
| Gyroscope, magnetometer | HID, 0xFF00/9 and 0xFF00/10 | units not independently verified |
| Barometer | HID, page 0x20 / usage 0x31 | first field looks like kPa (~102 kPa here) |
| Ambient light | HID, 0xFF00/4 | three raw channels |
| Temperatures | HID temperature services | SoC, TCC, battery gauge, charger junction |
| Charger / battery power | HID "power" events | volts and amps; `*_accum` values are running totals; unit scale of amps not verified |
| **Sound level** | AudioQueue input | RMS and peak in dBFS. **No audio is stored or sent.** Needs a microphone exception, see below |

## Status (what has and has not been verified)

Tested on one phone: **iPhone 6 (iPhone7,2), iOS 12.0.1, Procursus bootstrap, Tailscale 1.68.2 from ios12-tailscale,
Mosquitto 2.0.21 on Debian 13.**

| Claim | Evidence |
|---|---|
| All sensors above stream from Python | read live, values plausible (phone flat: z about -0.97 g, pressure about 102.4 kPa) |
| Phone -> broker -> dashboard over Tailscale | works continuously; data lands within about a second |
| Broker refuses anonymous or wrong logins | checked with a deliberately wrong login (CONNACK 5) |
| Everything restarts after a reboot + re-jailbreak with no manual step | verified once (launchd jobs came up, ~3 min of data gap, no history lost) |
| Sound level | works; **not yet verified to survive a reboot** (the program keeps publishing the rest if the mic is unavailable) |
| Power-loss recovery | **not automatic.** The phone is semi-tethered; see [`docs/POWER_LOSS.md`](docs/POWER_LOSS.md). The hardware part is untested. |
| Other phones / iOS versions | not tested. The HID usage numbers are specific to what this phone reported. |

## Requirements

* A jailbroken phone you can SSH into, with `python3` from the Procursus repo (`apt install python3`).
* Tailscale running on the phone in userspace mode with a SOCKS5 proxy on `localhost:1055`
  (see ios12-tailscale; the daemon flag is `--socks5-server=localhost:1055`).
* A server on your tailnet with Mosquitto and Python 3 (any recent Linux with systemd).

## Quick start

1. **Broker** (on the server): `sudo apt install mosquitto mosquitto-clients`, then
   `sudo TSIP=<server tailnet IP> bash broker/setup-broker.sh`. It requires logins, listens on that address and
   localhost only, and creates two users, `iphone6` (may only publish under `sensors/iphone6/`) and `homelab`
   (read-only). You choose both passwords.
2. **Phone files**: copy `phone/*` to `/var/root/sensors/` on the phone. Copy `config.example.json` to `config.json`
   and set `host` to the broker's tailnet IP.
3. **Phone password**: `ssh -t root@<phone> /var/root/sensors/set_mqtt_password.sh` (you type it; it is stored in a
   root-only file and never printed).
4. **Try it**: `python3 /var/root/sensors/sensor_mqtt.py --once` should print `connected to broker` and one reading.
5. **Dashboard** (on the server): copy `hub/sensor_hub.py` and `hub/dashboard.html` to `~/sensor-hub/`, save the
   `homelab` login for `mosquitto_sub` in `~/.config/mosquitto_sub` (options file with `-h 127.0.0.1`, `-u homelab`,
   `-P ...`, mode 600), then `sudo TSIP=<server tailnet IP> RUNUSER=<you> bash hub/install-hub.sh`.
   Open `http://<server tailnet IP>:8088`.
6. **Start at boot**: install `phone/com.local.sensors.plist` into `/Library/LaunchDaemons/` and add a memory-limit
   entry for its label to Apple's jetsam table (otherwise iOS kills the job at about 6 MB; Python needs about 10 MB).
   `scripts/jetsam_patch.py` in ios12-tailscale does this: `--label com.local.sensors --mb 100`. It edits an Apple
   system file; read that repo's notes first. Needs a reboot, then re-jailbreak.
7. **Sound level (optional)**: see [`docs/MIC_SETUP.md`](docs/MIC_SETUP.md). It needs a deliberate privacy exception.

## Message format

`sensors/iphone6/state` once a second (JSON), plus a retained `sensors/iphone6/status` of `online` / `offline`
(the broker sets `offline` itself if the phone drops):

```json
{"t": 1792944431.3, "accel_g": [0.27, -0.02, -0.97], "accel_peak_g": 1.008, "accel_rms_dev_g": 0.0013,
 "accel_samples": 11, "gyro": [-3.4, -2.0, -1.1], "mag": [149, 201, -609], "als": [11, 24, 2],
 "pressure_kpa": 102.44, "temp_c": {"gas gauge battery": 38.8, "Max: TCC Temp Sensor2": 66.4},
 "power": {"Charger vbat_V": 4.24, "Charger vbus_V": 4.7, "Charger ibat_A": 1.2},
 "sound": {"rms_dbfs": -44.7, "peak_dbfs": -30.0}}
```

## Security and privacy notes

* The dashboard is **read-only and has no login**. Bind it to localhost or your tailnet address only
  (the installer refuses to run without an explicit address). Anyone on your tailnet who can reach port 8088 can see
  the readings, including a sound level and acceleration that can reveal activity in the room.
* The broker is authenticated and per-user restricted. Use long passwords.
* The microphone exception is narrow (one private copy of Python) and the program only ever computes a loudness number.
  Still: it is a microphone in your room. Know where the phone is.
* Change the default `alpine` passwords on the phone, and prefer key-only SSH.

## Repository layout

```
phone/    sensor program, HID discovery tools, mic probes, launchd job, config example
hub/      sensor_hub.py (MQTT -> SQLite + API), dashboard.html, systemd installer
broker/   Mosquitto setup script
docs/     SENSORS.md (how the sensors were found), MIC_SETUP.md, POWER_LOSS.md
```

## License

MIT, see `LICENSE`.
