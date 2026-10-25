#!/usr/bin/env python3
"""Sensor hub: MQTT -> SQLite collector + small live dashboard (stdlib only).

  python3 sensor_hub.py                       # normal: needs mosquitto_sub with credentials in ~/.config/mosquitto_sub
  python3 sensor_hub.py --demo                # generate fake data instead of MQTT (for testing)
Env: HUB_DB, HUB_BIND (default 127.0.0.1), HUB_PORT (8088), HUB_BROKER_HOST (127.0.0.1), HUB_RETENTION_DAYS (7)
The dashboard is read-only and has no login: bind it to localhost / your tailnet address only.
"""
import json, math, os, random, sqlite3, subprocess, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

DB = os.environ.get("HUB_DB", os.path.expanduser("~/sensor-hub/hub.db"))
BIND = os.environ.get("HUB_BIND", "127.0.0.1")
PORT = int(os.environ.get("HUB_PORT", "8088"))
BROKER = os.environ.get("HUB_BROKER_HOST", "127.0.0.1")
KEEP_DAYS = float(os.environ.get("HUB_RETENTION_DAYS", "7"))
DEMO = "--demo" in sys.argv
lock = threading.Lock()
state = {"status": "unknown", "status_ts": 0.0, "last_state_ts": 0.0}


def db():
    c = sqlite3.connect(DB, timeout=30, check_same_thread=False)
    c.execute("PRAGMA journal_mode=WAL")
    return c


def init_db():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    c = db()
    c.execute("CREATE TABLE IF NOT EXISTS samples (ts REAL NOT NULL, topic TEXT NOT NULL, body TEXT NOT NULL)")
    c.execute("CREATE INDEX IF NOT EXISTS samples_ts ON samples (topic, ts)")
    c.commit(); c.close()


def store(topic, payload):
    now = time.time()
    if topic.endswith("/status"):
        state["status"], state["status_ts"] = payload.strip(), now
        return
    if topic.endswith("/state"):
        try:
            json.loads(payload)
        except ValueError:
            return
        state["last_state_ts"] = now
        with lock:
            c = db(); c.execute("INSERT INTO samples VALUES (?,?,?)", (now, topic, payload)); c.commit(); c.close()


def prune_loop():
    while True:
        time.sleep(3600)
        with lock:
            c = db(); c.execute("DELETE FROM samples WHERE ts < ?", (time.time() - KEEP_DAYS * 86400,)); c.commit(); c.close()


def mqtt_loop():
    """Run mosquitto_sub forever (it reads credentials from ~/.config/mosquitto_sub) and ingest its lines."""
    while True:
        try:
            p = subprocess.Popen(["mosquitto_sub", "-h", BROKER, "-t", "sensors/#", "-v"], stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True, bufsize=1)
            for line in p.stdout:
                topic, _, payload = line.rstrip("\n").partition(" ")
                if payload: store(topic, payload)
            print("mosquitto_sub exited; restarting in 5 s", flush=True)
        except Exception as e:
            print("mqtt loop error:", e, flush=True)
        time.sleep(5)


def demo_loop():
    t0 = time.time()
    while True:
        now = time.time(); x = now - t0
        msg = {"t": now, "accel_g": [0.27, -0.02, -0.97], "accel_peak_g": 1.008, "accel_rms_dev_g": abs(random.gauss(0.0013, 0.0004)),
               "gyro": [-3.4, -2.0, -1.1], "mag": [148, 201, -609], "als": [11 + 8 * math.sin(x / 60), 24, 2],
               "pressure_kpa": 102.44 + 0.01 * math.sin(x / 90),
               "temp_c": {"gas gauge battery": 38.8 + math.sin(x / 120), "Max: TCC Temp Sensor2": 66 + 4 * math.sin(x / 45)},
               "power": {"Charger vbus_V": 4.7, "Charger vbat_V": 4.24, "Charger ibat_A": 1.2}}
        state["status"], state["status_ts"] = "online", now
        store("sensors/iphone6/state", json.dumps(msg)); time.sleep(1)


