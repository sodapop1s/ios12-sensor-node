# How the sensors were found and read (iPhone 6, iOS 12.0.1)

None of this is documented by Apple; it is what this one phone did. Treat the numbers as observations.

## Method
The phone's HID event system (`IOHIDEventSystemClient` in IOKit, a private API) lists every sensor as a *service*.
From Python/`ctypes` (`phone/hid_probe.py`):

1. `IOHIDEventSystemClientCreate`, then `IOHIDEventSystemClientCopyServices`: **93 services** on this phone.
2. Read each service's `Product`, `PrimaryUsagePage` and `PrimaryUsage`.
3. `IOHIDServiceClientCopyEvent(service, type, 0, 0)` returns a cached value for always-on sensors (the light sensor,
   temperatures, power rails answered this way).
4. Motion and pressure sensors only report when **subscribed**: set the `ReportInterval` and `BatchInterval` service
   properties (microseconds), register `IOHIDEventSystemClientRegisterEventCallback`, schedule the client on a
   run loop (`phone/hid_stream.py` does this and prints what arrives).

This worked from a root Python on a jailbroken phone with no extra entitlements.

## What was observed
| Service (page / usage) | Event type | Values seen |
|---|---|---|
| 0xFF00 / 3 | 13 (accelerometer) | x, y, z in g; about (0.27, -0.02, -0.97) lying flat |
| 0xFF00 / 9 | 20 (gyro) | x, y, z; small noise around 0 when still (units not verified) |
| 0xFF00 / 10 | 21 (compass) | about (149, 201, -609) (units not verified) |
| 0xFF00 / 4 | 12 (ambient light) | three raw channels; first is roughly the brightness |
| 0x20 / 49 | 31 (pressure) | field 0 about 102.4 (looks like kPa); field 1 counts up (probably a timestamp) |
| 0xFF00 / 5 (named, e.g. "gas gauge battery") | 15 (temperature) | degrees C |
| 0xFF08 / 2 and 3 (named "Charger ...", "PMU ...") | 25 (power) | usage 3 looks like volts, usage 2 like amps; `*_accum` are running totals |

Accelerometer and barometer do **not** appear as ordinary IOKit hardware services (`ioreg` shows only temperature and
light sensors); they come through the HID event system. Other iPhones will have different numbering: run
`hid_probe.py` and `hid_stream.py` and adapt the `WANT` table in `sensor_mqtt.py`.

## Things not verified
* Physical units for the gyro, magnetometer and the "amps" power values.
* Whether the barometer's second field is a timestamp.
* Sampling rate accuracy (it was set to 10 Hz and about 10 events per second arrived per sensor).
