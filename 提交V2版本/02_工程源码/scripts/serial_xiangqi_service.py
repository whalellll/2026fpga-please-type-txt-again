#!/usr/bin/env python3
"""Load the bare-metal Xiangqi service into DDR and verify its UART RPC."""

from __future__ import annotations

import argparse
import pathlib
import re
import sys
import time

import serial


STX = 0x02
EOT = 0x04
ACK = 0x06
NAK = 0x15
CAN = 0x18
PAD = 0x1A
BLOCK_BYTES = 1024
START_FEN = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w"


class BoardLink:
    def __init__(self, port: str, baud: int, log_path: pathlib.Path):
        self.serial = serial.Serial(port, baudrate=baud, timeout=0.2)
        self.log = log_path.open("w", encoding="utf-8", newline="")

    def close(self) -> None:
        self.serial.close()
        self.log.close()

    def record(self, value: int) -> None:
        if value in (9, 10, 13) or 32 <= value <= 126:
            text = chr(value)
            self.log.write(text)
            self.log.flush()
            print(text, end="", flush=True)

    def read_until(self, needles: tuple[bytes, ...], timeout: float) -> bytes:
        deadline = time.monotonic() + timeout
        recent = bytearray()
        while time.monotonic() < deadline:
            data = self.serial.read(1)
            if not data:
                continue
            self.record(data[0])
            recent += data
            if len(recent) > 4096:
                del recent[:-4096]
            for needle in needles:
                if needle in recent:
                    return needle
        names = ", ".join(item.decode("ascii", errors="replace") for item in needles)
        raise TimeoutError(f"timed out waiting for board text: {names}")

    def wait_control(self, allowed: tuple[int, ...], timeout: float) -> int:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            data = self.serial.read(1)
            if not data:
                continue
            value = data[0]
            if value in allowed:
                return value
            self.record(value)
        raise TimeoutError("timed out waiting for XMODEM control byte")

    def command(self, text: str, timeout: float = 10.0) -> str:
        self.serial.write((text + "\r").encode("ascii"))
        deadline = time.monotonic() + timeout
        line = bytearray()
        while time.monotonic() < deadline:
            data = self.serial.read(1)
            if not data:
                continue
            self.record(data[0])
            if data[0] in (10, 13):
                decoded = line.decode("ascii", errors="replace")
                line.clear()
                if decoded.startswith("XQ "):
                    return decoded
            elif 32 <= data[0] <= 126:
                line += data
        raise TimeoutError(f"timed out waiting for response to {text}")


def crc16_xmodem(payload: bytes) -> int:
    crc = 0
    for value in payload:
        crc ^= value << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def send_xmodem(link: BoardLink, image: bytes, address: str) -> None:
    link.serial.write(f"loadx {address}\r".encode("ascii"))
    link.read_until((b"Start XMODEM-CRC transfer now...",), 10.0)
    link.wait_control((ord("C"),), 5.0)
    blocks = (len(image) + BLOCK_BYTES - 1) // BLOCK_BYTES
    for index in range(blocks):
        payload = image[index * BLOCK_BYTES : (index + 1) * BLOCK_BYTES]
        payload += bytes((PAD,)) * (BLOCK_BYTES - len(payload))
        number = (index + 1) & 0xFF
        crc = crc16_xmodem(payload)
        packet = bytes((STX, number, 0xFF - number)) + payload + crc.to_bytes(2, "big")
        for attempt in range(10):
            link.serial.write(packet)
            response = link.wait_control((ACK, NAK, CAN), 8.0)
            if response == ACK:
                break
            if response == CAN:
                raise RuntimeError(f"board cancelled XMODEM at block {index + 1}")
        else:
            raise RuntimeError(f"XMODEM retries exhausted at block {index + 1}")
        if (index + 1) % 32 == 0 or index + 1 == blocks:
            percent = (index + 1) * 100 // blocks
            print(f"\nXMODEM {percent}% ({index + 1}/{blocks})", flush=True)

    link.serial.write(bytes((EOT,)))
    link.wait_control((ACK,), 8.0)
    link.read_until((b"soc> ",), 10.0)
    print(f"\nXMODEM loaded {len(image)} bytes", flush=True)