# ------------------------------------------------------------------ queries
def dig(obj, path):
    """metric path like 'temp_c.gas gauge battery' or 'als.0' -> float or None"""
    cur = obj
    for part in path.split("."):
        if isinstance(cur, list):
            try: cur = cur[int(part)]
            except (ValueError, IndexError): return None
        elif isinstance(cur, dict):
            if part not in cur:
                # allow metric names that themselves contain dots? (none do) -> give up
                return None
            cur = cur[part]
        else:
            return None
    return float(cur) if isinstance(cur, (int, float)) else None


def metric_names():
    with lock:
        c = db(); row = c.execute("SELECT body FROM samples ORDER BY ts DESC LIMIT 1").fetchone(); c.close()
    if not row: return []
    d = json.loads(row[0]); out = []
    def walk(prefix, v):
        if isinstance(v, dict):
            for k, x in v.items(): walk(prefix + [k], x)
        elif isinstance(v, list):
            for i, x in enumerate(v): walk(prefix + [str(i)], x)
        elif isinstance(v, (int, float)) and prefix and prefix[0] not in ("t", "accel_samples"):
            out.append(".".join(prefix))
    walk([], d)
    return out


def series(metric, hours, points):
    since = time.time() - hours * 3600
    with lock:
        c = db(); rows = c.execute("SELECT ts, body FROM samples WHERE ts >= ? ORDER BY ts", (since,)).fetchall(); c.close()
    if not rows: return []
    bucket = max(1.0, hours * 3600 / points); out, cur, acc = [], None, []
    for ts, body in rows:
        v = dig(json.loads(body), metric)
        if v is None: continue
        b = int(ts // bucket)
        if cur is not None and b != cur and acc:
            out.append([round(cur * bucket + bucket / 2, 1), round(sum(acc) / len(acc), 5), round(min(acc), 5), round(max(acc), 5)]); acc = []
        cur = b; acc.append(v)
    if acc: out.append([round(cur * bucket + bucket / 2, 1), round(sum(acc) / len(acc), 5), round(min(acc), 5), round(max(acc), 5)])
    return out


def latest():
    with lock:
        c = db(); row = c.execute("SELECT ts, body FROM samples ORDER BY ts DESC LIMIT 1").fetchone()
        n = c.execute("SELECT COUNT(*) FROM samples").fetchone()[0]; c.close()
    age = (time.time() - row[0]) if row else None
    return {"status": state["status"], "status_age_s": round(time.time() - state["status_ts"], 1) if state["status_ts"] else None,
            "last_sample_age_s": round(age, 1) if age is not None else None, "samples_stored": n,
            "latest": json.loads(row[1]) if row else None}


PAGE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard.html")


def page():
    try:
        return open(PAGE_FILE).read()      # re-read on every request: dashboard tweaks need no restart
    except OSError:
        return "<h1>dashboard.html missing</h1>"


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, ctype, body):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        u = urlparse(self.path); q = parse_qs(u.query)
        try:
            if u.path == "/": return self._send(200, "text/html; charset=utf-8", page())
            if u.path == "/api/latest": return self._send(200, "application/json", json.dumps(latest()))
            if u.path == "/api/metrics": return self._send(200, "application/json", json.dumps(metric_names()))
            if u.path == "/api/series":
                m = q.get("metric", [""])[0]; h = min(float(q.get("hours", ["1"])[0]), KEEP_DAYS * 24)
                pts = min(int(q.get("points", ["300"])[0]), 2000)
                return self._send(200, "application/json", json.dumps(series(m, h, pts)))
            self._send(404, "text/plain", "not found")
        except Exception as e:
            self._send(500, "text/plain", "error: %s" % e)


def main():
    init_db()
    threading.Thread(target=prune_loop, daemon=True).start()
    threading.Thread(target=demo_loop if DEMO else mqtt_loop, daemon=True).start()
    binds = {BIND}
    srv = [ThreadingHTTPServer((b, PORT), H) for b in binds]
    print(f"sensor hub: dashboard on http://{BIND}:{PORT}  db={DB}  {'DEMO DATA' if DEMO else 'mqtt ' + BROKER}", flush=True)
    for s in srv[1:]: threading.Thread(target=s.serve_forever, daemon=True).start()
    srv[0].serve_forever()


if __name__ == "__main__":
    main()
