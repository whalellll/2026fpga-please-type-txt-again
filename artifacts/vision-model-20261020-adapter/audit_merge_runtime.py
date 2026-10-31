"""Inventory actual r14 graph shapes, packed residency and main hardware identity."""
import hashlib,json,struct,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[2];B=R/'build/picture-merge-20261023';E=R/'docs/validation/picture-merge-20261023'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def main():
 assert not subprocess.check_output(['git','diff','origin/main','--name-only','--','rtl','ip','pds','config','sw/bootloader'],cwd=R).strip()
 candidate=load(R/'CPU80_CONV_CANDIDATE.json');native=load(R/'docs/validation/cpu80-conv-sdboot-20261022/attempt-03/native-content-verification.json')
 assert candidate['bitstream_sha256']==native['bitstream_sha256'] and native['sta_rows']==116 and native['skew_rows']==20
 models={};reasons={};eligible=[];pointwise=0
 for name in ('board','detector','classifier'):
  data=(B/'native-models'/(name+'.xqm')).read_bytes();h=struct.unpack_from('<10I',data,8);desc=16 if h[0]==2 else 0
  nodes=[struct.unpack_from('<32i',data,48+desc+i*128) for i in range(h[2])];blob=data[48+desc+h[2]*128:]
  total=raw=layer_count=0
  for n in nodes:
   if n[0]!=1:continue
   layer_count+=1;shape=(3,192 if name=='board' else 640 if name=='detector' else 32,192 if name=='board' else 640 if name=='detector' else 32) if n[5]<0 else nodes[n[5]][1:4]
   cin,ih,iw=shape;k=cin*n[10]*n[11];cout=n[1];raw+=k*cout
   step=min(256,32*(64//((min(k,256)+3)//4)))
   for co in range(0,cout,step):
    for ci in range(0,k,256):total+=((min(cout-co,step)+31)//32)*((min(k-ci,256)+3)//4)*128
   if n[10]==n[11]==n[12]==n[13]==1 and not(n[14] or n[15]):pointwise+=1
   reason=None
   if n[25] or cin>4 or cout>16:reason='ABI3_channel_or_linear_limit'
   elif ih>320 or iw>320:reason='ABI3_spatial_limit'
   elif n[10]!=n[11] or n[10] not in (1,3,6) or n[12]!=n[13] or n[12] not in (1,2) or n[14]!=n[15] or n[16]!=1 or n[17]!=1:reason='ABI3_kernel_geometry_limit'
   elif any(struct.unpack_from('<q',blob,n[22]+c*8)[0] for c in range(cout)):reason='ties_even_S16_vs_ABI3_away_S8'
   else:
    for c in range(cout):
     bias=struct.unpack_from('<i',blob,n[21]+c*4)[0];lo=hi=bias
     for q in range(k):
      w=blob[n[20]+c*k+q];w=w if w<128 else w-256;lo+=w*-128 if w>=0 else w*127;hi+=w*127 if w>=0 else w*-128
     if lo< -128 or hi>127:reason='S16_head_not_proven_S8_bounded';break
   if reason:reasons[reason]=reasons.get(reason,0)+1
   else:eligible.append(n[9])
  models[name]=dict(qops=layer_count,raw_S8_weight_bytes=raw,packed_dense_weight_bytes=total,snapshot_fits_1MiB_minus_32KiB=total<=0x100000-32768,residency='whole-model immutable fd snapshot' if name!='detector' else 'per-layer immutable fd snapshot')
 # The main sd-kit describes its candidate explicitly; avoid taking its older
 # accepted base bitstream hash as the CPU80-conv bitstream identity.
 kit=load(R/'artifacts/cpu80_audio_service_20261022/sd-kit/manifest.json')
 assert kit['candidate_bitstream_sha256']==candidate['bitstream_sha256']
 report=dict(status='OFFLINE_INVENTORY_PASS',upstream=subprocess.check_output(['git','rev-parse','origin/main'],cwd=R).decode().strip(),CPU_Hz=80000000,SYS_MAC_Hz=49500000,bitstream_sha256=candidate['bitstream_sha256'],upstream_native_receipt=dict(run_id=native['run_id'],STA_rows=116,skew_rows=20,scope='upstream identity-bound evidence; not Picture_new board validation'),hardware_sources_exact_main=True,physical_scratch=dict(base='0x1b000000',bytes=0x100000,guard='0x1b100000..0x1b1fffff unavailable'),models=models,pointwise_ops_with_direct_NCHW_to_shadow=pointwise,conv_gray_eligible_layers=eligible,conv_rejection_reasons=reasons,conv_default_enabled=False,conv_error_fallback=False,raw_I32_conv_extension_required_for_general_exact_graph=True,residency_warning='per-fd CPU/shadow snapshots are persistent; the single physical aperture is evicted/restored on owner changes, so physical DMA reload/restore is not zero',host_CPU_copy_improvement_measured_on_board=False,independent_DDR_copy_DMA_available=False,new_RTL_or_PDS_run=False,new_board_evidence=False,production_ready=False)
 (E/'runtime-and-main-identity.json').write_text(json.dumps(report,indent=2)+'\n');print('RUNTIME_AUDIT_PASS',models,'gray_eligible',eligible,'direct1x1',pointwise)
if __name__=='__main__':main()
