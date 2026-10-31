"""Reject real mapped SD TX data/enable and RAM write-enable faults in memory.

The frozen native file is never edited. No fault result can certify a build.
"""
from pathlib import Path
import argparse,hashlib,json,re,traceback
from unittest.mock import patch
import check_sd_argument_native as checker
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--baseline',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
a=ap.parse_args();assert not a.output.exists()
vm=a.baseline/'pds/synthesize/soc_top_syn.vm';raw=vm.read_text();digest=checker.sha(vm)
g=checker.SdGraph(raw);node=g.state[(g.ctx,'cmd_tx_shift[8]')]
body=re.sub(r'/\*.*?\*/|//[^\n]*','',g.h.modules['sd_native_mmio'],flags=re.S)
pattern=r'\b'+re.escape(node['kind'])+r'\s*#\s*\((.*?)\)\s*(\\\S+|\w+)\s*\((.*?)\);'
matches=[m for m in re.finditer(pattern,body,re.S) if re.search(r'\.Q\s*\(\s*cmd_tx_shift\[8\]\s*\)',m[3])]
assert len(matches)==1;cell=matches[0][0]
result={'status':'RUNNING','native_vm_sha256':digest,'checker_sha256':checker.sha(Path(checker.__file__)),'test_sha256':checker.sha(Path(__file__)),'cases':[]}
real=checker.SdGraph
try:
    for label,pin in [('tx-data','D'),('tx-enable','CE')]:
        assert pin in node['ports'];changed=re.sub(r'\.'+pin+r'\s*\([^()]*\)',"."+pin+" (1'b0)",cell,count=1)
        assert changed!=cell
        # The parser source has attributes/comments removed. Apply the exact
        # parsed cell substitution only after that provenance normalization.
        def mutate(text):
            normalized=re.sub(r'\(\*.*?\*\)','',text,flags=re.S)
            normalized=re.sub(r'/\*.*?\*/|//[^\n]*','',normalized,flags=re.S)
            before=re.sub(r'/\*.*?\*/|//[^\n]*','',cell,flags=re.S)
            after=re.sub(r'/\*.*?\*/|//[^\n]*','',changed,flags=re.S)
            assert normalized.count(before)==1
            return normalized.replace(before,after,1)
        count=[0]
        def build(text):
            count[0]+=1
            return real(mutate(text) if count[0]==2 else text)
        error=None
        with patch.object(checker,'SdGraph',side_effect=build):
            try:checker.validate(a.baseline,a.baseline,self_test=True)
            except AssertionError as ex:error=str(ex)
        assert error and 'next_state:' in error and 'cmd_tx_shift[8]' in error,(label,error)
        result['cases'].append(dict(label=label,rejected=True,reason=error[:1800]))
    key=next(iter(g.rams));ram=g.rams[key];kind=g.h.contexts[key[0]][0]
    bank=re.sub(r'/\*.*?\*/|//[^\n]*','',g.h.modules[kind],flags=re.S)
    pattern=r'\bGTP_RAM64X1DP\s*#\s*\((.*?)\)\s*(\\\S+|\w+)\s*\((.*?)\);'
    matches=[m for m in re.finditer(pattern,bank,re.S) if checker.signal(m[2])==ram['name']]
    assert len(matches)==1;cell=matches[0][0];changed=re.sub(r'\.WE\s*\([^()]*\)',".WE (1'b0)",cell,count=1);assert cell!=changed
    # Both bank instances share one module: deliberately corrupt its actual
    # RAM write pin in the candidate graph and require the pin proof to fail.
    count=[0]
    def build(text):
        count[0]+=1
        return real(mutate(text) if count[0]==2 else text)
    error=None
    with patch.object(checker,'SdGraph',side_effect=build):
        try:checker.validate(a.baseline,a.baseline,self_test=True)
        except AssertionError as ex:error=str(ex)
    assert error and 'memory:' in error and ':WE:' in error,error
    result['cases'].append(dict(label='actual-ram-write-enable',rejected=True,reason=error[:1800]))
    assert checker.sha(vm)==digest
    result['status']='SD_NATIVE_THREE_REAL_PIN_FAULTS_REJECTED_NOT_STA_OR_BOARD'
except Exception:result.update(status='FAILED_SD_NATIVE_FAULT_TEST_PRESERVED',error=traceback.format_exc());raise
finally:a.output.write_text(json.dumps(result,indent=2)+'\n');print(result['status'],flush=True)
