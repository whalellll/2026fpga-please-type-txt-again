"""Compose independently proven RAS and PMA boundaries; keep CPU oracle locked."""
from pathlib import Path
import hashlib,json,sys
import audit_voice_nnue75_ads as voice
import audit_cpu85_half_ads as pma

def main():
    source=Path(sys.argv[1]).read_text();proof=pma.prove_boundary(source)
    base=voice.BASE_EVALUATE
    voice.BASE_EVALUATE=pma.scoped_evaluator(source,base)
    try:voice.main()
    finally:voice.BASE_EVALUATE=base
    out=Path(sys.argv[sys.argv.index('--output')+1]);record=json.loads(out.read_text())
    assert record['status']=='PASS'
    record['pma_page_export_contract']=proof
    record['pma_page_adapter_sha256']=hashlib.sha256(Path(pma.__file__).read_bytes()).hexdigest()
    record['integrated60_adapter']={'status':'ACTUAL_PMA_AND_RAS_BOUNDARIES_WITH_UNCHANGED_CPU_ORACLE_PASS','adapter_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    out.write_text(json.dumps(record,indent=2)+'\n');print('INTEGRATED60_NATIVE_PMA_RAS_BOUNDARIES_CPU_ORACLE_PASS')
if __name__=='__main__':main()
