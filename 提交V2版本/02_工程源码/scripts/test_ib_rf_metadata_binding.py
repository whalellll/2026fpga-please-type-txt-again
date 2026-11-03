"""Synthetic tests of the actual CPU audit's source-capability gate.

Native cone proofs are exercised separately on the integrated VM. These fixtures
isolate legacy/new profile selection and source/checker binding; no hardware.
"""
import contextlib,copy,hashlib,io,json,sys,tempfile
from pathlib import Path
from unittest.mock import patch
import audit_cpu_ads as cpu

def main():
    proof=dict(status='IB_RF_METADATA_CAPTURE_ADS_PASS_NOT_STA_OR_BOARD',metadata_storage_bits=64)
    baseline=dict(frontend_cases=0,return_cases=0,pma_address_cases=0,rsmem_hint_cases=0)
    cases=[('legacy',False,None,None,True),('new',True,proof,None,True),
           ('new_missing_proof',True,None,None,False),('legacy_undeclared_proof',False,proof,None,False),
           ('wrong_storage',True,dict(proof,metadata_storage_bits=0),None,False),
           ('cpu_hash',True,proof,'rtl/cpu/CoreTop.sv',False),
           ('checker_hash',True,proof,'scripts/audit_ib_rf_metadata_ads.py',False),
           ('hierarchy_hash',True,proof,'scripts/ads_frontend_ib_cone.py',False)]
    with tempfile.TemporaryDirectory(prefix='ib-rf-source-binding-') as d:
        root=Path(d);(root/'rtl/cpu').mkdir(parents=True);(root/'pds').mkdir()
        rtl=root/'rtl/cpu/CoreTop.sv';snap=root/'pds/build_snapshot.json';vm=root/'pds/fixture.vm';vm.write_text('SYNTHETIC ONLY')
        for label,new,ib,bad,accept in cases:
            rtl.write_text('module CoreTop; '+('wire io_popRfMeta_0; ' if new else '')+'endmodule\n')
            inputs={'rtl/cpu/CoreTop.sv':hashlib.sha256(rtl.read_bytes()).hexdigest(),'rtl/cpu/emit-config.json':'0'*64,'artifacts/bootrom.hex':'0'*64}
            inputs.update({'scripts/'+n:hashlib.sha256(Path(__file__).with_name(n).read_bytes()).hexdigest() for n in ['audit_ib_rf_metadata_ads.py','ads_frontend_ib_cone.py','ads_bdd.py']})
            if bad:inputs[bad]='0'*64
            snap.write_text(json.dumps(dict(inputs=inputs,run_id='synthetic-source-binding',release='V6.4')))
            result=root/(label+'.json');fake=dict(baseline,ib_rf_metadata_contract=copy.deepcopy(ib))
            with patch.object(cpu,'audit',return_value=fake),patch.object(sys,'argv',['audit_cpu_ads.py',str(vm),'--input-snapshot',str(snap),'--output',str(result)]),contextlib.redirect_stdout(io.StringIO()):
                try:cpu.main()
                except ValueError:
                    assert not accept,label
                else:
                    assert accept,label
                    assert json.loads(result.read_text())['ib_rf_metadata_contract']['required']==new,label
    print('IB_RF_METADATA_SOURCE_BINDING_FIXTURES_PASS cases=8 synthetic_only=true hardware_operations=0')

if __name__=='__main__':main()
