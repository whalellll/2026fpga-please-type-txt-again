"""PC SD location and missing-card handling; never opens a real serial port."""
from pathlib import Path
import json,sys,tempfile
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'linux/voice'))
import record_dataset_pc as recorder
import record_batch_pc as batch
from voice_phrase_labels import LABELS_BY_SPLIT, ID_TO_LABEL

assert tuple(map(len, (LABELS_BY_SPLIT['train'], LABELS_BY_SPLIT['validation'], LABELS_BY_SPLIT['test']))) == (73, 10, 20)
assert len(set(sum((list(v) for v in LABELS_BY_SPLIT.values()), []))) == 103
assert batch.parse_words(' '.join(LABELS_BY_SPLIT['train'][:2]), 'train') == ['phrase001', 'phrase002']
assert ID_TO_LABEL['phrase074'] == LABELS_BY_SPLIT['validation'][0]
try:
    batch.parse_words(LABELS_BY_SPLIT['validation'][0], 'train')
except ValueError:
    pass
else:
    raise AssertionError('Validation labels must not enter the training split')

with tempfile.TemporaryDirectory() as temp:
    root=Path(temp);(root/'VOICE').mkdir()
    card={'volume_serial':123}
    with patch.object(batch,'pc_volume_serial',return_value=123):
        assert batch.pc_sd_voice_directories(card,[root])==[root/'VOICE']
    with patch.object(batch,'pc_volume_serial',return_value=456):
        assert batch.pc_sd_voice_directories(card,[root])==[]
    for number,speaker in [(5,'unlabelled'),(6,'speaker01'),(7,'unlabelled')]:
        wav=root/'VOICE'/('REC%05d.WAV'%number);wav.touch()
        wav.with_suffix('.JSON').write_text(json.dumps({'request':{'speaker':speaker,'split':'train'}}))
    assert batch.latest_sd_recording(root/'VOICE','speaker01','train').name=='REC00006.WAV'
    assert batch.latest_sd_recording(root/'VOICE','speaker01','validation') is None

board=recorder.Board.__new__(recorder.Board)
board.command=lambda *args,**kwargs:(_ for _ in ()).throw(RuntimeError('SD initialization error=-1\nRAW SHELL TRACE'))
try:
    board.sd_info({'binary_path':'/tmp/sd','binary_sha256':'0'*64})
except recorder.SDCardNotPresentError as exc:
    assert 'SD' in str(exc) and 'RAW SHELL' not in str(exc)
else:raise AssertionError('Missing card must be a clear user-facing error')
board.command=lambda *args,**kwargs:(_ for _ in ()).throw(RuntimeError('SD initialization error=-2'))
try:board.sd_info({'binary_path':'/tmp/sd','binary_sha256':'0'*64})
except recorder.SDCardNotPresentError:raise AssertionError('Do not mislabel other SD faults as card absent')
except RuntimeError:pass
else:raise AssertionError('Other SD faults must not be swallowed')
print('VOICE_SD_PC_WORKFLOW_PASS: bound volume, manual import selection, absent-card message, other errors retained')
