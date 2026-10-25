#!/usr/bin/env python3
"""List the HID sensor services iOS exposes and try to read one value from each.
Runs on the phone (Python 3.9 from Procursus) via ctypes. Read-only."""
import ctypes as C

cf = C.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
io = C.CDLL("/System/Library/Frameworks/IOKit.framework/IOKit")
vp = C.c_void_p
cf.CFStringCreateWithCString.restype = vp; cf.CFStringCreateWithCString.argtypes = [vp, C.c_char_p, C.c_uint32]
cf.CFArrayGetCount.restype = C.c_long; cf.CFArrayGetCount.argtypes = [vp]
cf.CFArrayGetValueAtIndex.restype = vp; cf.CFArrayGetValueAtIndex.argtypes = [vp, C.c_long]
cf.CFGetTypeID.restype = C.c_ulong; cf.CFGetTypeID.argtypes = [vp]
cf.CFStringGetTypeID.restype = C.c_ulong; cf.CFNumberGetTypeID.restype = C.c_ulong
cf.CFStringGetCString.restype = C.c_bool; cf.CFStringGetCString.argtypes = [vp, C.c_char_p, C.c_long, C.c_uint32]
cf.CFNumberGetValue.restype = C.c_bool; cf.CFNumberGetValue.argtypes = [vp, C.c_int, vp]
cf.CFRelease.argtypes = [vp]
io.IOHIDEventSystemClientCreate.restype = vp; io.IOHIDEventSystemClientCreate.argtypes = [vp]
io.IOHIDEventSystemClientCopyServices.restype = vp; io.IOHIDEventSystemClientCopyServices.argtypes = [vp]
io.IOHIDServiceClientCopyProperty.restype = vp; io.IOHIDServiceClientCopyProperty.argtypes = [vp, vp]
io.IOHIDServiceClientCopyEvent.restype = vp; io.IOHIDServiceClientCopyEvent.argtypes = [vp, C.c_int64, C.c_int32, C.c_int64]
io.IOHIDEventGetFloatValue.restype = C.c_double; io.IOHIDEventGetFloatValue.argtypes = [vp, C.c_int32]

UTF8 = 0x08000100
def S(s): return cf.CFStringCreateWithCString(None, s.encode(), UTF8)

def prop(svc, key):
    v = io.IOHIDServiceClientCopyProperty(svc, S(key))
    if not v: return None
    t = cf.CFGetTypeID(v)
    if t == cf.CFStringGetTypeID():
        buf = C.create_string_buffer(256); cf.CFStringGetCString(v, buf, 256, UTF8); return buf.value.decode(errors="replace")
    if t == cf.CFNumberGetTypeID():
        n = C.c_int64(); cf.CFNumberGetValue(v, 4, C.byref(n)); return n.value   # kCFNumberSInt64Type
    return "<other>"


cf.CFNumberCreate.restype = vp; cf.CFNumberCreate.argtypes = [vp, C.c_int, vp]
cf.CFRunLoopGetCurrent.restype = vp
cf.CFRunLoopRunInMode.restype = C.c_int; cf.CFRunLoopRunInMode.argtypes = [vp, C.c_double, C.c_bool]
io.IOHIDServiceClientSetProperty.restype = C.c_bool; io.IOHIDServiceClientSetProperty.argtypes = [vp, vp, vp]
io.IOHIDEventGetType.restype = C.c_int32; io.IOHIDEventGetType.argtypes = [vp]
io.IOHIDEventSystemClientScheduleWithRunLoop.argtypes = [vp, vp, vp]
CB = C.CFUNCTYPE(None, vp, vp, vp, vp)
io.IOHIDEventSystemClientRegisterEventCallback.argtypes = [vp, CB, vp, vp]
mode = vp.in_dll(cf, "kCFRunLoopDefaultMode")

import json, math, os, socket, struct, sys, time

CFG_PATH = os.environ.get("SENSOR_CONFIG", "/var/root/sensors/config.json")
cfg = {"host": None, "port": 1883, "user": "iphone6", "password_file": "/var/root/sensors/mqtt.pass",
       "topic": "sensors/iphone6", "client_id": "iphone6-sensors", "interval": 1.0, "proxy_host": "127.0.0.1", "proxy_port": 1055, "sample_hz": 10}
if os.path.exists(CFG_PATH):
    cfg.update(json.load(open(CFG_PATH)))
if not cfg["host"]:
    sys.exit("set \"host\" (the broker's IP) in %s - see config.example.json" % CFG_PATH)

