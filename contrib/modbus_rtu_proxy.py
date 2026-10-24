#!/usr/bin/env python
"""Minimal read-only Modbus TCP -> Modbus RTU proxy for a Linux serial port.

Standard library only; runs on Python 2.7 and Python 3. Intended for gateways
whose bundled software caches or stalls (for example Techbase iMod), so that
the Home Assistant integration can talk to the meters through a plain bridge.

* Accepts Modbus TCP on --port and forwards each request to the serial bus.
* Requests are serialised, so several TCP clients can share the RS-485 bus.
* Only read functions (0x01-0x04) are forwarded; anything else is refused with
  an "illegal function" exception so a write can never reach a meter.
* A silent meter is answered at once with exception 0x0B (gateway target failed
  to respond) carrying the request's own unit id.

Usage:
    python modbus_rtu_proxy.py --serial /dev/ttySC0 --baud 9600 --port 502
    python modbus_rtu_proxy.py --serial /dev/ttySC0 --probe 1   # one test read
    python modbus_rtu_proxy.py --serial /dev/ttySC0 --scan      # time every address

--probe and --scan talk to the serial port directly, with no network involved,
so stop the proxy (and any other program using the port) before running them.
"""

from __future__ import print_function

import argparse
import errno
import os
import select
import socket
import struct
import sys
import termios
import threading
import time

READ_FUNCTIONS = (0x01, 0x02, 0x03, 0x04)
EXC_ILLEGAL_FUNCTION = 0x01
EXC_TARGET_FAILED = 0x0B

BAUDS = {
    1200: termios.B1200,
    2400: termios.B2400,
    4800: termios.B4800,
    9600: termios.B9600,
    19200: termios.B19200,
    38400: termios.B38400,
    57600: termios.B57600,
    115200: termios.B115200,
}


def log(message):
    print("%s %s" % (time.strftime("%H:%M:%S"), message))
    sys.stdout.flush()


def crc16(data):
    crc = 0xFFFF
    for byte in bytearray(data):
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


class SerialBus(object):
    """One RTU serial port; use under a lock, one transaction at a time."""

    def __init__(self, path, baud, parity, stop_bits):
        self.fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        attrs = termios.tcgetattr(self.fd)
        cflag = termios.CS8 | termios.CREAD | termios.CLOCAL
        if parity in ("E", "O"):
            cflag |= termios.PARENB
            if parity == "O":
                cflag |= termios.PARODD
        if stop_bits == 2:
            cflag |= termios.CSTOPB
        attrs[0] = 0
        attrs[1] = 0
        attrs[2] = cflag
        attrs[3] = 0
        attrs[4] = attrs[5] = BAUDS[baud]
        attrs[6][termios.VMIN] = 0
        attrs[6][termios.VTIME] = 0
        termios.tcsetattr(self.fd, termios.TCSANOW, attrs)

    def _read(self, count, timeout):
        end = time.time() + timeout
        buf = bytearray()
        while len(buf) < count:
            left = end - time.time()
            if left <= 0:
                break
            ready, _, _ = select.select([self.fd], [], [], left)
            if not ready:
                break
            try:
                chunk = os.read(self.fd, count - len(buf))
            except OSError as err:
                if err.errno in (errno.EAGAIN, errno.EINTR):
                    continue
                break
            if not chunk:
                break
            buf.extend(chunk)
        return buf

    def _write(self, data, timeout=1.0):
        """Write all of data to the non-blocking port; False if it will not drain."""
        end = time.time() + timeout
        while data:
            try:
                data = data[os.write(self.fd, data):]
            except OSError as err:
                if err.errno not in (errno.EAGAIN, errno.EINTR):
                    raise
                if time.time() > end:
                    return False
                select.select([], [self.fd], [], 0.05)
        return True

    def transact(self, unit, pdu, first_byte_timeout, char_timeout=0.25):
        """Send one request, return the response PDU, or None on failure."""
        frame = bytearray([unit]) + bytearray(pdu)
        frame += bytearray(struct.pack("<H", crc16(frame)))
        termios.tcflush(self.fd, termios.TCIFLUSH)
        if not self._write(bytes(frame)):
            return None
        termios.tcdrain(self.fd)

        head = self._read(2, first_byte_timeout)
        if len(head) < 2 or head[0] != unit:
            return None
        function = head[1]
        if function & 0x80:
            rest = self._read(3, char_timeout)
            need = 3
        elif function in READ_FUNCTIONS:
            count = self._read(1, char_timeout)
            if len(count) < 1:
                return None
            head += count
            need = count[0] + 2
            rest = self._read(need, char_timeout)
        else:
            return None
        if len(rest) < need:
            return None
        message = head + rest
        if crc16(message[:-2]) != struct.unpack("<H", bytes(message[-2:]))[0]:
            return None
        if (function & 0x7F) != bytearray(pdu)[0]:
            return None
        return bytes(message[1:-2])


def recv_exact(conn, count):
    buf = bytearray()
    while len(buf) < count:
        chunk = conn.recv(count - len(buf))
        if not chunk:
            return None
        buf.extend(chunk)
    return bytes(buf)


def exception_pdu(function, code):
    return bytes(bytearray([function | 0x80, code]))


