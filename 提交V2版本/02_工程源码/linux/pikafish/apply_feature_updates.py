"""Upgrade prepared official source to direct descriptors after pipeline hooks."""
from pathlib import Path
import hashlib
import json
import re
import sys

work, output = map(Path, sys.argv[1:])
source = work/'src/nnue/nnue_accumulator.cpp'
text = source.read_text()
if 'using StageATerms = StageAAccel::FeatureUpdates;' not in text:
    text, n = re.subn(r'struct StageATerms \{.*?\n\};',
                     'using StageATerms = StageAAccel::FeatureUpdates;', text, count=1, flags=re.S)
    assert n == 1
    old = ('return StageAAccel::apply(base, out, terms.rows.data(), terms.coefficients.data(),\n'
           '                              terms.count, view);')
    assert text.count(old) == 1, 'Expected final pipeline view-aware Stage A hook'
    text = text.replace(old, 'return terms.apply(base, out, view);')
    text, n = re.subn(r'StageATerms\s+(terms|cacheTerms|threatTerms);',
                     r'StageATerms \1(featureTransformer.weights.data(), featureTransformer.threatWeights.data());', text)
    assert n == 3, n
    text = text.replace('#include "../pikafish_stagea_accel.h"',
                        '#include "../pikafish_stagea_accel.h"\n    #include "../pikafish_feature_updates.h"')
    source.write_text(text)
assert text.count('StageAAccel::materialize(); // Deferred batch') == 3
assert 'terms.rows' not in text and 'terms.apply(base, out, view)' in text
assert text.count('featureTransformer.threatWeights.data());') == 3
output.write_text(json.dumps(dict(status='DIRECT_FEATURE_DESCRIPTORS_AND_SCALAR_GUARDS_VERIFIED',
    source_sha256=hashlib.sha256(source.read_bytes()).hexdigest()), indent=2)+'\n')
pipeline = output.with_name('pipeline-integration.json')
if pipeline.exists():
    record = json.loads(pipeline.read_text())
    record['hooks']['src/nnue/nnue_accumulator.cpp'] = 'terms.apply(base, out, view)'
    record['patched_sources_sha256']['src/nnue/nnue_accumulator.cpp'] = hashlib.sha256(source.read_bytes()).hexdigest()
    record['direct_feature_updates'] = True
    pipeline.write_text(json.dumps(record, indent=2)+'\n')
print('DIRECT_FEATURE_DESCRIPTORS_AND_SCALAR_GUARDS_VERIFIED')
