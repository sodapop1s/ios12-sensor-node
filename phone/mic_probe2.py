#!/usr/bin/env python3
"""Activate an AVAudioSession (record category) through the Objective-C runtime, then run the AudioQueue input test."""
import ctypes as C, sys
objc = C.CDLL("/usr/lib/libobjc.A.dylib")
C.CDLL("/System/Library/Frameworks/Foundation.framework/Foundation")
avf = C.CDLL("/System/Library/Frameworks/AVFoundation.framework/AVFoundation")
vp = C.c_void_p
objc.objc_getClass.restype = vp; objc.objc_getClass.argtypes = [C.c_char_p]
objc.sel_registerName.restype = vp; objc.sel_registerName.argtypes = [C.c_char_p]
def msg(restype, argtypes):
    f = C.CFUNCTYPE(restype, vp, vp, *argtypes)(("objc_msgSend", objc)); return f
sel = lambda s: objc.sel_registerName(s.encode())
cls = objc.objc_getClass(b"AVAudioSession")
print("AVAudioSession class:", bool(cls))
shared = msg(vp, [])(cls, sel("sharedInstance"))
cat = vp.in_dll(avf, "AVAudioSessionCategoryRecord")
err = vp()
ok = msg(C.c_bool, [vp, C.POINTER(vp)])(shared, sel("setCategory:error:"), cat, C.byref(err))
print("setCategory(Record):", ok, "error:", bool(err.value))
err = vp()
ok = msg(C.c_bool, [C.c_bool, C.POINTER(vp)])(shared, sel("setActive:error:"), True, C.byref(err))
print("setActive(True):", ok)
if err.value:
    desc = msg(vp, [])(err.value, sel("localizedDescription"))
    s = msg(C.c_char_p, [])(desc, sel("UTF8String"))
    print("  error:", s.decode(errors="replace"))
perm = msg(C.c_int, [])(shared, sel("recordPermission"))   # 'undt'=undetermined 'deny' 'grnt'
print("recordPermission:", perm.to_bytes(4, "big").decode(errors="replace") if perm > 0 else perm, "(grnt = granted, deny = denied, undt = not asked)")
exec(open("/var/root/sensors/mic_probe.py").read())
