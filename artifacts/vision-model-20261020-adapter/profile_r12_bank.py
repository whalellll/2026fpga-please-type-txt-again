"""Audit the frozen 64-line bank and compare nondeployable larger-bank inventories."""
import argparse
import collections
import hashlib
import json
import math
import re
from pathlib import Path

REPO=Path(__file__).resolve().parents[2]


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def load(path):return json.loads(path.read_text(encoding='utf-8'))


def inventory(layers,capacity):
    result=collections.defaultdict(collections.Counter)
    for layer in layers:
        m,k,n=layer['m'],layer['k'],layer['n'];tile=min(256,32*(capacity//math.ceil(min(k,256)/4)))
        counts=collections.Counter(MACs=m*k*n)
        for row in range(0,m,16):
            mt=min(16,m-row)
            for co in range(0,n,tile):
                nt=min(tile,n-co)
                for ci in range(0,k,256):
                    kt=min(256,k-ci);lines=math.ceil(kt/4)
                    assert lines*math.ceil(nt/32)<=capacity
                    counts['jobs']+=1;counts['input_DMA_bytes']+=mt*lines*8
                    counts['weight_DMA_bytes']+=math.ceil(nt/32)*lines*128
                    counts['output_DMA_bytes']+=mt*nt*4
        result[layer['layer'].split('__')[0]].update(counts)
    return {k:dict(v) for k,v in result.items()}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frozen-root',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();frozen=args.frozen_root.resolve()
    if args.out.exists():raise ValueError('fresh receipt required')
    snapshot=load(frozen/'pds/build_snapshot.json');evidence=load(frozen/'artifacts/build_evidence.json')
    paths=['rtl/soc/soc_top.v','rtl/mac_accel/mac_accel_ddr_kernel_top.v','rtl/mac_accel/mac_accel_dma_kernel.v','rtl/mac_accel/MacAccelCore.v']
    for name in paths:assert sha(frozen/name)==snapshot['inputs'][name],name
    top=(frozen/paths[0]).read_text();generic=(frozen/paths[1]).read_text();dma=(frozen/paths[2]).read_text();core=(frozen/paths[3]).read_text()
    assert re.search(r'parameter integer WEIGHT_BANK_LINES\s*=\s*64\b',top)
    assert re.search(r'parameter integer WEIGHT_BANK_LINES\s*=\s*1024\b',generic)
    assert '.WEIGHT_BANK_LINES(WEIGHT_BANK_LINES)' in top and '.WEIGHT_BANK_LINES(WEIGHT_BANK_LINES)' in generic
    assert '(weight_line_count_small > WEIGHT_BANK_LINES)' in dma
    assert 'if (WEIGHT_BANK_LINES == 64) begin : g_compact_weight' in core
    bitstream=frozen/'artifacts/soc_top.sbit'
    assert sha(bitstream)=='e8a037fa676e10f31a994b2f67d35a458586a6669c61800ace53e9edacb97b45'
    netlist=frozen/'pds/synthesize/soc_top_syn.vm';assert sha(netlist)==evidence['synth_vm_sha256']
    text=netlist.read_text(errors='replace')
    compact='Bank1R1W_1_compact \\g_compact_weight.weightBank'
    assert text.count(compact)==1 and 'weightBank_io_raddr[5]' in text
    start=text.index(compact);excerpt=text[start:start+1800]
    assert 'weightBank_io_raddr[5]' in excerpt and 'weightBank_io_raddr[0]' in excerpt
    plan_path=REPO/'docs/validation/picture-p20-combined-20261020/dense-plan-bank64.json'
    plan=load(plan_path);plans={str(c):inventory(plan['layers'],c) for c in (64,128,256,1024)}
    for name,item in plans['64'].items():
        assert item['jobs']==plan['totals'][name]['dense_jobs']
        for capacity in ('128','256','1024'):
            assert plans[capacity][name]['MACs']==item['MACs']
            assert plans[capacity][name]['weight_DMA_bytes']==item['weight_DMA_bytes']
            assert plans[capacity][name]['output_DMA_bytes']==item['output_DMA_bytes']
    scaled={}
    for capacity,models in plans.items():
        counts={field:sum(item[field]*(.208 if name=='classifier' else 1) for name,item in models.items()) for field in ('jobs','MACs','input_DMA_bytes','weight_DMA_bytes','output_DMA_bytes')}
        scaled[capacity]=counts
    baseline=scaled['64']
    for capacity,counts in scaled.items():
        counts['job_reduction_fraction_vs64']=1-counts['jobs']/baseline['jobs']
        counts['deployable_on_E8']=capacity=='64'
    budget=load(REPO/'docs/validation/picture-r09-offline-20261021/training-budget.json')
    base=budget['baseline'];class_cycles=base['classifier_batch211']['busy_cycles']*.208
    scenarios={}
    for side in (640,512,416):
        cycles=base['board']['busy_cycles']+base['detector640']['busy_cycles']*(side/640)**2+class_cycles
        busy=cycles/49500000
        scenarios[str(side)]=dict(conditional_busy_s=busy,host_capture_graph_refine_driver_IPC_s=None,
            conditional_end_to_end_lower_bound_s=busy,end_to_end_s=None,
            remaining_budget_for_all_overheads_at_5s=5-busy,remaining_budget_at_3s=3-busy,
            meets_5s_busy_budget=busy<=5,meets_3s_busy_budget=busy<=3,
            scope='historical bank64 plan, fixed .208 classifier ratio, detector area scaling; no r12 INT8 graphs or board latency')
    result=dict(status='E8_COMPACT64_CONFIRMED_LARGER_BANK_NOT_SOFTWARE_DEPLOYABLE',
        hardware_used=False,new_RTL_or_PDS=False,bitstream_sha256=sha(bitstream),
        frozen_build_run_id=evidence['run_id'],snapshot_sha256=sha(frozen/'pds/build_snapshot.json'),
        source_sha256={name:sha(frozen/name) for name in paths},synthesized_netlist_sha256=sha(netlist),
        actual_weight_bank_lines=64,generic_module_default_lines=1024,bank_line_bytes=128,
        instantiated_bank='Bank1R1W_1_compact; read address bits 5:0',
        descriptor_rule='ceil(cin/4)*ceil(cout/32)<=64 in S8; pixels<=16; cin/cout<=256',
        examples=[dict(cin=256,cout=32,lines=64,accepted=True),dict(cin=256,cout=64,lines=128,accepted=False),
            dict(cin=256,cout=128,lines=256,accepted=False),dict(cin=64,cout=128,lines=64,accepted=True),
            dict(cin=32,cout=256,lines=64,accepted=True)],
        existing_software_already_uses_128_256_output_channels_when_the_joint_limit_allows=True,
        current_zero_RTL_gain_from_raising_capacity=0,
        counterfactual_inventories=plans,counterfactual_planA_fixed_classifier_ratio_0208=scaled,
        counterfactual_warning='128/256/1024 capacities require different hardware; job reductions do not equal speedup. MACs and weight DMA bytes stay unchanged. No cycle extrapolation from job count.',
        budget_scenarios=scenarios,training_512_2_5_to_2_9s_claim_reconciled=False,
        budget_discrepancy='r12 proposal uses detector640 2.798s; bank64 source has 327732335/49500000=6.621s. Its 512 total 2.5-2.9s cannot be combined with this bank64 budget.',
        E_native_end_to_end_measurement='blocked pending v3c exact-int64 graph/tensors; existing640/v1 runs do not count as E',
        latency_waiver_granted=False,production_ready=False)
    args.out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print('R12_BANK_CAPACITY_AUDIT_PASS',json.dumps(scaled))


if __name__=='__main__':main()
