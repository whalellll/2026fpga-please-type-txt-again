"""Reject real mapped data/enable/clock pin faults with the stream native prover."""
from pathlib import Path
import argparse,hashlib,json,re,subprocess,sys
from audit_cpu_ads import Cone

sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--native',type=Path,required=True)
ap.add_argument('--output',type=Path,required=True)
ap.add_argument('--fault-action',choices=['upper-data','low-enable','clock'])
a=ap.parse_args();out=a.output
vm=a.native/'pds/synthesize/soc_top_syn.vm';digest=sha(vm);source=vm.read_text()

if a.fault_action:
    import prove_conv_stream_native as prover
    c=Cone(source,'mac_conv_weight_dma')
    entries={n['name']:n for n,p in c.drivers.values() if p=='Q'}
    target='line_shift[0]' if a.fault_action=='low-enable' else 'upper_fold[0]'
    node=entries[target]
    module=re.search(r'(?ms)^module mac_conv_weight_dma\b.*?^endmodule',source).group()
    pattern=r'\b(GTP_DFF\w*)\s*/\*.*?\*/\s*#\((.*?)\)\s*(\\\S+|\w+)\s*\((.*?)\);'
    matches=[m for m in re.finditer(pattern,module,re.S) if m[3].replace('\\','')==target]
    assert len(matches)==1;cell=matches[0]
    pin={'upper-data':'D','low-enable':'CE','clock':'CLK'}[a.fault_action]
    replacement=node['ports']['Q'] if pin=='D' else "1'b0"
    changed=re.sub(r'\.'+pin+r'\s*\([^()]*\)',lambda _:'.'+pin+' ('+replacement+')',cell.group(),count=1)
    assert changed!=cell.group()
    mutated=source.replace(module,module[:cell.start()]+changed+module[cell.end():],1)
    original=prover.WeightGraph.__init__;calls=0
    def altered(self,text):
        global calls
        calls+=1
        original(self,mutated if calls==2 else text)
    prover.WeightGraph.__init__=altered
    expected={'upper-data':'upper_capture_transition:0','low-enable':'low_capture_transition:0',
              'clock':'capture_clock:upper_fold[0]'}[a.fault_action]
    try:prover.prove(a.native,Path('G:/fpga/c80f1080p6'))
    except AssertionError as error:
        assert expected in str(error) and "'sat'" in str(error),(expected,str(error)[:1200])
        assert sha(vm)==digest
        record=dict(status='REAL_NATIVE_STREAM_PIN_FAULT_REJECTED',case=a.fault_action,
                    actual_mismatch=expected,mutated_vm_sha256=hashlib.sha256(mutated.encode()).hexdigest(),
                    original_vm_sha256=digest,original_native_file_unchanged=True)
        out.write_text(json.dumps(record,indent=2)+'\n');print(record['status']);raise SystemExit(0)
    raise AssertionError('Actual native pin fault was accepted')

out.mkdir(exist_ok=False)
cases=[]
for name in ['upper-data','low-enable','clock']:
    proc=subprocess.run([sys.executable,'-X','utf8',str(Path(__file__).resolve()),'--native',str(a.native),
        '--output',str(out/(name+'.json')),'--fault-action',name],capture_output=True,timeout=240)
    log=out/(name+'.log');log.write_bytes(proc.stdout+proc.stderr)
    assert proc.returncode==0,(name,proc.stdout[-1200:],proc.stderr[-2000:])
    record=json.loads((out/(name+'.json')).read_text());assert record['status']=='REAL_NATIVE_STREAM_PIN_FAULT_REJECTED'
    record['log_sha256']=sha(log);cases.append(record)
assert sha(vm)==digest
result=dict(status='FOLD_ADS_SYNTHETIC_FAULT_REJECTIONS_PASS_NOT_HARDWARE',
    representation='STREAMED_UPPER_FOLD_544_CAPTURE_BITS',cases=cases,native_source_sha256=digest,
    proof_tool_sha256=sha(Path(__file__).with_name('prove_conv_stream_native.py')),test_sha256=sha(Path(__file__)))
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(result['status'])
