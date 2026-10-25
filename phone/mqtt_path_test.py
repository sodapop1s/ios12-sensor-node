#!/usr/bin/env python3
"""Check phone -> Tailscale SOCKS5 proxy -> broker, using a deliberately WRONG login.
Expected: CONNACK return code 5 (not authorized) = the path works and anonymous/bad logins are refused."""
import socket, struct, sys
PROXY = ("127.0.0.1", 1055)
HOST, PORT = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 1883

s = socket.create_connection(PROXY, timeout=10)
s.sendall(b"\x05\x01\x00"); assert s.recv(2) == b"\x05\x00", "SOCKS5 greeting refused"
ip = socket.inet_aton(HOST)
s.sendall(b"\x05\x01\x00\x01" + ip + struct.pack(">H", PORT))
rep = s.recv(10)
print("socks5 connect reply code:", rep[1], "(0 = ok)")
if rep[1] != 0: sys.exit("proxy could not reach the broker")

def S(b): return struct.pack(">H", len(b)) + b
payload = S(b"path-test") + S(b"nobody") + S(b"wrong")          # client id, user, password
var = S(b"MQTT") + b"\x04" + b"\xC2" + struct.pack(">H", 10)     # v3.1.1, clean session, user+pass flags
pkt = b"\x10" + bytes([len(var) + len(payload)]) + var + payload
s.sendall(pkt)
resp = s.recv(4)
print("CONNACK bytes:", resp.hex(), "-> return code", resp[3] if len(resp) == 4 else "?", "(5 = not authorized: EXPECTED)")