def serve_client(conn, addr, bus, lock, opts):
    conn.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    try:
        while True:
            header = recv_exact(conn, 7)
            if header is None:
                return
            tid, proto, length, unit = struct.unpack(">HHHB", header)
            if proto != 0 or not 2 <= length <= 254:
                return
            pdu = recv_exact(conn, length - 1)
            if pdu is None:
                return
            function = bytearray(pdu)[0]
            if function not in READ_FUNCTIONS:
                reply = exception_pdu(function, EXC_ILLEGAL_FUNCTION)
            elif not 1 <= unit <= 247:
                reply = exception_pdu(function, EXC_TARGET_FAILED)
            else:
                reply = None
                with lock:
                    for _ in range(opts.retries + 1):
                        reply = bus.transact(unit, pdu, opts.timeout)
                        if reply is not None:
                            break
                    time.sleep(opts.gap)
                if reply is None:
                    if opts.verbose:
                        log("no reply from unit %d (%s)" % (unit, addr[0]))
                    reply = exception_pdu(function, EXC_TARGET_FAILED)
            conn.sendall(struct.pack(">HHHB", tid, 0, len(reply) + 1, unit) + reply)
    except (socket.error, OSError):
        pass
    finally:
        conn.close()


def run_probe(bus, opts):
    pdu = struct.pack(">BHH", 0x03, opts.addr, 1)
    reply = bus.transact(opts.probe, pdu, opts.timeout)
    if reply is None:
        print("unit %d: no reply" % opts.probe)
        return 1
    if bytearray(reply)[0] & 0x80:
        print("unit %d: exception 0x%02x" % (opts.probe, bytearray(reply)[1]))
        return 1
    print("unit %d register %d = %d" % (opts.probe, opts.addr, struct.unpack(">H", reply[2:4])[0]))
    return 0


def run_scan(bus, opts):
    """Read register 11 from every unit id straight off the serial bus, timing each."""
    results = []
    started = time.time()
    for unit in range(opts.first, opts.last + 1):
        begun = time.time()
        reply = None
        for _ in range(opts.retries + 1):
            reply = bus.transact(unit, struct.pack(">BHH", 0x03, opts.addr, 1), opts.timeout)
            if reply is not None:
                break
        took = time.time() - begun
        if reply is None:
            kind, detail = "silent", "no reply"
        elif bytearray(reply)[0] & 0x80:
            kind, detail = "exception", "exception 0x%02x" % bytearray(reply)[1]
        else:
            kind, detail = "meter", "id %d" % struct.unpack(">H", reply[2:4])[0]
        results.append((unit, kind, took))
        print("%3d  %-9s %-16s %6.0f ms" % (unit, kind, detail, took * 1000))
        sys.stdout.flush()
        time.sleep(opts.gap)

    def of(kind):
        return [r for r in results if r[1] == kind]

    def avg(rows):
        return sum(r[2] for r in rows) / len(rows) * 1000 if rows else 0.0

    print("")
    print("scanned %d addresses (%d-%d) in %.1f s" % (
        len(results), opts.first, opts.last, time.time() - started))
    print("  meters answering: %3d  (avg %.0f ms)  units %s" % (
        len(of("meter")), avg(of("meter")), [r[0] for r in of("meter")]))
    print("  exception replies:%3d  (avg %.0f ms)  units %s" % (
        len(of("exception")), avg(of("exception")), [r[0] for r in of("exception")]))
    print("  no reply:         %3d  (avg %.0f ms)" % (len(of("silent")), avg(of("silent"))))
    slowest = sorted(results, key=lambda r: -r[2])[:5]
    print("  slowest: " + ", ".join("%d (%.0f ms)" % (r[0], r[2] * 1000) for r in slowest))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--serial", required=True, help="serial device, e.g. /dev/ttySC0")
    parser.add_argument("--baud", type=int, default=9600, choices=sorted(BAUDS))
    parser.add_argument("--parity", default="N", choices=["N", "E", "O"])
    parser.add_argument("--stop-bits", type=int, default=1, choices=[1, 2])
    parser.add_argument("--port", type=int, default=502, help="TCP listen port")
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--timeout", type=float, default=0.3, help="seconds to wait for a meter per try")
    parser.add_argument("--retries", type=int, default=1, help="extra tries per request")
    parser.add_argument("--gap", type=float, default=0.01, help="idle seconds between requests")
    parser.add_argument("--max-clients", type=int, default=16)
    parser.add_argument("--probe", type=int, metavar="UNIT", help="read one register and exit")
    parser.add_argument("--scan", action="store_true", help="time every unit id and exit")
    parser.add_argument("--first", type=int, default=1, help="first unit id for --scan")
    parser.add_argument("--last", type=int, default=247, help="last unit id for --scan")
    parser.add_argument("--addr", type=int, default=11, help="register for --probe/--scan")
    parser.add_argument("-v", "--verbose", action="store_true")
    opts = parser.parse_args()

    bus = SerialBus(opts.serial, opts.baud, opts.parity, opts.stop_bits)
    if opts.probe is not None:
        sys.exit(run_probe(bus, opts))
    if opts.scan:
        sys.exit(run_scan(bus, opts))

    lock = threading.Lock()
    slots = threading.BoundedSemaphore(opts.max_clients)
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((opts.bind, opts.port))
    server.listen(16)
    log("proxy %s -> %s %d-8%s%d" % (opts.port, opts.serial, opts.baud, opts.parity, opts.stop_bits))
    while True:
        conn, addr = server.accept()
        if not slots.acquire(False):
            conn.close()
            continue

        def run(conn=conn, addr=addr):
            try:
                serve_client(conn, addr, bus, lock, opts)
            finally:
                slots.release()

        thread = threading.Thread(target=run)
        thread.daemon = True
        thread.start()


if __name__ == "__main__":
    main()