def log(*a): print(time.strftime("%H:%M:%S"), *a, flush=True)

# ---------------------------------------------------------------- tiny MQTT 3.1.1 client over SOCKS5
def _str(b): return struct.pack(">H", len(b)) + b
def _remlen(n):
    out = b""
    while True:
        d, n = n % 128, n // 128
        out += bytes([d | (128 if n else 0)])
        if not n: return out

class Mqtt:
    def __init__(self):
        self.sock = None; self.last_tx = 0.0
    def connect(self):
        pw = open(cfg["password_file"]).read().strip()
        s = socket.create_connection((cfg["proxy_host"], cfg["proxy_port"]), timeout=10)
        s.sendall(b"\x05\x01\x00")
        if s.recv(2) != b"\x05\x00": raise OSError("socks5 greeting refused")
        s.sendall(b"\x05\x01\x00\x01" + socket.inet_aton(cfg["host"]) + struct.pack(">H", cfg["port"]))
        rep = s.recv(10)
        if len(rep) < 2 or rep[1] != 0: raise OSError("proxy could not reach broker (code %s)" % (rep[1] if len(rep) > 1 else "?"))
        will_topic = (cfg["topic"] + "/status").encode()
        var = _str(b"MQTT") + b"\x04" + bytes([0xE6]) + struct.pack(">H", 30)   # user, pass, will(retain), clean session, keepalive 30
        payload = _str(cfg["client_id"].encode()) + _str(will_topic) + _str(b"offline") + _str(cfg["user"].encode()) + _str(pw.encode())
        s.sendall(b"\x10" + _remlen(len(var) + len(payload)) + var + payload)
        ack = s.recv(4)
        if len(ack) != 4 or ack[0] != 0x20 or ack[3] != 0:
            raise OSError("broker refused login (CONNACK %s)" % ack.hex())
        s.settimeout(10); self.sock = s; self.last_tx = time.time()
        self.publish(cfg["topic"] + "/status", b"online", retain=True)
    def publish(self, topic, payload, retain=False):
        body = _str(topic.encode()) + payload
        self.sock.sendall(bytes([0x30 | (1 if retain else 0)]) + _remlen(len(body)) + body)
        self.last_tx = time.time()
    def ping_if_idle(self):
        if self.sock and time.time() - self.last_tx > 15:
            self.sock.sendall(b"\xC0\x00"); self.last_tx = time.time()
            self.sock.settimeout(0.01)
            try: self.sock.recv(16)          # discard PINGRESP
            except OSError: pass
            self.sock.settimeout(10)
    def close(self):
        try: self.sock.close()
        except Exception: pass
        self.sock = None

# ---------------------------------------------------------------- sensors
client = io.IOHIDEventSystemClientCreate(None)
arr = io.IOHIDEventSystemClientCopyServices(client)
n = cf.CFArrayGetCount(arr)
SENSORS = {}      # service ptr -> name, found by (usage page, usage) as seen on iPhone 6 / iOS 12.0.1
WANT = {(65280, 3): "accel", (65280, 9): "gyro", (65280, 11): "mag_unused", (65280, 4): "als", (32, 49): "pressure", (65280, 10): "mag"}
temps = {}        # label -> service ptr
power = {}        # label -> service ptr  (charger / power-management rails; usage 3 = volts, 2 = amps)
POWER_NAMES = {"Charger vbus", "Charger vbat", "Charger vdd_main", "Charger ibat", "Charger ibus_accum",
               "Charger vbus_accum", "PMU vcc_main", "PMU vbus"}
for i in range(n):
    svc = cf.CFArrayGetValueAtIndex(arr, i)
    key = (prop(svc, "PrimaryUsagePage"), prop(svc, "PrimaryUsage"))
    name = prop(svc, "Product")
    if key in WANT and not name:
        SENSORS[svc] = WANT[key]
        num = C.c_int64(int(1e6 / cfg["sample_hz"]))
        for k in ("ReportInterval", "BatchInterval"):
            io.IOHIDServiceClientSetProperty(svc, S(k), cf.CFNumberCreate(None, 4, C.byref(num)))
    if name in ("gas gauge battery", "Max: PMGR SOC Die Temp Sensor0", "Max: TCC Temp Sensor2", "Charger tjunc"):
        temps[name] = svc
    if name in POWER_NAMES and key[0] == 65288:
        power[name + ("_A" if key[1] == 2 else "_V")] = svc
