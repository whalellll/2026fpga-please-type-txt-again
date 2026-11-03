"""Native convolution resource accounting; no routing or board claim."""
import re


def conv_resource_contract(netlist, report, enabled):
    assert enabled in (0, 1), 'Unknown convolution enable'
    names=re.findall(r'(?m)^module\s+(\w+)\b', netlist)
    for name in ('mac_conv_mmio_frontend','mac_conv_compute_core',
                 'mac_conv_input_dma','mac_conv_weight_dma',
                 'mac_weight_double_buffer','mac_conv_compact_writer'):
        assert names.count(name)==enabled, ('Convolution mapped module presence',name,names.count(name))
    rows=[]
    for line in report.splitlines():
        fields=line.split('|')
        if len(fields)<8 or not re.fullmatch(r'\s*\d+\s*',fields[2]): continue
        label=fields[1].strip().removeprefix('+').strip()
        if re.search(r'(?:^|[./])u_conv$',label):
            rows.append(dict(lut=float(fields[2]),ff=float(fields[3]),
                             lutram=float(fields[4]),apm=float(fields[5]),drm=float(fields[6])))
    assert len(rows)==enabled, ('Convolution SNR subtree missing/duplicated',rows)
    if not enabled:return dict(lut=0,ff=0,lutram=0,apm=0,drm=0)
    result=rows[0]
    assert result['lut']>0 and result['ff']>0 and result['drm']>0, 'Convolution optimized away'
    assert all(x>=0 for x in result.values()),'Negative convolution resource count'
    # The PE uses8APMs; descriptor dimension arithmetic uses6more. The
    # selected compact weight store frees30DRMs; the input line store keeps2.
    assert result['apm']==14 and result['drm']==2, ('Convolution footprint outside compact profile',result)
    assert result['lutram']>=272, 'Folded two-bank weight storage missing'
    return result
