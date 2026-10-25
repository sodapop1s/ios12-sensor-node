#!/bin/sh
# Run this ON THE PHONE (ssh -t). Stores the phone's MQTT password in a root-only file. You type it; nothing is echoed.
mkdir -p /var/root/sensors && chmod 700 /var/root/sensors
printf "MQTT password for user 'iphone6' (the one you set on the broker): "
stty -echo; read PW; stty echo; echo
printf '%s\n' "$PW" > /var/root/sensors/mqtt.pass && chmod 600 /var/root/sensors/mqtt.pass
echo "saved to /var/root/sensors/mqtt.pass ($(wc -c < /var/root/sensors/mqtt.pass) bytes, mode 600)"
