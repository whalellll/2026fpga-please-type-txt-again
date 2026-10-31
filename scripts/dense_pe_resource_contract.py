"""Require an exact native PE footprint for each supported output profile."""
import re

def dense_pe_resource_contract(report,top):
    declared=re.findall(r'\.HALF_OUTPUT\s*\(\s*([^()]*)\)',top)
    assert len(declared)<=1,'Ambiguous dense output profile'
    profile=int(declared[0]) if declared else 0
    assert profile in (0,1,2),'Unsupported dense output profile'
    expected={0:160,1:80,2:40}[profile]
    rows=[]
    for line in report.splitlines():
        fields=line.split('|')
        if len(fields)>=8 and re.fullmatch(r'\s*\d+\s*',fields[2]):
            label=fields[1].strip().removeprefix('+').strip()
            if label=='pe':rows.append(float(fields[5]))
    assert rows==[float(expected)],('Native dense PE footprint differs',profile,expected,rows)
    return dict(profile=profile,apm=expected,output_groups=1<<profile)
