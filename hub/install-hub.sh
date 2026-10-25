#!/bin/bash
# Install the sensor-hub systemd service on the homelab server.
# Usage:  sudo TSIP=<address to listen on, e.g. the server's tailnet IP> RUNUSER=<your user> bash install-hub.sh
# (copy sensor_hub.py and dashboard.html to /home/<RUNUSER>/sensor-hub/ first)
set -e
: "${TSIP:?set TSIP to the address the dashboard should listen on (tailnet/LAN IP, never 0.0.0.0)}"
: "${RUNUSER:?set RUNUSER to the user the service should run as}"
cat > /etc/systemd/system/sensor-hub.service <<EOF
[Unit]
Description=iPhone sensor hub (MQTT -> SQLite + dashboard)
After=network-online.target tailscaled.service mosquitto.service
Wants=tailscaled.service mosquitto.service

[Service]
User=$RUNUSER
Environment=HUB_BIND=$TSIP HUB_PORT=8088 HUB_DB=/home/$RUNUSER/sensor-hub/hub.db HUB_BROKER_HOST=127.0.0.1
ExecStart=/usr/bin/python3 /home/$RUNUSER/sensor-hub/sensor_hub.py
Restart=always
RestartSec=5
# read-only dashboard; keep the process boxed in
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/home/$RUNUSER/sensor-hub
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable sensor-hub
systemctl restart sensor-hub   # restart (not just --now) so a re-run picks up new code and settings
sleep 3
echo "== service: $(systemctl is-active sensor-hub)"
echo "== listening:"; ss -ltn | grep ':8088' || echo "NOT LISTENING (journalctl -u sensor-hub -n 20)"
echo "== local check:"; curl -s http://$TSIP:8088/api/latest | head -c 200; echo
echo "== firewall:"; (command -v ufw >/dev/null && ufw status | head -3) || echo "no ufw"
