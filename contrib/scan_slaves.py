#!/usr/bin/env python3
"""Read-only scan of Modbus slave addresses, timing every one.

Reads the identification register (11) from each unit id over one Modbus TCP
connection and reports who answered, who returned an exception (nobody home)
and who stayed silent, with the time each took.

Usage:  python scan_slaves.py [host] [first] [last] [port]
        python scan_slaves.py 172.16.29.51 1 247
"""

import socket
import struct
import sys
import time

host = sys.argv[1] if len(sys.argv) > 1 else "172.16.29.51"
first = int(sys.argv[2]) if len(sys.argv) > 2 else 1
last = int(sys.argv[3]) if len(sys.argv) > 3 else 247
port = int(sys.argv[4]) if len(sys.argv) > 4 else 502
REPLY_WAIT = 10.0  # generous: a healthy gateway answers within about a second


def recv_exact(sock, count, deadline):
    buf = b""
    while len(buf) < count:
        sock.settimeout(max(0.01, deadline - time.time()))
        chunk = sock.recv(count - len(buf))
        if not chunk:
            raise ConnectionError("gateway closed the connection")
        buf += chunk
    return buf


def read_reply(sock, tid, deadline):
    """Return the PDU of the reply with this transaction id, skipping stale ones."""
    while True:
        header = recv_exact(sock, 7, deadline)
        got_tid, _, length, _ = struct.unpack(">HHHB", header)
        pdu = recv_exact(sock, length - 1, deadline)
        if got_tid == tid:
            return pdu


sock = socket.create_connection((host, port), timeout=3)
time.sleep(0.3)
results = []  # (unit, kind, detail, seconds)
started = time.time()
try:
    for unit in range(first, last + 1):
        began = time.time()
        sock.sendall(struct.pack(">HHHBBHH", unit, 0, 6, unit, 3, 11, 1))
        try:
            pdu = read_reply(sock, unit, began + REPLY_WAIT)
        except socket.timeout:
            kind, detail = "silent", "no reply in %d s" % REPLY_WAIT
        else:
            if pdu[0] == 3:
                kind, detail = "meter", "id %d" % struct.unpack(">H", pdu[2:4])[0]
            else:
                kind, detail = "empty", "exception 0x%02x" % pdu[1]
        took = time.time() - began
        results.append((unit, kind, detail, took))
        print("%3d  %-6s %-22s %6.0f ms" % (unit, kind, detail, took * 1000), flush=True)
finally:
    sock.close()

total = time.time() - started
meters = [r for r in results if r[1] == "meter"]
empty = [r for r in results if r[1] == "empty"]
silent = [r for r in results if r[1] == "silent"]


def average(rows):
    return sum(r[3] for r in rows) / len(rows) * 1000 if rows else 0.0


print()
print("scanned %d addresses (%d-%d) in %.1f s" % (len(results), first, last, total))
print("  meters answering : %3d  (avg %.0f ms)  units %s" % (
    len(meters), average(meters), [r[0] for r in meters]))
print("  exception replies: %3d  (avg %.0f ms)" % (len(empty), average(empty)))
print("  no reply         : %3d  (avg %.0f ms)" % (len(silent), average(silent)))
slowest = sorted(results, key=lambda r: -r[3])[:5]
print("  slowest          :", ", ".join("%d (%.0f ms)" % (r[0], r[3] * 1000) for r in slowest))