def main() -> int:
    root = pathlib.Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="COM17")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--image", type=pathlib.Path,
                        default=root / "prebuilt" / "xiangqi_service.bin")
    parser.add_argument("--address", default="0x01000000")
    parser.add_argument("--log", type=pathlib.Path,
                        default=root / "artifacts" / "board_xiangqi_service.log")
    parser.add_argument("--skip-load", action="store_true")
    parser.add_argument("--compare-batch", action="store_true",
                        help="compare sparse HW, generic MAC and CPU paths")
    args = parser.parse_args()

    if not args.image.is_file():
        parser.error(f"missing service image: {args.image}")
    args.log.parent.mkdir(parents=True, exist_ok=True)
    link = BoardLink(args.port, args.baud, args.log)
    try:
        if not args.skip_load:
            link.serial.reset_input_buffer()
            link.serial.write(b"\r")
            link.read_until((b"soc> ",), 180.0)
            send_xmodem(link, args.image.read_bytes(), args.address)
            link.serial.write(f"boot {args.address}\r".encode("ascii"))
            link.read_until((b"XQ SERVICE READY", b"XQ FATAL"), 60.0)

        pong = link.command("PING")
        info = link.command("INFO")
        result = link.command("EVAL " + START_FEN, timeout=30.0)
        search = link.command("GO " + START_FEN, timeout=30.0)
        if pong != "XQ OK PONG":
            raise RuntimeError(f"unexpected PING response: {pong}")
        if ("MODEL=orange_h128_i8" not in info or
                "MAC_ID=0x4d41434b" not in info or
                "SPARSE_ID=0x58515345" not in info or
                "EVAL=SPARSE-HW16" not in info or
                "BATCH=HW16+MAC16+CPU" not in info):
            raise RuntimeError(f"unexpected INFO response: {info}")
        if not result.startswith("XQ OK SCORE=13 "):
            raise RuntimeError(f"unexpected start-position result: {result}")
        search_match = re.match(
                r"^XQ OK BESTMOVE=[a-i][0-9][a-i][0-9] SCORE=-?\d+ "
                r"RED_SCORE=-?\d+ DEPTH=1 NODES=\d+ "
                r"MAC_CYCLES=(?P<mac_cycles>\d+) COUNT=[1-5] TOP=", search)
        if not search_match:
            raise RuntimeError(f"unexpected board search result: {search}")
        if int(search_match.group("mac_cycles")) >= 50000:
            raise RuntimeError(
                f"sparse search used too many accelerator cycles: {search}")
        post_info = link.command("INFO")
        jobs = re.search(r" SPARSE_JOBS=(\d+)", post_info)
        positions = re.search(r" SPARSE_POSITIONS=(\d+)", post_info)
        errors = re.search(r" SPARSE_ERRORS=(\d+)", post_info)
        if (not jobs or int(jobs.group(1)) == 0 or
                not positions or int(positions.group(1)) == 0 or
                not errors or int(errors.group(1)) != 0):
            raise RuntimeError(f"sparse accelerator was not used cleanly: {post_info}")
        if args.compare_batch:
            go2 = link.command("GO2 " + START_FEN, timeout=30.0)
            go2_cpu = link.command("GO2C " + START_FEN, timeout=30.0)
            batch = link.command("GOB " + START_FEN, timeout=30.0)
            cpu = link.command("GOC " + START_FEN, timeout=30.0)
            if " DEPTH=2 " not in go2 or " BATCHES=0" in go2:
                raise RuntimeError(f"unexpected GO2 result: {go2}")
            if " DEPTH=1 " not in batch or " BATCHES=0" in batch:
                raise RuntimeError(f"unexpected batched GO1 result: {batch}")
            signature = re.compile(
                r"BESTMOVE=(?P<move>\S+) SCORE=(?P<score>-?\d+).*? "
                r"COUNT=(?P<count>\d+) TOP=(?P<top>\S+)")
            hw_match = signature.search(search)
            mac_match = signature.search(batch)
            cpu_match = signature.search(cpu)
            if not hw_match or not mac_match or not cpu_match:
                raise RuntimeError("could not parse backend comparison")
            if hw_match.groupdict() != mac_match.groupdict() or \
                    hw_match.groupdict() != cpu_match.groupdict():
                raise RuntimeError(
                    "sparse HW, generic MAC and CPU search results differ")
            go2_hw_match = signature.search(go2)
            go2_cpu_match = signature.search(go2_cpu)
            if not go2_hw_match or not go2_cpu_match or \
                    go2_hw_match.groupdict() != go2_cpu_match.groupdict():
                raise RuntimeError("sparse HW and CPU depth-2 results differ")
        print("\nXIANGQI_SERVICE_BOARD_PASS", flush=True)
        return 0
    finally:
        link.close()


if __name__ == "__main__":
    sys.exit(main())
