"""Verify the sealed CPU70 package inventory and implementation evidence.

Content PASS is not independent regression, final SD media or delivery completion.
"""
from pathlib import Path
import argparse,json
from verify_main70_release import validate,ref
from verify_board_release import safe,sha,need,read

def verify(root,host_gcc):
    root=Path(root).resolve();m=read(root/'MAIN70_DELIVERY.json')
    need(m['schema']==1 and m['status']=='MAIN70_PUBLISHED_IMPLEMENTATION_PACKAGE_FINAL_MEDIA_PENDING' and m['formal_delivery_complete'] is False,'Wrong package identity/scope')
    expected=set(m['files_sha256'])|{'MAIN70_DELIVERY.json'}
    for name,h in m['files_sha256'].items():need(sha(safe(root,name))==h,'Packaged file changed '+name)
    # Generated build outputs are checked by the regression receipt separately.
    # Initial extraction checks every filesystem entry before tests are run.
    result=validate(root,root/'MAIN70_RELEASE.json',host_gcc)
    need(result['run_id']==m['run_id'] and result['bitstream_sha256']==m['bitstream_sha256'],'Seal/implementation differs')
    need(m['publication']['soc_commit']==read(root/'MAIN70_PUBLICATION.json')['soc_commit'],'Publication differs')
    return dict(status='MAIN70_SEALED_CONTENT_PASS_FULL_REGRESSION_AND_FINAL_MEDIA_SEPARATE',files=len(expected),
                source_commit=m['publication']['soc_commit'],formal_delivery_complete=False)

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--root',type=Path,required=True)
    ap.add_argument('--host-gcc',default='G:/fpga/workspace/tools/msys64/mingw64/bin/gcc.exe');ap.add_argument('--output',type=Path)
    a=ap.parse_args();result=verify(a.root,a.host_gcc)
    if a.output:
        need(not a.output.exists(),'Preserve prior receipt');a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
