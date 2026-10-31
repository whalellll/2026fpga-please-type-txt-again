"""PC-only recording boundaries; no serial port or microphone is opened."""
from pathlib import Path
import importlib.util

source = Path(__file__).resolve().parents[1] / 'linux/voice/record_dataset_pc.py'
spec = importlib.util.spec_from_file_location('recorder', source)
recorder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recorder)
blob = recorder.wav_blob(b'\x20\x00' * (60 * 16000))
assert len(blob) == 1920044
assert recorder.pcm_info(blob, max_samples=960000)[2]['samples'] == 960000
try:
    recorder.pcm_info(blob)
except RuntimeError:
    pass
else:
    raise AssertionError('Single-token limit must remain unchanged')
for seconds in [0, 61, True]:
    try:
        recorder.Board.__new__(recorder.Board).capture(lambda: None, seconds=seconds)
    except ValueError:
        pass
    else:
        raise AssertionError('Invalid recording length accepted')

class UART:
    def __init__(self): self.data = b'A' * 2600000 + b'\nDONE\n'
    @property
    def in_waiting(self): return len(self.data)
    def read(self, count):
        result, self.data = self.data[:count], self.data[count:]
        return result

board = recorder.Board.__new__(recorder.Board)
board.uart = UART()
assert board.until(rb'DONE\n', 10).endswith(b'DONE\n')
print('PC_60S_BOUNDARIES_PASS: 60s WAV, unchanged token bound, invalid durations, 2.6MB UART')
