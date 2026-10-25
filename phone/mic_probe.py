#!/usr/bin/env python3
"""Does AudioQueue input work from a root Python on this phone? Reports sound LEVEL only; audio is not saved or sent."""
import ctypes as C, math, struct, sys, time
at = C.CDLL("/System/Library/Frameworks/AudioToolbox.framework/AudioToolbox")
vp = C.c_void_p

class ASBD(C.Structure):
    _fields_ = [("mSampleRate", C.c_double), ("mFormatID", C.c_uint32), ("mFormatFlags", C.c_uint32),
                ("mBytesPerPacket", C.c_uint32), ("mFramesPerPacket", C.c_uint32), ("mBytesPerFrame", C.c_uint32),
                ("mChannelsPerFrame", C.c_uint32), ("mBitsPerChannel", C.c_uint32), ("mReserved", C.c_uint32)]
class AQBuf(C.Structure):
    _fields_ = [("mAudioDataBytesCapacity", C.c_uint32), ("mAudioData", vp), ("mAudioDataByteSize", C.c_uint32),
                ("mUserData", vp), ("mPacketDescriptionCapacity", C.c_uint32), ("mPacketDescriptions", vp),
                ("mPacketDescriptionCount", C.c_uint32)]
CB = C.CFUNCTYPE(None, vp, vp, C.POINTER(AQBuf), vp, C.c_uint32, vp)
at.AudioQueueNewInput.argtypes = [C.POINTER(ASBD), CB, vp, vp, vp, C.c_uint32, C.POINTER(vp)]
at.AudioQueueNewInput.restype = C.c_int32
at.AudioQueueAllocateBuffer.argtypes = [vp, C.c_uint32, C.POINTER(C.POINTER(AQBuf))]
at.AudioQueueEnqueueBuffer.argtypes = [vp, C.POINTER(AQBuf), C.c_uint32, vp]
at.AudioQueueStart.argtypes = [vp, vp]
at.AudioQueueStop.argtypes = [vp, C.c_bool]

fmt = ASBD(16000.0, 0x6C70636D, 12, 2, 1, 2, 1, 16, 0)   # 16 kHz mono signed 16-bit PCM
stats = {"buffers": 0, "frames": 0, "rms": 0.0, "peak": 0}
def cb(user, q, buf, ts, npk, descs):
    b = buf.contents
    n = b.mAudioDataByteSize // 2
    if n:
        data = C.string_at(b.mAudioData, n * 2)
        s = struct.unpack("<%dh" % n, data)
        stats["rms"] = math.sqrt(sum(x * x for x in s) / n) / 32768.0
        stats["peak"] = max(abs(x) for x in s) / 32768.0
        stats["frames"] += n
    stats["buffers"] += 1
    at.AudioQueueEnqueueBuffer(q, buf, 0, None)
cbf = CB(cb)
q = vp()
st = at.AudioQueueNewInput(C.byref(fmt), cbf, None, None, None, 0, C.byref(q))
print("AudioQueueNewInput status:", st, "(0 = ok)")
if st: sys.exit(1)
for _ in range(3):
    b = C.POINTER(AQBuf)()
    print("AllocateBuffer:", at.AudioQueueAllocateBuffer(q, 3200, C.byref(b)))
    at.AudioQueueEnqueueBuffer(q, b, 0, None)
print("AudioQueueStart status:", at.AudioQueueStart(q, None))
for i in range(6):
    time.sleep(0.5)
    print(f"  t={0.5*(i+1):.1f}s buffers={stats['buffers']} frames={stats['frames']} rms={stats['rms']:.5f} peak={stats['peak']:.5f}", flush=True)
at.AudioQueueStop(q, True)
