"""Bounded HTTP smoke test; all frames and outcomes are generated synthetically."""
import argparse
import json
from pathlib import Path
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    base = "http://127.0.0.1:8766"
    server = subprocess.Popen([sys.executable, str(Path(__file__).with_name("host_preview.py")),
                               "--library", str(args.library), "--port", "8766", "--duration", "45"],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def state():
        with urllib.request.urlopen(base+"/state", timeout=3) as r:
            return json.load(r)

    def event(text, status=200):
        request = urllib.request.Request(base+"/event", json.dumps({"event":text}).encode(),
                                          {"Content-Type":"application/json"})
        try:
            response = urllib.request.urlopen(request, timeout=3)
        except urllib.error.HTTPError as e:
            response = e
        with response:
            assert response.status == status
            return json.load(response)

    def idle(seconds=4):
        deadline = time.monotonic()+seconds
        while time.monotonic()<deadline:
            s = state()
            if not s["job"]:
                return s
            time.sleep(.05)
        raise AssertionError("Synthetic job did not finish")

    try:
        for _ in range(40):
            try:
                s=state()
                break
            except OSError:
                time.sleep(.05)
        else:
            raise AssertionError("Preview did not start")
        preset=s["coremark"]
        assert s["page"]==0 and not s["coremark_measured"]
        event("start"); event("scenario-third-rook"); event("capture")
        s=idle(); assert s["recommended"] and s["removed"]==1 and s["corrected_count"]==1
        assert s["from"]==25 and s["to"]==22 and s["board"].count(5)==2
        assert s["notation"]=="炮二平五" and s["photo_ms"]>=600
        with urllib.request.urlopen(base+"/frame.png",timeout=4) as r:
            png=r.read()
        assert png[:8]==b"\x89PNG\r\n\x1a\n" and struct.unpack(">II",png[16:24])==(1920,1080)
        (args.out/"interactive-coach.png").write_bytes(png)
        original=s["board"]
        event("voice"); assert state()["microphone"]==1
        event("capture",409); event("say"); s=idle()
        assert s["voice_total"]==s["voice_success"]==1
        event("coach"); assert state()["board"]==original and state()["microphone"]==0
        event("scenario-missing-king"); event("capture"); s=idle()
        assert s["has_board"] and not s["recommended"] and s["position_reason"]!=0
        previous=s["board"]
        event("scenario-geometry-failure"); event("capture"); s=idle()
        assert s["geometry_failed"] and s["board"]==previous
        event("home"); event("coremark"); event("cancel"); s=idle()
        assert s["coremark"]==preset and not s["coremark_measured"]
        event("coremark"); s=idle(6)
        assert s["coremark_progress"]==1000 and s["coremark"]==preset and not s["coremark_measured"]
        event("coremark-log");assert state()["coremark_log_visible"]
        event("coremark-log-next");event("coremark-log-close")
        event("coremark-reference");started=time.monotonic()
        assert not state()["coremark_reference_shown"]
        s=idle(12)
        assert time.monotonic()-started>=9.8 and s["coremark_reference_shown"]
        assert s["coremark"]==preset and not s["coremark_measured"] and not s["coremark_log_bytes"]
        with urllib.request.urlopen(base+"/frame.png",timeout=4) as r:
            (args.out/"reference-demo.png").write_bytes(r.read())
        receipt=dict(schema=1,scope="synthetic native-controller / actual RGB565 HTTP preview only",
            status="PASS",checks=["home", "red recommendation", "confidence deletion", "badge count",
            "native 1920x1080 PNG", "mic/camera exclusion", "voice statistics", "coach/voice board separation",
            "invalid shown without recommendation", "geometry failure keeps previous board",
            "cancel acknowledged", "mock finish never changes reference score"],board_measurement=False)
        (args.out/"preview-smoke.json").write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf-8")
        print("XINYI_PREVIEW_HTTP_PASS native_RGB565 delete_only red_notation exclusive_modes mock_never_scores")
    finally:
        server.terminate()
        try: server.wait(timeout=3)
        except subprocess.TimeoutExpired:
            server.kill(); server.wait()
        stdout,stderr=server.communicate()
        if server.returncode not in (0,-15) and stderr:
            print(stderr.decode(errors="replace"),file=sys.stderr)


if __name__=="__main__": main()