log("sensor services:", sorted(set(SENSORS.values())), "| temps:", sorted(temps), "| power:", len(power))

latest, acc = {}, []
def cb(target, refcon, sender, event):
    try:
        name = SENSORS.get(sender)
        if not name: return
        t = io.IOHIDEventGetType(event)
        v = [io.IOHIDEventGetFloatValue(event, (t << 16) | f) for f in range(3)]
        if name == "accel": acc.append(v); latest["accel"] = v
        elif name == "gyro": latest["gyro"] = v
        elif name == "mag": latest["mag"] = v
        elif name == "als": latest["als"] = v
        elif name == "pressure": latest["pressure_kpa"] = v[0]
    except Exception:
        pass
cbf = CB(cb)
io.IOHIDEventSystemClientRegisterEventCallback(client, cbf, None, None)
io.IOHIDEventSystemClientScheduleWithRunLoop(client, cf.CFRunLoopGetCurrent(), mode)

def snapshot():
    out = {"t": round(time.time(), 3)}
    r = lambda v: [round(x, 4) for x in v]
    if "accel" in latest: out["accel_g"] = r(latest["accel"])
    if acc:
        mags = [math.sqrt(a * a + b * b + c * c) for a, b, c in acc]
        mean = sum(mags) / len(mags)
        out["accel_peak_g"] = round(max(mags), 4)
        out["accel_rms_dev_g"] = round(math.sqrt(sum((m - mean) ** 2 for m in mags) / len(mags)), 5)
        out["accel_samples"] = len(acc)
    for k in ("gyro", "mag", "als"):
        if k in latest: out[k] = r(latest[k])
    if "pressure_kpa" in latest: out["pressure_kpa"] = round(latest["pressure_kpa"], 4)
    tt = {}
    for label, svc in temps.items():
        ev = io.IOHIDServiceClientCopyEvent(svc, 15, 0, 0)
        if ev: tt[label] = round(io.IOHIDEventGetFloatValue(ev, 15 << 16), 2); cf.CFRelease(ev)
    if tt: out["temp_c"] = tt
    pw = {}
    for label, svc in power.items():
        ev = io.IOHIDServiceClientCopyEvent(svc, 25, 0, 0)
        if ev: pw[label] = round(io.IOHIDEventGetFloatValue(ev, 25 << 16), 4); cf.CFRelease(ev)
    if pw: out["power"] = pw
    sl = sound_level()
    if sl: out["sound"] = sl
    return out


