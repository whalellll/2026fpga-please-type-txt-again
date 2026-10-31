"""Local, bounded synthetic preview of native C + existing GUI1080 RGB565.

No real camera / ASR / engine / benchmark is opened. Browser only displays the
actual native framebuffer; it contains no alternate chessboard implementation.
Run with WSL Python after build_host.sh. Ctrl+C stops it; default lifespan 15m.
"""
from __future__ import annotations
import argparse
import ctypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import struct
import threading
import time
import zlib


class Preview:
    def __init__(self, library):
        self.lib = ctypes.CDLL(str(library.resolve()))
        self.lib.xy_host_create.restype = ctypes.c_void_p
        self.lib.xy_host_destroy.argtypes = [ctypes.c_void_p]
        self.lib.xy_host_event.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        self.lib.xy_state_json.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
        self.lib.xy_state_json.restype = ctypes.c_size_t
        self.lib.xy_host_rgb888.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
        self.lib.xy_host_rgb888.restype = ctypes.c_size_t
        self.app = self.lib.xy_host_create()
        if not self.app:
            raise MemoryError("Native app allocation failed")
        self.buffer = ctypes.create_string_buffer(16384)
        self.rgb = ctypes.create_string_buffer(1920 * 1080 * 3)
        self.lock = threading.Lock()
        self.cached_state = None
        self.png = None

    def state(self):
        self.lib.xy_host_event(self.app, b"tick")
        if not self.lib.xy_state_json(self.app, self.buffer, len(self.buffer)):
            raise RuntimeError("Native state serialization failed")
        return self.buffer.value

    def frame(self):
        state = self.state()
        if state != self.cached_state:
            assert self.lib.xy_host_rgb888(self.app, self.rgb, len(self.rgb)) == len(self.rgb)
            raw = self.rgb.raw
            scan = b"".join(b"\0" + raw[row * 5760:(row + 1) * 5760] for row in range(1080))

            def chunk(name, payload):
                return struct.pack(">I", len(payload)) + name + payload + struct.pack(">I", zlib.crc32(name + payload))

            self.png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">2I5B", 1920, 1080, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(scan, 3)) + chunk(b"IEND", b"")
            self.cached_state = state
        return self.png


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--library", type=Path, default=Path("build/xinyi-host-20261024/native/libxinyi.so"))
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--duration", type=int, default=900)
    args = parser.parse_args()
    if not 1 <= args.duration <= 3600:
        parser.error("--duration must be 1..3600 seconds")
    preview = Preview(args.library)
    html = (Path(__file__).parent / "host_preview.html").read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # No persistent request / polling logs.

        def send(self, code, kind, body):
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            route = self.path.split("?", 1)[0]
            with preview.lock:
                if route == "/":
                    self.send(200, "text/html; charset=utf-8", html)
                elif route == "/state":
                    self.send(200, "application/json", preview.state())
                elif route == "/frame.png":
                    self.send(200, "image/png", preview.frame())
                else:
                    self.send(404, "text/plain", b"Not found")

        def do_POST(self):
            if self.path != "/event":
                return self.send(404, "text/plain", b"Not found")
            origin = self.headers.get("Origin")
            if origin and origin not in (f"http://127.0.0.1:{args.port}", f"http://localhost:{args.port}"):
                return self.send(403, "text/plain", b"Origin rejected")
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 256:
                return self.send(400, "text/plain", b"Bad length")
            try:
                event = json.loads(self.rfile.read(length))["event"].encode("ascii")
            except (ValueError, KeyError, AttributeError, UnicodeError):
                return self.send(400, "text/plain", b"Bad event")
            with preview.lock:
                accepted = preview.lib.xy_host_event(preview.app, event)
                self.send(200 if accepted else 409, "application/json", preview.state())

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.daemon_threads = True
    deadline = threading.Timer(args.duration, server.shutdown)
    deadline.daemon = True
    deadline.start()
    print(f"XINYI_HOST_PREVIEW http://127.0.0.1:{args.port}/ synthetic_only duration={args.duration}s Ctrl+C stops", flush=True)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        deadline.cancel()
        server.server_close()
        preview.lib.xy_host_destroy(preview.app)


if __name__ == "__main__":
    main()
