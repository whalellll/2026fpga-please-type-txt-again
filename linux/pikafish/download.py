#!/usr/bin/env python3
"""Small urllib replacement for musl-cross-make's wget invocation."""

import os
import sys
import time
import urllib.request


def main() -> int:
    if len(sys.argv) != 3:
        print(f"usage: {sys.argv[0]} OUTPUT URL", file=sys.stderr)
        return 2

    output, url = sys.argv[1:]
    partial = output + ".part"
    if os.path.isfile(output) and os.path.getsize(output) > 0:
        return 0

    request = urllib.request.Request(url, headers={"User-Agent": "pikafish-rv32-builder/1"})
    for attempt in range(1, 6):
        try:
            with urllib.request.urlopen(request, timeout=120) as response, open(partial, "wb") as target:
                while chunk := response.read(1024 * 1024):
                    target.write(chunk)
            os.replace(partial, output)
            return 0
        except Exception as error:  # Network diagnostics belong in the build log.
            print(f"download attempt {attempt}/5 failed: {error}", file=sys.stderr)
            if attempt == 5:
                return 1
            time.sleep(attempt * 5)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
