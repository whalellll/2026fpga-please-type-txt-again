"""Apply every missing official-source pipeline hook and bind the final headers."""
from pathlib import Path
import hashlib,json,re,subprocess,sys
work,patch,output=map(Path,sys.argv[1:])
text=patch.read_text();sections={}
for part in re.split(r'(?=^--- a/)',text,flags=re.M):
 if part.startswith('--- a/'):
  name=part.splitlines()[0][6:];sections[name]=part
hooks={'src/nnue/nnue_feature_transformer.h':'StageBAccel::forward_accumulators',
       'src/nnue/nnue_architecture.h':'StageBAccel::consume_pipeline',
       'src/nnue/nnue_accumulator.cpp':'terms.count, view'}
if 'terms.apply(base, out, view)' in (work/'src/nnue/nnue_accumulator.cpp').read_text():
 hooks['src/nnue/nnue_accumulator.cpp']='terms.apply(base, out, view)'
applied=[]
for name,marker in hooks.items():
 p=work/name
 if marker not in p.read_text():
  subprocess.run(['patch','--batch','--forward','-d',str(work),'-p1'],input=sections[name].encode(),check=True)
  applied.append(name)
 assert marker in p.read_text(),name
assert 'StageBAccel::verify_pipeline' in (work/'src/nnue/nnue_architecture.h').read_text()
accumulator=work/'src/nnue/nnue_accumulator.cpp'
source=accumulator.read_text()
for handled in ('stageAHandled','cacheHandled','threatHandled'):
 pattern=r'(if \(!'+handled+r'\)\s*\{)'
 guard='\n#if defined(PIKAFISH_STAGEA_ACCEL)\n        StageAAccel::materialize(); // Deferred batch must precede scalar reads.\n#endif'
 assert len(re.findall(pattern,source))==1,handled
 if not re.search(pattern+r'\s*#if defined\(PIKAFISH_STAGEA_ACCEL\)\s*StageAAccel::materialize',source):
  source=re.sub(pattern,lambda m:m[0]+guard,source)
accumulator.write_text(source)
assert source.count('StageAAccel::materialize(); // Deferred batch')==3
output.write_text(json.dumps(dict(status='ALL_THREE_NNUE_PIPELINE_HOOKS_VERIFIED',applied=applied,
 batch_scalar_fallback_guards=3,
 hooks=hooks,patched_sources_sha256={n:hashlib.sha256((work/n).read_bytes()).hexdigest() for n in hooks},
 patch_sha256=hashlib.sha256(patch.read_bytes()).hexdigest()),indent=2)+'\n')
print('ALL_THREE_NNUE_PIPELINE_HOOKS_VERIFIED')
