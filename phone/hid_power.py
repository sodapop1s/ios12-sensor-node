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


client = io.IOHIDEventSystemClientCreate(None)
arr = io.IOHIDEventSystemClientCopyServices(client)
n = cf.CFArrayGetCount(arr)
for i in range(n):
    svc = cf.CFArrayGetValueAtIndex(arr, i)
    name = prop(svc, "Product") or ""
    if not (name.startswith("Charger") or "gas gauge" in name or name in ("PMU vbus", "PMU ich_avg", "PMU tbat", "PMU vcc_main")): continue
    hits = []
    for t in range(0, 45):
        ev = io.IOHIDServiceClientCopyEvent(svc, t, 0, 0)
        if ev:
            vals = [round(io.IOHIDEventGetFloatValue(ev, (t << 16) | f), 4) for f in range(0, 5)]
            hits.append(f"type{t}={vals}")
            cf.CFRelease(ev)
    print(f"[{i}] {name!r} page={prop(svc,'PrimaryUsagePage')} u={prop(svc,'PrimaryUsage')}", " ".join(hits) if hits else "(nothing)")
