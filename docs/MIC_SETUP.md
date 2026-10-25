# Microphone: level only, how it works and how to undo it

## What it does
`sensor_mqtt.py` opens a 16 kHz mono input AudioQueue and, once per second, publishes two numbers in the
`sound` field: `rms_dbfs` (average loudness) and `peak_dbfs` (loudest instant), in dB below digital full scale
(0 = maximum). Each audio buffer is measured and dropped immediately: **no audio is stored, logged or sent.**
(Typical quiet room on this phone: about -45 dBFS RMS.)

## The permission, and the one exception that was made
iOS refuses microphone input to a process without microphone permission (`AVAudioSession.recordPermission`
reported `deny`, and no buffers arrived). The exception that was granted, at the owner's explicit request:

* `/var/root/sensors/python-mic` is a **private copy** of `/usr/bin/python3.9`, signed on the phone with
  `ldid -Cadhoc -Hsha1 -Hsha256 -Sents-mic.plist` where `ents-mic.plist` is the usual three entitlements copied from
  `/usr/bin/uname` plus `com.apple.private.tcc.allow = [kTCCServiceMicrophone]`.
* Only that copy has the exception. The system `python3` and everything else are unchanged. The phone's permission
  database (TCC.db) was **not** edited.
* The `com.local.sensors` launch job runs `python-mic`; if the permission is ever missing the sensor program
  logs "microphone level: off (...)" and keeps publishing everything else.

## Undo
```sh
# on the phone
launchctl unload /Library/LaunchDaemons/com.local.sensors.plist
sed -i 's#/var/root/sensors/python-mic#/usr/bin/python3#' /Library/LaunchDaemons/com.local.sensors.plist
rm /var/root/sensors/python-mic /var/root/sensors/ents-mic.plist
launchctl load /Library/LaunchDaemons/com.local.sensors.plist
```
To also stop the sound field cleanly, set `"mic": false` in `/var/root/sensors/config.json`.

## Not yet verified
* That the signed copy still has microphone access **after a reboot + re-jailbreak** (the next reboot test will show it).
