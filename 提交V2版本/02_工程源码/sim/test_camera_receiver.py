"""Windows loopback integration test for receive_camera.ps1 (Python stdlib)."""
import json
import pathlib
import socket
import struct
import subprocess
import sys
import tempfile
import time
import zlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOTAL = 1280 * 720 * 2
CHUNK = 1024
LOCAL = ("127.0.0.1", 49061)
PEER = ("127.0.0.1", 49062)


def packet(kind, session, frame, sequence, frame_crc, payload=b""):
    header = struct.pack(">4sBBHIIIIHHHHI", b"CAMP", 1, kind, 40, session,
                         frame, sequence, TOTAL, 1280, 720, 1, len(payload), frame_crc)
    crc = zlib.crc32(header + payload)
    return header + struct.pack(">I", crc) + payload


def answer(sock, kind, session, frame, sequence, frame_crc, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        sock.settimeout(max(0.01, deadline - time.monotonic()))
        try:
            data, _ = sock.recvfrom(1500)
        except (socket.timeout, ConnectionResetError):
            break
        if len(data) != 40 or data[:4] != b"CAMP" or zlib.crc32(data[:36]) != struct.unpack(">I", data[36:40])[0]:
            continue
        decoded = struct.unpack(">4sBBHIIIIHHHHII", data)
        if decoded[2] == kind and decoded[4] == session and decoded[5] == frame and decoded[6] == sequence and decoded[12] == frame_crc:
            return
    raise AssertionError("missing reply type %d seq %d" % (kind, sequence))


def no_answer(sock):
    sock.settimeout(0.15)
    try:
        data, _ = sock.recvfrom(1500)
        raise AssertionError("unexpected receiver response: %r" % data[:40])
    except (socket.timeout, ConnectionResetError):
        pass


def png_pixels(path):
    """Decode PNG scanlines with stdlib to check exact RGB and row direction."""
    contents = path.read_bytes()
    assert contents[:8] == b"\x89PNG\r\n\x1a\n"
    chunks = []
    position = 8
    width = height = channels = None
    while position < len(contents):
        length = struct.unpack_from(">I", contents, position)[0]
        kind = contents[position + 4:position + 8]
        payload = contents[position + 8:position + 8 + length]
        assert zlib.crc32(kind + payload) == struct.unpack_from(">I", contents, position + 8 + length)[0]
        if kind == b"IHDR":
            width, height, depth, mode, compression, filtering, interlace = struct.unpack(">IIBBBBB", payload)
            assert depth == 8 and mode in (2, 6) and interlace == 0
            channels = 3 if mode == 2 else 4
        if kind == b"IDAT":
            chunks.append(payload)
        position += length + 12
    data = zlib.decompress(b"".join(chunks))
    stride = width * channels
    previous = bytearray(stride)
    samples = {}
    position = 0
    for y in range(height):
        kind = data[position]
        position += 1
        row = bytearray(data[position:position + stride])
        position += stride
        for i in range(stride):
            left = row[i - channels] if i >= channels else 0
            above = previous[i]
            upper_left = previous[i - channels] if i >= channels else 0
            if kind == 0:
                predictor = 0
            elif kind == 1:
                predictor = left
            elif kind == 2:
                predictor = above
            elif kind == 3:
                predictor = (left + above) // 2
            elif kind == 4:
                p = left + above - upper_left
                distances = (abs(p - left), abs(p - above), abs(p - upper_left))
                predictor = (left, above, upper_left)[distances.index(min(distances))]
            else:
                raise AssertionError("unsupported PNG row filter")
            row[i] = (row[i] + predictor) & 255
        if y in (0, 1, 719):
            samples[y] = row
        previous = row
    assert position == len(data)
    return width, height, channels, samples


def send_frame(sock, session, frame, raw, frame_crc):
    start = packet(1, session, frame, 0, frame_crc)
    for _ in range(30):
        sock.sendto(start, PEER)
        try:
            answer(sock, 0x81, session, frame, 0, frame_crc, 0.3)
            break
        except AssertionError:
            time.sleep(0.25)
            continue
    else:
        raise AssertionError("receiver did not start")

    # Bad packet CRC and out-of-order data must not advance the receiver.
    bad = bytearray(packet(2, session, frame, 0, frame_crc, raw[:CHUNK]))
    bad[-1] ^= 1
    sock.sendto(bad, PEER)
    no_answer(sock)
    sock.sendto(packet(2, session, frame, 1, frame_crc, raw[CHUNK:2 * CHUNK]), PEER)
    no_answer(sock)
    sock.sendto(packet(2, session + 1000, frame, 0, frame_crc, raw[:CHUNK]), PEER)
    no_answer(sock)
    sock.sendto(packet(2, session, frame + 1, 0, frame_crc, raw[:CHUNK]), PEER)
    no_answer(sock)
    # Valid packet CRC cannot make wrong dimensions/format/length valid.
    for offset, field, value in ((20, "I", TOTAL - 2), (24, "H", 1279),
                                 (26, "H", 719), (28, "H", 2),
                                 (30, "H", CHUNK - 1)):
        malformed = bytearray(packet(2, session, frame, 0, frame_crc, raw[:CHUNK]))
        struct.pack_into(">" + field, malformed, offset, value)
        struct.pack_into(">I", malformed, 36,
                         zlib.crc32(malformed[:36] + malformed[40:]))
        sock.sendto(malformed, PEER)
        no_answer(sock)
    sock.sendto(packet(1, session + 2000, frame, 0, frame_crc), PEER)
    answer(sock, 0x84, session + 2000, frame, 0, frame_crc)
    sock.sendto(packet(3, session, frame, 0, frame_crc), PEER)
    answer(sock, 0x84, session, frame, 0, frame_crc)

    chunks = (TOTAL + CHUNK - 1) // CHUNK
    for seq in range(chunks):
        payload = raw[seq * CHUNK:(seq + 1) * CHUNK]
        data = packet(2, session, frame, seq, frame_crc, payload)
        sock.sendto(data, PEER)
        answer(sock, 0x82, session, frame, seq, frame_crc)
        if seq in (0, 5):
            # Duplicate delivery models a lost ACK.
            sock.sendto(data, PEER)
            answer(sock, 0x82, session, frame, seq, frame_crc)
    end = packet(3, session, frame, chunks, frame_crc)
    sock.sendto(end, PEER)
    return end, chunks


def main():
    raw = bytearray(TOTAL)
    for y in range(720):
        color = 0xF800 if y == 0 else 0x07E0 if y == 1 else 0x001F if y == 719 else (y & 31)
        raw[y * 2560:(y + 1) * 2560] = struct.pack("<H", color) * 1280
    raw[2558:2560] = struct.pack("<H", 0xFFFF)
    raw[2:4] = struct.pack("<H", 0x8410)
    crc = zlib.crc32(raw)
    with tempfile.TemporaryDirectory(prefix="camera_protocol_") as directory:
        process = subprocess.Popen([
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
            str(ROOT / "scripts" / "receive_camera.ps1"), "-OutputDirectory", directory,
            "-ListenAddress", "127.0.0.1", "-BoardAddress", "127.0.0.1"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.bind(LOCAL)
                # A cancelled partial session must leave no image or raw data.
                start = packet(1, 100, 7, 0, crc)
                # UDP resets can return immediately while PowerShell/Add-Type
                # starts. Preserve the original nominal 30 * (0.3 + 0.25)
                # second window instead of counting those immediate failures.
                startup_deadline = time.monotonic() + 16.5
                while True:
                    returncode = process.poll()
                    if returncode is not None:
                        raise AssertionError("receiver exited during startup: %d" % returncode)
                    remaining = startup_deadline - time.monotonic()
                    if remaining <= 0:
                        raise AssertionError("receiver startup timeout after 16.5 seconds")
                    sock.sendto(start, PEER)
                    try:
                        answer(sock, 0x81, 100, 7, 0, crc, min(0.3, remaining))
                        break
                    except AssertionError:
                        time.sleep(min(0.25, max(0, startup_deadline - time.monotonic())))
                # A cancel must match the entire descriptor and control seq.
                sock.sendto(packet(4, 100, 7, 0, crc ^ 1), PEER)
                no_answer(sock)
                sock.sendto(packet(4, 100, 7, 1, crc), PEER)
                no_answer(sock)
                sock.sendto(packet(2, 100, 7, 0, crc, raw[:CHUNK]), PEER)
                answer(sock, 0x82, 100, 7, 0, crc)
                sock.sendto(packet(4, 100, 7, 0, crc), PEER)
                time.sleep(0.2)
                assert not list(pathlib.Path(directory).iterdir())

                for session in (101, 102):
                    end, chunks = send_frame(sock, session, 7, raw, crc)
                    answer(sock, 0x83, session, 7, chunks, crc, 30)
                    # A lost SAVED response is answered again without a new file.
                    sock.sendto(end, PEER)
                    answer(sock, 0x83, session, 7, chunks, crc)

                pngs = sorted(pathlib.Path(directory).glob("*.png"))
                jsons = sorted(pathlib.Path(directory).glob("*.json"))
                assert len(pngs) == len(jsons) == 2
                assert pngs[0].name != pngs[1].name
                assert not list(pathlib.Path(directory).glob("*.part"))
                for png in pngs:
                    width, height, channels, rows = png_pixels(png)
                    assert (width, height) == (1280, 720)
                    assert tuple(rows[0][:3]) == (255, 0, 0)
                    assert tuple(rows[0][channels:channels + 3]) == (132, 130, 132)
                    assert tuple(rows[0][1279 * channels:1279 * channels + 3]) == (255, 255, 255)
                    assert tuple(rows[1][:3]) == (0, 255, 0)
                    assert tuple(rows[719][:3]) == (0, 0, 255)
                    metadata = json.loads(png.with_suffix(".json").read_text(encoding="utf-8"))
                    assert metadata["source"] == "CMOS2"
                    assert metadata["raw_crc32"] == "%08x" % crc
                    assert "label" not in metadata
                # A complete transfer with the wrong whole-frame CRC must
                # fail before a final PNG or JSON is published.
                wrong_crc = crc ^ 1
                _, chunks = send_frame(sock, 103, 8, raw, wrong_crc)
                answer(sock, 0x84, 103, 8, chunks, wrong_crc, 30)
                assert len(list(pathlib.Path(directory).glob("*.png"))) == 2
                assert not list(pathlib.Path(directory).glob("*.part"))
                # An incomplete session expires and removes its raw part.
                sock.sendto(packet(1, 104, 9, 0, crc), PEER)
                answer(sock, 0x81, 104, 9, 0, crc)
                sock.sendto(packet(2, 104, 9, 0, crc, raw[:CHUNK]), PEER)
                answer(sock, 0x82, 104, 9, 0, crc)
                time.sleep(5.6)
                assert not list(pathlib.Path(directory).glob("*.part"))
                assert len(list(pathlib.Path(directory).glob("*.png"))) == 2
                print("CAMERA_RECEIVER_PROTOCOL_PNG_PASS")
        finally:
            test_failed = sys.exc_info()[0] is not None
            output = b""
            try:
                if process.poll() is None:
                    process.terminate()
                try:
                    output, _ = process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    output, _ = process.communicate(timeout=5)
            except Exception as cleanup_error:
                output = getattr(cleanup_error, "output", None) or output
                print("receiver cleanup failed: %r" % cleanup_error, file=sys.stderr)
                if not test_failed:
                    raise
            finally:
                if test_failed:
                    print("receiver output on failure:\n" + output.decode(errors="replace"),
                          file=sys.stderr)


if __name__ == "__main__":
    main()
