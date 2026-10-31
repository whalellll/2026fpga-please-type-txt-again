"""Reject changes to real DSP capture, product wiring and used sign bits."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,re,sys

helpers=Path(__file__).resolve().with_name('gui1080_mul');sys.path.insert(0,str(helpers))
from inspect_mul_signed_mapping import apms,audit

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--source',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    assert not a.output.exists();raw=a.source.read_bytes();digest=hashlib.sha256(raw).hexdigest();source=raw.decode()
    match=re.search(r'(?ms)^module Mul\b.*?^endmodule',source);assert match
    body=match[0];cells=apms(body,True);assert len(cells)==4
    positive=audit(source);assert positive['operand_bits_proven']==172 and positive['reconstruction_bits_proven']==32
    cases=[]
    def reject(name,fn,reason=None):
        try:fn()
        except (AssertionError,KeyError) as error:
            if reason:assert reason.lower() in str(error).lower(),(name,str(error))
            cases.append(dict(name=name,rejected=True,reason=str(error)[:250]))
        else:raise AssertionError('Accepted faulty DSP: '+name)
    for name,old,new in [
        ('unregistered-product','.MULT_REG(1)','.MULT_REG(0)'),
        ('extra-input-stage','.X_REG(0)','.X_REG(1)'),
        ('extra-output-stage','.P_REG(0)','.P_REG(1)'),
        ('postadder-enabled','.USE_POSTADD(0)','.USE_POSTADD(1)'),
        ('preadder-enabled','.USE_PREADD(0)','.USE_PREADD(1)'),
        ('simd-enabled','.USE_SIMD(0)','.USE_SIMD(1)'),
        ('capture-disabled','.CEM (io_valid)',".CEM (1'b0)"),
        ('wrong-clock','.CLK (clock)','.CLK (reset)'),
        ('changed-product-reset',".RSTM (1'b0)",'.RSTM (reset)')]:
        assert old in body,(name,old)
        reject(name,lambda old=old,new=new:apms(body.replace(old,new,1),True))
    cell=next(c for c in cells if c['part']=='00')
    ports=cell['ports'];bits=list(reversed(ports['P'][1:-1].split(',')))
    swapped=list(bits);swapped[0],swapped[1]=swapped[1],swapped[0]
    # Preserve all other cells and replace only the first DSP output expression.
    pattern=r'(\.P\s*\()\s*('+r'\{'+r'\s*,\s*'.join(map(re.escape,list(reversed(bits))))+r'\}'+r')\s*(\))'
    bad,count=re.subn(pattern,lambda m:m[1]+'{'+','.join(reversed(swapped))+'}'+m[3],body,count=1)
    assert count==1
    reject('physical-product-low-bits-swapped',lambda:audit(source[:match.start()]+bad+source[match.end():]),'Native mismatch')
    high=next(c for c in cells if c['part']=='10');sign=list(reversed(high['ports']['X'][1:-1].split(',')))[24]
    assert re.fullmatch(r'[A-Za-z_$][\w$]*\[0\]',sign),sign
    clean=re.sub(r'/\*.*?\*/|//[^\n]*','',body,flags=re.S)
    native_cells=list(re.finditer(r'\bGTP_APM_E2\s*#\s*\((.*?)\)\s+(\w+)\s*\((.*?)\);',clean,re.S))
    native=next(m for m in native_cells if m[2]==high['name']);xm=re.search(r'\.X\s*\(([^()]*)\)',native[0]);assert xm
    for name,replacement,reason in [('wrong-used-sign-bit',"1'b0",'Native mismatch'),('unknown-used-sign-bit',"1'bx",'unknown')]:
        changed=xm[1].replace(sign,replacement,1);assert changed!=xm[1]
        part=native[0][:xm.start(1)]+changed+native[0][xm.end(1):]
        bad=clean[:native.start()]+part+clean[native.end():]
        reject(name,lambda bad=bad:audit(source[:match.start()]+bad+source[match.end():]),reason)
    assert len(cases)==12 and hashlib.sha256(a.source.read_bytes()).hexdigest()==digest
    result=dict(status='GUI1080_MUL_POSITIVE_AND_12_NATIVE_FAULTS_REJECTED_NOT_STA_OR_BOARD',cases=cases,native_vm_sha256=digest,
        checker_sha256=hashlib.sha256((helpers/'inspect_mul_signed_mapping.py').read_bytes()).hexdigest(),
        test_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),completed_utc=datetime.now(timezone.utc).isoformat())
    a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(result['status'])

if __name__=='__main__':main()
