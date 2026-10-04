"""Resolves a hostname with a raw DNS query against a public resolver.

The machine's configured resolver is not answering, so this bypasses it and
talks to 8.8.8.8 / 1.1.1.1 directly on port 53.
"""

from __future__ import annotations

import socket
import struct
import sys

SERVERS = ["8.8.8.8", "1.1.1.1"]


def build_query(host: str) -> bytes:
    header = struct.pack("!HHHHHH", 0x1234, 0x0100, 1, 0, 0, 0)
    body = b""
    for label in host.split("."):
        body += bytes([len(label)]) + label.encode("ascii")
    body += b"\x00" + struct.pack("!HH", 1, 1)  # A record
    return header + body


def parse_a(payload: bytes) -> list[str]:
    # Skip the header and the question section.
    index = 12
    while payload[index] != 0:
        index += 1 + payload[index]
    index += 5  # null byte + QTYPE + QCLASS

    addresses: list[str] = []
    while index < len(payload):
        if payload[index] & 0xC0 == 0xC0:  # compression pointer
            index += 2
            continue
        length = payload[index]
        rtype, _, _ttl, rdlength = struct.unpack("!HHIH", payload[index + 1 : index + 11])
        if rtype == 1 and rdlength == 4:
            addresses.append(socket.inet_ntoa(payload[index + 11 : index + 15]))
        index += 11 + rdlength
    return addresses


def main() -> int:
    host = sys.argv[1] if len(sys.argv) > 1 else "qtozkhuqaqnglztaalkx.supabase.co"

    try:
        print(f"system resolver: {socket.gethostbyname(host)}")
    except OSError as exc:
        print(f"system resolver: FAILED ({exc})")

    for server in SERVERS:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(5)
        try:
            sock.sendto(build_query(host), (server, 53))
            data, _ = sock.recvfrom(512)
            addresses = parse_a(data)
            print(f"{server}: {addresses or 'no A record'}")
            if addresses:
                return 0
        except Exception as exc:  # noqa: BLE001
            print(f"{server}: failed ({type(exc).__name__})")
        finally:
            sock.close()

    return 1


if __name__ == "__main__":
    raise SystemExit(main())