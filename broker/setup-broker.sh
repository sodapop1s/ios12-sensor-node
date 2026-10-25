#!/bin/bash
# Configure Mosquitto as a private sensor broker: tailnet + localhost only, login required, per-user topic rights.
# Usage:  sudo TSIP=<the server's tailnet IP> bash setup-broker.sh      (asks you to choose two passwords)
set -e
: "${TSIP:?set TSIP to the address the broker should listen on (tailnet/LAN IP)}"

install -d -m 755 /etc/mosquitto/conf.d
cat > /etc/mosquitto/conf.d/sensors.conf <<EOF
# Private sensor broker: reachable on localhost and the Tailscale address only.
listener 1883 127.0.0.1
listener 1883 $TSIP
allow_anonymous false
password_file /etc/mosquitto/passwd
acl_file /etc/mosquitto/acl
EOF

cat > /etc/mosquitto/acl <<'EOF'
# the phone may only publish under sensors/iphone6/
user iphone6
topic write sensors/iphone6/#

# the homelab reader may only read sensor topics
user homelab
topic read sensors/#
EOF

# start after Tailscale so the tailnet address exists; retry if it does not yet
install -d /etc/systemd/system/mosquitto.service.d
cat > /etc/systemd/system/mosquitto.service.d/override.conf <<'EOF'
[Unit]
After=network-online.target tailscaled.service
Wants=tailscaled.service
[Service]
Restart=on-failure
RestartSec=5
EOF

echo
echo "== Choose a password for the PHONE's MQTT user 'iphone6' (you will type it twice):"
mosquitto_passwd -c /etc/mosquitto/passwd iphone6
echo "== Choose a password for the HOMELAB reader user 'homelab' (twice):"
mosquitto_passwd /etc/mosquitto/passwd homelab
chown mosquitto:mosquitto /etc/mosquitto/passwd /etc/mosquitto/acl
chmod 640 /etc/mosquitto/passwd /etc/mosquitto/acl

systemctl daemon-reload
systemctl restart mosquitto
sleep 2
echo
echo "== service: $(systemctl is-active mosquitto)"
echo "== listening:"; ss -ltn | grep ':1883' || echo "NOT LISTENING - see: journalctl -u mosquitto -n 20"
echo "== users:"; cut -d: -f1 /etc/mosquitto/passwd