# ---------------------------------------------------------------- microphone: LEVEL ONLY (audio is discarded on the spot)
# Needs a Python signed with the kTCCServiceMicrophone entitlement (see MIC_SETUP.md); without it this stays off.
mic = {"sumsq": 0.0, "n": 0, "peak": 0, "ok": False, "err": None}
_mic_keep = []
def start_mic():
    try:
        try: import audioop
        except ImportError: audioop = None
        objc = C.CDLL("/usr/lib/libobjc.A.dylib"); C.CDLL("/System/Library/Frameworks/Foundation.framework/Foundation")
        avf = C.CDLL("/System/Library/Frameworks/AVFoundation.framework/AVFoundation")
        at = C.CDLL("/System/Library/Frameworks/AudioToolbox.framework/AudioToolbox")
        objc.objc_getClass.restype = vp; objc.objc_getClass.argtypes = [C.c_char_p]
        objc.sel_registerName.restype = vp; objc.sel_registerName.argtypes = [C.c_char_p]
        def msg(rt, at_): return C.CFUNCTYPE(rt, vp, vp, *at_)(("objc_msgSend", objc))
        sel = lambda s: objc.sel_registerName(s.encode())
        shared = msg(vp, [])(objc.objc_getClass(b"AVAudioSession"), sel("sharedInstance"))
        err = vp(); msg(C.c_bool, [vp, C.POINTER(vp)])(shared, sel("setCategory:error:"), vp.in_dll(avf, "AVAudioSessionCategoryRecord"), C.byref(err))
        err = vp(); ok = msg(C.c_bool, [C.c_bool, C.POINTER(vp)])(shared, sel("setActive:error:"), True, C.byref(err))
        perm = msg(C.c_int, [])(shared, sel("recordPermission")).to_bytes(4, "big").decode(errors="replace") if True else ""
        if perm != "grnt": raise RuntimeError("microphone permission is '%s' (needs the mic-entitled python)" % perm)
        class ASBD(C.Structure):
            _fields_ = [("r", C.c_double), ("fid", C.c_uint32), ("ff", C.c_uint32), ("bpp", C.c_uint32), ("fpp", C.c_uint32),
                        ("bpf", C.c_uint32), ("ch", C.c_uint32), ("bits", C.c_uint32), ("res", C.c_uint32)]
        class AQBuf(C.Structure):
            _fields_ = [("cap", C.c_uint32), ("data", vp), ("size", C.c_uint32), ("user", vp), ("pdc", C.c_uint32), ("pd", vp), ("pdn", C.c_uint32)]
        CBT = C.CFUNCTYPE(None, vp, vp, C.POINTER(AQBuf), vp, C.c_uint32, vp)
        at.AudioQueueNewInput.argtypes = [C.POINTER(ASBD), CBT, vp, vp, vp, C.c_uint32, C.POINTER(vp)]
        at.AudioQueueAllocateBuffer.argtypes = [vp, C.c_uint32, C.POINTER(C.POINTER(AQBuf))]
        at.AudioQueueEnqueueBuffer.argtypes = [vp, C.POINTER(AQBuf), C.c_uint32, vp]
        at.AudioQueueStart.argtypes = [vp, vp]
        def mic_cb(user, q, buf, ts, npk, descs):
            try:
                b = buf.contents; nbytes = b.size - (b.size % 2)
                if nbytes:
                    raw = C.string_at(b.data, nbytes); n = nbytes // 2
                    if audioop: r, m = audioop.rms(raw, 2), audioop.max(raw, 2)
                    else:
                        s = struct.unpack("<%dh" % n, raw); r = math.sqrt(sum(x * x for x in s) / n); m = max(abs(x) for x in s)
                    mic["sumsq"] += r * r * n; mic["n"] += n; mic["peak"] = max(mic["peak"], m)
                    # the raw bytes go out of scope here: nothing is stored, logged or sent
            except Exception: pass
            at.AudioQueueEnqueueBuffer(q, buf, 0, None)
        cbm = CBT(mic_cb); q = vp()
        fmt = ASBD(16000.0, 0x6C70636D, 12, 2, 1, 2, 1, 16, 0)
        st = at.AudioQueueNewInput(C.byref(fmt), cbm, None, None, None, 0, C.byref(q))
        if st: raise RuntimeError("AudioQueueNewInput status %d" % st)
        for _ in range(3):
            bf = C.POINTER(AQBuf)(); at.AudioQueueAllocateBuffer(q, 3200, C.byref(bf)); at.AudioQueueEnqueueBuffer(q, bf, 0, None)
        st = at.AudioQueueStart(q, None)
        if st: raise RuntimeError("AudioQueueStart status %d" % st)
        _mic_keep.extend([cbm, q]); mic["ok"] = True
    except Exception as e:
        mic["err"] = str(e)
if cfg.get("mic", True): start_mic()
log("microphone level:", "ON" if mic["ok"] else "off (%s)" % mic["err"])

def sound_level():
    if not mic["ok"] or mic["n"] == 0: return None
    rms = math.sqrt(mic["sumsq"] / mic["n"]) / 32768.0; peak = mic["peak"] / 32768.0
    mic["sumsq"], mic["n"], mic["peak"] = 0.0, 0, 0
    db = lambda v: round(20 * math.log10(max(v, 1e-6)), 1)
    return {"rms_dbfs": db(rms), "peak_dbfs": db(peak)}

# ---------------------------------------------------------------- main loop
mq, next_pub, backoff = Mqtt(), time.time() + cfg["interval"], 2
once = "--once" in sys.argv
log("publishing to %s:%s as %s every %ss" % (cfg["host"], cfg["port"], cfg["user"], cfg["interval"]))
while True:
    cf.CFRunLoopRunInMode(mode, 0.1, False)
    now = time.time()
    if now < next_pub: continue
    next_pub = now + cfg["interval"]
    snap = snapshot(); acc.clear()
    try:
        if mq.sock is None:
            mq.connect(); log("connected to broker"); backoff = 2
        mq.publish(cfg["topic"] + "/state", json.dumps(snap, separators=(",", ":")).encode())
        mq.ping_if_idle()
        if once: log("published:", json.dumps(snap)); break
    except Exception as e:
        log("mqtt error:", e, "- retrying in", backoff, "s")
        mq.close(); next_pub = time.time() + backoff; backoff = min(backoff * 2, 60)
        if once: break
