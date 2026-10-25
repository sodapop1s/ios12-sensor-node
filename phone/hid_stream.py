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

import sys
SECS = float(sys.argv[1]) if len(sys.argv) > 1 else 6.0
INTERVAL_US = 100000   # 10 Hz

client = io.IOHIDEventSystemClientCreate(None)
arr = io.IOHIDEventSystemClientCopyServices(client)
n = cf.CFArrayGetCount(arr)
CAND = {8: "page32/u49 (pressure?)", 11: "ff00/u11 (magnetometer?)", 23: "ff00/u3 (accelerometer?)",
        63: "ff00/u10", 52: "ff00/u14", 76: "ff00/u9 (gyro?)", 64: "ff00/u4 (ALS)"}
svcs = {}
for i in range(n):
    svc = cf.CFArrayGetValueAtIndex(arr, i)
    if i in CAND:
        svcs[svc] = i
        num = C.c_int64(INTERVAL_US)
        for key in ("ReportInterval", "BatchInterval"):
            ok = io.IOHIDServiceClientSetProperty(svc, S(key), cf.CFNumberCreate(None, 4, C.byref(num)))
            print(f"[{i}] {CAND[i]}: set {key} -> {ok}")

counts, shown = {}, {}
def cb(target, refcon, sender, event):
    t = io.IOHIDEventGetType(event)
    idx = svcs.get(sender, "?")
    key = (idx, t)
    counts[key] = counts.get(key, 0) + 1
    if shown.get(key, 0) < 3:
        shown[key] = shown.get(key, 0) + 1
        vals = [round(io.IOHIDEventGetFloatValue(event, (t << 16) | f), 4) for f in range(0, 4)]
        print(f"  event from service [{idx}] type {t}: {vals}", flush=True)
cbf = CB(cb)
io.IOHIDEventSystemClientRegisterEventCallback(client, cbf, None, None)
io.IOHIDEventSystemClientScheduleWithRunLoop(client, cf.CFRunLoopGetCurrent(), mode)
print(f"listening for {SECS}s ...", flush=True)
cf.CFRunLoopRunInMode(mode, SECS, False)
print("event counts (service, type): count ->", counts if counts else "none")
