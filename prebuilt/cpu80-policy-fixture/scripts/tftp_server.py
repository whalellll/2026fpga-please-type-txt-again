#!/usr/bin/env python3
"""Read-only TFTP server for the SoC autonomous Linux boot.

Besides RFC 1350 stop-and-wait transfers, the board and bundled servers use
``offset`` resume and ``encoding=hexcrc`` integrity options.  The latter puts
an eight-digit Adler-32 followed by uppercase ASCII hex in every DATA block.
"""

from __future__ import annotations

import argparse
import socket
import struct
import time
import zlib
from pathlib import Path


ALLOWED_FILES = {
    "fw_jump.bin", "Image", "rootfs.cpio", "soc.dtb",
    "mac_selftest.bin", "mac_benchmark.bin",
}
BLOCK_SIZE = 512
MAX_SESSION_BLOCKS = 2048


def parse_rrq(packet: bytes) -> tuple[str, dict[str, str]] | None:
    if len(packet) < 4 or packet[:2] != b"\x00\x01":
        return None
    fields = packet[2:].split(b"\0")
    if len(fields) < 3 or fields[1].lower() != b"octet":
        return None
    try:
        name = fields[0].decode("ascii")
        options: dict[str, str] = {}
        for index in range(2, len(fields) - 1, 2):
            if not fields[index]:
                break
            options[fields[index].decode("ascii").lower()] = fields[index + 1].decode("ascii")
        return name, options
    except UnicodeDecodeError:
        return None


def send_error(sock: socket.socket, peer: tuple[str, int], code: int, message: str) -> None:
    payload = struct.pack("!HH", 5, code) + message.encode("ascii", "replace") + b"\0"
    sock.sendto(payload, peer)


def wait_for_ack(sock: socket.socket, peer: tuple[str, int], block: int,
                 packet: bytes, timeout: float) -> bool:
    sock.settimeout(timeout)
    for _ in range(16):
        sock.sendto(packet, peer)
        try:
            reply, reply_peer = sock.recvfrom(2048)
        except socket.timeout:
            continue
        if reply_peer == peer and reply == struct.pack("!HH", 4, block):
            return True
        if reply_peer == peer and len(reply) >= 2 and reply[:2] == b"\x00\x05":
            return False
        time.sleep(0.1)
    return False


def serve_file(root: Path, name: str, options: dict[str, str],
               peer: tuple[str, int], timeout: float) -> bool:
    if name not in ALLOWED_FILES:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as transfer:
            send_error(transfer, peer, 1, "File not found")
        print(f"DENY {peer[0]}:{peer[1]} {name!r}", flush=True)
        return False

    path = root / name
    if not path.is_file():
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as transfer:
            send_error(transfer, peer, 1, "File not found")
        print(f"MISS {peer[0]}:{peer[1]} {path}", flush=True)
        return False

    content = path.read_bytes()
    size = len(content)
    try:
        block_size = int(options.get("blksize", BLOCK_SIZE))
        start_offset = int(options.get("offset", "0"))
    except ValueError:
        block_size, start_offset = BLOCK_SIZE, -1
    block_size = min(512, max(8, block_size))
    hexcrc = options.get("encoding", "").lower() == "hexcrc"
    if start_offset < 0 or start_offset > size:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as transfer:
            send_error(transfer, peer, 0, "Invalid offset")
        print(f"DENY {name} invalid offset={start_offset}", flush=True)
        return False

    mode = "hexcrc" if hexcrc else "raw"
    print(f"SEND {name} ({size} bytes, offset={start_offset}, "
          f"blksize={block_size}, encoding={mode}) -> {peer[0]}:{peer[1]}", flush=True)
    with path.open("rb") as source, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as transfer:
        if start_offset == 0 and options:
            oack_fields = [b"blksize", str(block_size).encode("ascii")]
            if hexcrc:
                oack_fields += [b"encoding", b"hexcrc"]
            oack = struct.pack("!H", 6) + b"\0".join(oack_fields) + b"\0"
            if not wait_for_ack(transfer, peer, 0, oack, timeout):
                print(f"TIMEOUT {name} OACK", flush=True)
                return False

        source.seek(start_offset)
        block = 1
        offset = start_offset
        session_blocks = 0
        raw_per_block = (block_size - 8) // 2 if hexcrc else block_size
        while True:
            data = source.read(raw_per_block)
            if hexcrc:
                wire_data = f"{zlib.adler32(data) & 0xffffffff:08X}".encode("ascii") + data.hex().upper().encode("ascii")
            else:
                wire_data = data
            packet = struct.pack("!HH", 3, block) + wire_data
            if not wait_for_ack(transfer, peer, block, packet, timeout):
                print(f"TIMEOUT {name} block={block}", flush=True)
                return False
            offset += len(data)
            session_blocks += 1
            time.sleep(0.002)
            if block % 1024 == 0:
                print(f"PROGRESS {name} block={block} bytes={offset}", flush=True)
            if session_blocks >= MAX_SESSION_BLOCKS and offset < size:
                print(f"CHUNK {name} next-offset={offset}", flush=True)
                return True
            if len(wire_data) < block_size:
                print(f"DONE {name} ({offset} bytes)", flush=True)
                return True
            block = (block + 1) & 0xFFFF


def main() -> int:
    default_root = Path(__file__).resolve().parent.parent / "linux" / "boot"
    parser = argparse.ArgumentParser(description="Read-only SoC Linux TFTP server")
    parser.add_argument("--bind", default="192.168.1.2", help="host IPv4 address")
    parser.add_argument("--port", type=int, default=69, help="TFTP listen port")
    parser.add_argument("--root", type=Path, default=default_root, help="boot file directory")
    parser.add_argument("--timeout", type=float, default=2.0, help="per-packet ACK timeout")
    args = parser.parse_args()

    root = args.root.resolve()
    missing = sorted(name for name in ALLOWED_FILES if not (root / name).is_file())
    if missing:
        parser.error(f"missing boot files under {root}: {', '.join(missing)}")

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as listener:
        listener.bind((args.bind, args.port))
        print(f"SoC TFTP root: {root}", flush=True)
        print(f"Listening on {args.bind}:{args.port}; board is 192.168.1.50", flush=True)
        while True:
            packet, peer = listener.recvfrom(2048)
            request = parse_rrq(packet)
            if request is None:
                print(f"IGNORE malformed request from {peer[0]}:{peer[1]}", flush=True)
                continue
            name, options = request
            serve_file(root, name, options, peer, args.timeout)


if __name__ == "__main__":
    raise SystemExit(main())
