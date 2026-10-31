"""Bounded private hostmock resident-process test; no actual device/inference."""
from pathlib import Path
import argparse
import json
import os
import selectors
import subprocess
import time
import zlib


class Worker:
    def __init__(self, command, directory, unproven=False):
        self.directory = directory
        directory.mkdir()
        environment = dict(os.environ)
        if unproven:
            environment['XQCOACH_TEST_UNPROVEN'] = '1'
        self.process = subprocess.Popen(command+['--serve', str(directory)], stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, env=environment)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)
        self.buffer = b''
        self.lines = []
        self.pending = []

    def pump(self, duration):
        for key, _ in self.selector.select(duration):
            chunk = os.read(key.fd, 65536)
            if not chunk:
                self.selector.unregister(key.fileobj)
                continue
            self.buffer += chunk
            while b'\n' in self.buffer:
                line, self.buffer = self.buffer.split(b'\n', 1)
                line = line.decode('utf-8', errors='strict')
                self.lines.append(line)
                self.pending.append(line)

    def wait_line(self, prefix, timeout=12):
        deadline = time.monotonic()+timeout
        while time.monotonic() < deadline:
            while self.pending:
                line = self.pending.pop(0)
                if line.startswith(prefix):
                    return line
            self.pump(.03)
        raise AssertionError(('Missing line', prefix, self.process.poll(), self.lines))

    def publish(self, identity, crc):
        token, frame = identity
        temporary = self.directory/'request.part'
        temporary.write_text(f'XQ_COACH_REQUEST_V1 {token} {frame} {crc:08x} rv32-v321-coach\n')
        temporary.replace(self.directory/'request.txt')

    def packet(self, identity, crc, status, timeout=5):
        expected = f'XQ_COACH_RESULT_V1 {identity[0]} {identity[1]} {crc:08x} rv32-v321-coach {status} 0 00000000\n'
        deadline = time.monotonic()+timeout
        while time.monotonic() < deadline:
            path = self.directory/'result.txt'
            if path.exists() and path.read_text() == expected:
                return expected
            self.pump(.02)
        raise AssertionError(('Wrong/missing packet', expected, path.read_text() if path.exists() else None, self.lines))

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=4)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
                raise
        while self.selector.get_map():
            self.pump(.02)
        (self.directory/'worker.log').write_text('\n'.join(self.lines)+'\n')
        self.selector.close()
        self.process.stdout.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', required=True)
    parser.add_argument('--qemu', action='store_true')
    parser.add_argument('--models', required=True)
    parser.add_argument('--frame', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    assert not args.output.exists()
    args.output.mkdir()
    command = (['qemu-riscv32'] if args.qemu else [])+[args.worker, '--driver', '--models', args.models]
    frame = Path(args.frame).read_bytes()
    assert len(frame) == 1843200 and not any(frame)
    crc = zlib.crc32(frame)
    worker = Worker(command, args.output/'normal')
    try:
        (worker.directory/'frame.rgb565').write_bytes(frame)
        worker.wait_line('XQ_COACH_READY ')
        worker.wait_line('XQ_COACH_IDLE')
        worker.publish((401, 81), crc)
        worker.wait_line('XQ_COACH_TEST_IOCTL_ENTER hostmock=1')
        # A premature B cannot replace the already validated A identity.
        worker.publish((402, 82), crc ^ 1)
        worker.pump(.08)
        assert not (worker.directory/'result.txt').exists()
        assert worker.lines.count('XQ_COACH_IDLE') == 1
        start = time.monotonic()
        (worker.directory/'request.txt').unlink()
        worker.pump(.04)
        assert not (worker.directory/'result.txt').exists(), 'ACK before controlled drain'
        worker.wait_line('XQ_COACH_TEST_IOCTL_RETURN_DONE hostmock=1')
        worker.wait_line('XQ_COACH_IDLE')
        assert time.monotonic()-start >= .10
        cancelled = worker.packet((401, 81), crc, 9)
        assert worker.lines.count('XQ_COACH_IDLE') == 2
        (worker.directory/'result.txt').unlink()
        # B now starts only after release9+IDLE, and returns a distinct failure.
        worker.publish((402, 82), crc ^ 1)
        ordinary = worker.packet((402, 82), crc ^ 1, 7)
        worker.publish((403, 83), crc)  # Must not be treated as request C yet.
        worker.pump(.08)
        assert (worker.directory/'result.txt').read_text() == ordinary
        assert worker.lines.count('XQ_COACH_IDLE') == 2
        (worker.directory/'request.txt').unlink()
        worker.wait_line('XQ_COACH_IDLE')
        released = worker.packet((402, 82), crc ^ 1, 9)
        assert worker.lines.count('XQ_COACH_IDLE') == 3
        (worker.directory/'result.txt').unlink()
        worker.publish((403, 83), crc)
        worker.wait_line('XQ_COACH_TEST_IOCTL_ENTER hostmock=1')
        worker.process.terminate()
        assert worker.process.wait(timeout=5) == 0
        worker.close()
        assert not (worker.directory/'result.txt').exists()
        assert worker.lines.count('XQ_COACH_IDLE') == 3, 'TERM does not acknowledge reuse'
    finally:
        worker.close()
    unsafe = Worker(command, args.output/'unproven', unproven=True)
    try:
        (unsafe.directory/'frame.rgb565').write_bytes(frame)
        unsafe.wait_line('XQ_COACH_READY ')
        unsafe.wait_line('XQ_COACH_IDLE')
        unsafe.publish((501, 91), crc)
        unsafe.wait_line('XQ_COACH_TEST_IOCTL_ENTER hostmock=1')
        (unsafe.directory/'request.txt').unlink()
        assert unsafe.process.wait(timeout=5) == 2
        unsafe.close()
        assert not (unsafe.directory/'result.txt').exists()
        assert unsafe.lines.count('XQ_COACH_IDLE') == 1
        assert 'XQ_COACH_DRAIN_UNPROVEN no_release_ack=1' in unsafe.lines
    finally:
        unsafe.close()
    record = dict(status='PASS', hardware_used=False, hostmock=True,
                  cancel_after_done_before_release9=True, release_identity_not_overwritten=True,
                  next_generation_after_release9_and_idle=True, ordinary_consumption_requires_release9_and_idle=True,
                  term_waitpid_no_release_ack=True, unproven_busy_timeout_withholds_ack=True,
                  cancelled_packet=cancelled, ordinary_packet=ordinary, released_packet=released)
    (args.output/'result.json').write_text(json.dumps(record, indent=2)+'\n')
    print('XQCOACH_CANCEL_RELEASE9_IDLE_REUSE_TERM_AND_UNPROVEN_DRAIN_HOSTMOCK_PASS')


if __name__ == '__main__':
    main()
