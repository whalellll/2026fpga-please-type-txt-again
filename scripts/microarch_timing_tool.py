"""Microarchitecture timing workbench: bound path analysis and isolated edits.

Uses generated RTL hierarchy and lexical Chisel source hints, not a Scala compiler.
Never writes the source tree, invokes PDS, programs hardware, or certifies timing.
"""
import argparse
import difflib
import gzip
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import subprocess

VERSION = '0.1.0'
NUMBER = r'[-+]?(?:\d+(?:\.\d*)?|\.\d+)'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def child(root, name):
    require(isinstance(name, str) and name and '\\' not in name and ':' not in name,
            'Unsafe relative source path')
    parts = PurePosixPath(name)
    require(not parts.is_absolute() and all(p not in ('', '.', '..') for p in name.split('/')),
            'Unsafe relative source path')
    target = root.joinpath(*parts.parts)
    require(root in target.resolve().parents, 'Source path escapes root')
    for part in (target, *target.parents):
        if part == root:
            break
        require(not part.is_symlink(), 'Symlink source refused')
    return target


def parse_report(text, clock=None):
    """Read PDS detailed sequential paths; clock tree loads are excluded."""
    text = text.replace('\r', '')
    starts = list(re.finditer(r'(?m)^\s*Startpoint\s*:', text))
    require(starts, 'No detailed timing paths')
    paths = []
    for i, match in enumerate(starts):
        block = text[match.start():starts[i+1].start() if i+1<len(starts) else len(text)]

        def field(pattern, numeric=False):
            found = re.search(pattern, block, re.M)
            require(found is not None, 'Incomplete timing path: '+pattern)
            value = float(found[1]) if numeric else found[1]
            require(not numeric or math.isfinite(value), 'Nonfinite timing number')
            return value

        group = field(r'^\s*Path Group\s*:[ \t]*(\S+)')
        require(group not in ('Path', 'Endpoint'), 'Missing path clock group')
        if clock is not None and group!=clock:
            continue
        point = field(r'^\s*Startpoint\s*:\s*(\S+)')
        endpoint = field(r'^\s*Endpoint\s*:\s*(\S+)')
        corner = field(r'^\s*Path Type\s*:\s*(?:max|min)\s*\((\w+) corner\)')
        kind = field(r'^\s*Path Type\s*:\s*(max|min)')
        slack = field(r'^\s*Slack\s*\([^)]*\)\s+('+NUMBER+r')\s*$', True)
        levels = int(field(r'Logic Levels:\s*(\d+)'))
        logic = field(r'Logic:\s*('+NUMBER+r')ns', True)
        route = field(r'Route:\s*('+NUMBER+r')ns', True)
        skew = field(r'^\s*Clock Skew\s*:\s*('+NUMBER+r')', True)
        require(logic>=0 and route>=0, 'Negative path delay')
        cells, nets, active = [], [], False
        for line in block.splitlines():
            if re.search(r'\bData arrival time\b', line):
                break
            if re.search(r'\btco\b', line):
                active = True
            if not active:
                continue
            net = re.search(r'net\s*\(fanout=(\d+)\)\s+('+NUMBER+r')\s+('+NUMBER+r')\s+(.+?)\s*$', line)
            if net:
                nets.append(dict(fanout=int(net[1]),delay_ns=float(net[2]),arrival_ns=float(net[3]),resource=net[4]))
                continue
            cell = re.search(r'\b(?:td|tco)\s+('+NUMBER+r')\s+('+NUMBER+r')\s+[rf]\s+(.+?)\s*$',line)
            if cell:
                cells.append(dict(delay_ns=float(cell[1]),arrival_ns=float(cell[2]),resource=cell[3]))
        require(active and cells and nets, 'Unsupported or incomplete sequential data path')
        paths.append(dict(id=i,startpoint=point,endpoint=endpoint,clock_group=group,corner=corner,
                          delay_type=kind,slack_ns=slack,logic_levels=levels,logic_ns=logic,route_ns=route,
                          route_fraction=route/(logic+route) if logic+route else 0,skew_ns=skew,
                          max_data_fanout=max(n['fanout'] for n in nets),data_cells=cells,data_nets=nets))
    return paths


def strip_comments(text):
    return re.sub(r'/\*.*?\*/|//[^\n]*', lambda m:'\n'*m[0].count('\n'),text,flags=re.S)


def rtl_hierarchy(text):
    blocks = {}
    for match in re.finditer(r'\bmodule\s+(\w+)\b(.*?)\bendmodule\b',strip_comments(text),re.S):
        require(match[1] not in blocks, 'Duplicate RTL module '+match[1])
        blocks[match[1]] = match[2]
    require(blocks, 'No generated RTL modules')
    names = '|'.join(re.escape(x) for x in sorted(blocks,key=len,reverse=True))
    instance = re.compile(r'\b('+names+r')\s+(\\[^\s]+|\w+)\s*\(')
    result={}
    for name,body in blocks.items():
        result[name]={m[2].lstrip('\\'):m[1] for m in instance.finditer(body)}
        result[name]['__signals__']=set(re.findall(r'\b(?:input|output|wire|reg)\s+(?:(?:wire|reg|signed)\s+)*(?:\[[^\]]+\]\s*)?(\w+)',body))
    return result


def resolve_resource(resource, hierarchy, top, root_instance='core'):
    parts = resource.replace('\\','').split('/')
    if root_instance not in parts or top not in hierarchy:
        return None
    index = parts.index(root_instance)+1
    module = hierarchy[top].get(root_instance,top)
    while index<len(parts) and parts[index] in hierarchy.get(module,{}):
        module=hierarchy[module][parts[index]]
        index+=1
    if index>=len(parts):
        return None
    leaf=parts[index].strip()
    base=re.split(r'[\[\s]',leaf)[0]
    if base not in hierarchy[module]['__signals__']:
        return None
    return module,leaf


def scala_declarations(text):
    """Conservative lexical hints: nested scopes are not resolved or proven."""
    clean = strip_comments(text)
    result = {}
    for match in re.finditer(r'\bval\s+(\w+)\s*(?::[^=\n]+)?\s*=\s*', clean):
        start=match.end()
        tail=clean[start:]
        lines=tail.splitlines(keepends=True)
        expression=''
        for line in lines[:32]:
            expression+=line
            balance=sum(expression.count(c) for c in '([{')-sum(expression.count(c) for c in ')]}')
            if balance<=0:
                break
        expression=expression.strip()
        kind = ('register' if re.search(r'\bReg(?:Init|Next|Enable)?\s*\(',expression) else
                'memory' if re.search(r'\b(?:SyncReadMem|Mem)\s*\(',expression) else 'combinational_hint')
        row=dict(name=match[1],line=clean.count('\n',0,match.start())+1,kind=kind,
                 expression=expression[:1600],identifiers=sorted(set(re.findall(r'\b[A-Za-z_]\w*\b',expression))),
                 ambiguous=match[1] in result)
        if match[1] in result:
            row['ambiguous']=True
        result[match[1]]=row
    return result


def source_snapshot(cpu_root, commit):
    """Bind every main Scala source to the frozen CPU Git commit."""
    command=['git','-C',str(cpu_root),'ls-tree','-rz',commit,'--','cpu/src/main/scala']
    data=subprocess.run(command,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE).stdout
    files={}
    for record in data.split(b'\0'):
        if not record:
            continue
        metadata,name=record.split(b'\t',1)
        relative=name.decode('utf-8')
        if not relative.endswith('.scala'):
            continue
        mode,kind,blob=metadata.decode().split()
        require(mode=='100644' and kind=='blob','Unsupported CPU source entry')
        raw=child(cpu_root,relative).read_bytes()
        require(hashlib.sha1(('blob '+str(len(raw))+'\0').encode()+raw).hexdigest()==blob,
                'CPU source differs from frozen commit: '+relative)
        files[relative]=digest(raw)
    actual={p.relative_to(cpu_root).as_posix() for p in (cpu_root/'cpu/src/main/scala').rglob('*.scala')}
    require(files and set(files)==actual,'CPU source inventory differs from frozen commit')
    return files


def analyze(project_root,cpu_root,report,binding,snapshot,output,clock='cpu_clk',fanout_threshold=32):
    require(not output.exists(),'Analysis output already exists')
    identity,record=load(snapshot),load(binding)
    require(record.get('formal_run_id')==identity['run_id'],'Report and snapshot run mismatch')
    require(record.get('original_files_unchanged') is True,'Timing replay source was not preserved')
    raw=report.read_bytes()
    require(record.get('files_sha256',{}).get(report.name)==digest(raw),'Detailed report hash mismatch')
    rtl_path=project_root/'rtl/cpu/CoreTop.sv'
    source_path=project_root/'rtl/cpu/source.json'
    rtl,metadata=rtl_path.read_bytes(),load(source_path)
    for name,data in [('rtl/cpu/CoreTop.sv',rtl),('rtl/cpu/source.json',source_path.read_bytes())]:
        require(identity['inputs'].get(name)==digest(data),'Frozen project source mismatch: '+name)
    require(metadata['sha256']==digest(rtl),'CPU generated RTL identity mismatch')
    files=source_snapshot(cpu_root,metadata['source_reference_commit'])
    report_text=gzip.decompress(raw).decode('utf-8') if report.suffix=='.gz' else raw.decode('utf-8')
    paths=parse_report(report_text,clock)
    require(paths,'No paths for requested clock')
    expected={(p['startpoint'],p['endpoint'],p['corner'],p['delay_type']):p for p in record['paths'] if p['clock_group']==clock}
    observed={(p['startpoint'],p['endpoint'],p['corner'],p['delay_type']):p for p in paths}
    require(len(observed)==len(paths) and set(observed)==set(expected),'Detailed path inventory differs from replay receipt')
    for key,row in observed.items():
        require(abs(row['slack_ns']-expected[key]['slack_ns'])<1e-6 and row['logic_levels']==expected[key]['logic_levels'],
                'Detailed path values differ from replay receipt')
    hierarchy=rtl_hierarchy(rtl.decode('utf-8'))
    sources={}
    for relative in files:
        text=child(cpu_root,relative).read_text(encoding='utf-8')
        declarations=scala_declarations(text)
        for name in re.findall(r'\bclass\s+(\w+)\b',strip_comments(text)):
            sources.setdefault(name,[]).append((relative,declarations))
    units={}
    for path in paths:
        hints=[]
        unit_chain=[]
        ordered=sorted(path['data_nets']+path['data_cells'],key=lambda row:row['arrival_ns'])
        resources=[path['startpoint']]+[row['resource'] for row in ordered]+[path['endpoint']]
        for resource in resources:
            resolved=resolve_resource(resource,hierarchy,metadata.get('module','CoreTop'))
            if resolved is None:
                continue
            module,leaf=resolved
            base=re.sub(r'_unq\d+$','',module)
            options=sources.get(base,[])
            if len(options)!=1:
                continue
            if not unit_chain or unit_chain[-1]!=module:
                unit_chain.append(module)
            relative,declarations=options[0]
            unit=units.setdefault(module,dict(module=module,source=relative,path_ids=[],state_hints=[],source_sha256=files[relative]))
            if path['id'] not in unit['path_ids']:
                unit['path_ids'].append(path['id'])
            if not unit['state_hints']:
                unit['state_hints']=[dict(name=d['name'],line=d['line'],kind=d['kind']) for d in declarations.values() if d['kind'] in ('register','memory') and not d['ambiguous']]
            symbol=re.split(r'[\[\s]',leaf)[0]
            if symbol not in declarations:
                symbol=re.sub(r'_\d+$','',symbol)
            definition=declarations.get(symbol)
            if definition and not definition['ambiguous']:
                dependencies=[n for n in definition['identifiers'] if n in declarations and not declarations[n]['ambiguous'] and n!=symbol]
                hint=dict(module=module,source=relative,resource=resource,symbol=symbol,
                          definition=definition,local_dependencies=dependencies,evidence='RTL_HIERARCHY_PLUS_LEXICAL_SOURCE_HINT_NOT_ELABORATED_EQUIVALENCE')
                if not any(h['module']==module and h['symbol']==symbol for h in hints):
                    hints.append(hint)
        path['source_hints']=hints
        path['unit_chain']=unit_chain
        candidates=[]
        if path['max_data_fanout']>=fanout_threshold:
            net=max(path['data_nets'],key=lambda n:n['fanout'])
            candidates.append(dict(strategy='replicate_or_partition_consumers',target_net=net['resource'],
                                   reason=f"observed data fanout {net['fanout']}; route fraction {path['route_fraction']:.3f}",
                                   obligations=['Confirm actual consumers and preserve timing registers','Budget replicas and control/reset loads','Recheck mapped replicas, placement and final STA']))
        if path['logic_levels']>=2:
            candidates.append(dict(strategy='pipeline_two_stage',scope='logic chain or entire mapped unit',
                                   reason=f"{path['logic_levels']} reported logic levels; cut and balance actual delays",
                                   source_candidates=[dict(module=h['module'],symbol=h['symbol'],line=h['definition']['line'],source=h['source']) for h in hints if h['definition']['kind']=='combinational_hint'],
                                   obligations=['Align data/control/valid/transaction identity','Update ready/valid, backpressure, forwarding, flush, exceptions and reset','Measure added latency, initiation interval, workload cycles and performance budget','Final all-corner STA and board acceptance required']))
        if any(len(h['local_dependencies'])>=2 for h in hints):
            candidates.append(dict(strategy='shorten_control_or_arbitration_chain',
                                   reason='source hints show coupled select/readiness dependencies; inspect priority and early preparation',
                                   obligations=['Preserve arbitration semantics and timing register boundaries','Do not increase control fanout or move logic to a slower input cone']))
        path['optimization_candidates']=candidates
    require(units,'No source-mapped units; unsupported hierarchy/source profile')
    paths.sort(key=lambda p:p['slack_ns'])
    result=dict(schema=1,tool_version=VERSION,status='MICROARCHITECTURE_ANALYSIS_NOT_OPTIMIZED_OR_VALIDATED',
                project_root=str(project_root),cpu_root=str(cpu_root),run_id=identity['run_id'],
                cpu_commit=metadata['source_reference_commit'],cpu_source_files=files,
                inputs=dict(report=str(report),report_sha256=digest(raw),binding_sha256=digest(binding.read_bytes()),
                            snapshot_sha256=digest(snapshot.read_bytes()),rtl_sha256=digest(rtl),tool_sha256=digest(Path(__file__).read_bytes())),
                clock=clock,path_count=len(paths),paths_without_source_hints=sum(not p['source_hints'] for p in paths),
                other_clock_paths_not_analyzed=len(re.findall(r'(?m)^\s*Startpoint\s*:',report_text))-len(paths),
                worst_slack_ns=paths[0]['slack_ns'],units=list(units.values()),paths=paths,
                threshold_scope='fanout threshold prioritizes suggestions; it is not a timing pass/fail limit',
                limits=['Generated RTL hierarchy supports named, unparameterized module instances; unmapped hierarchy is not guessed.',
                        'Chisel parsing is lexical: nested scope ambiguity is excluded; source dependencies are hints, not compiler IR or equivalence.',
                        'Optimization candidates are engineering plans; no resource/timing/functional improvement has been proven.'],
                functional_validated=False,timing_validated=False,board_validated=False)
    output.mkdir(parents=True)
    save(output/'analysis.json',result)
    template=dict(schema=1,strategy='logic_rewrite',reason='Describe the selected microarchitecture change',edits=[],
                  example_edit={'path':'cpu/src/main/scala/.../Unit.scala','replacements':[{'before':'exact original source','after':'reviewed new source'}]},
                  latency_contract={'added_cycles':1,'controls':'Describe all control/data/handshake/flush changes if splitting stages','validation':'Describe transaction, cycle, throughput and STA checks'})
    save(output/'edit-spec.template.json',template)
    lines=['# Microarchitecture timing analysis','',f"Run: `{result['run_id']}`; CPU: `{result['cpu_commit']}`.",
           f"Detailed paths: {len(paths)}; worst slack: {result['worst_slack_ns']:.3f} ns.",
           '', 'Status: source-mapped analysis and unvalidated optimization plans.', '',
           '| Path | Slack ns | Levels | Data fanout | Route % | Mapped units |',
           '|---|---:|---:|---:|---:|---|']
    for p in paths:
        lines.append(f"| {p['id']} | {p['slack_ns']:.3f} | {p['logic_levels']} | {p['max_data_fanout']} | {p['route_fraction']*100:.1f} | {' → '.join(p['unit_chain'])} |")
    for p in paths[:10]:
        lines += ['',f"## Path {p['id']}: {p['startpoint']} → {p['endpoint']}",'']
        for h in p['source_hints']:
            target=child(cpu_root,h['source']).as_posix()
            lines.append(f"- [{h['module']}.{h['symbol']}]({target}:{h['definition']['line']}): `{h['definition']['expression'].splitlines()[0]}`")
        for suggestion in p['optimization_candidates']:
            lines.append(f"- Candidate `{suggestion['strategy']}`: {suggestion['reason']}")
    lines += ['', 'Source hints are lexical and may omit implicit Chisel control dependencies. No automatic pipeline correctness claim.','']
    (output/'report.md').write_text('\n'.join(lines),encoding='utf-8')
    return result


def replication_spec(analysis,request):
    """Generate a narrow Chisel expression-replication rewrite with explicit consumers.

    This is not arbitrary Scala AST rewriting or automatic sequential retiming.
    The named val must have a single-line, directly declared combinational RHS.
    """
    root=Path(analysis['cpu_root']).resolve()
    name=request['path']
    path=child(root,name)
    raw=path.read_bytes()
    require(analysis['cpu_source_files'].get(name)==digest(raw),'Stale/unbound replication source')
    text=raw.decode('utf-8')
    symbol=request['symbol']
    declarations=scala_declarations(text)
    declaration=declarations.get(symbol)
    require(declaration and not declaration['ambiguous'] and declaration['kind']=='combinational_hint',
            'Replication requires a unique combinational val; registers need a complete reviewed edit')
    require(re.search(r'^\s*import\s+chisel3\._\s*$',text,re.M),'Chisel dontTouch import is not available')
    matches=list(re.finditer(r'(?m)^([ \t]*)val[ \t]+'+re.escape(symbol)+r'[ \t]*=[ \t]*([^\r\n]+)(\r?\n|$)',text))
    require(len(matches)==1,'Replication requires a single-line val declaration')
    match=matches[0]
    indent,expression,newline=match[1],match[2],match[3] or '\n'
    require(not any(c in expression for c in '{};') and not re.search(r'\b(?:Reg\w*|Mem|SyncReadMem|new|when|assert|printf|stop)\b',expression),
            'Unsupported stateful/compound replication expression')
    calls=set(re.findall(r'\b(\w+)\s*\(',expression))
    require(calls <= set(declarations)|{'Mux','Cat','Fill','VecInit'},'Unknown Scala call in replication expression')
    groups=request.get('groups',[])
    require(len(groups)>=2,'Replication requires at least two explicit consumer groups')
    require(bool(request.get('reason','').strip()),'Missing replication reason')
    addition=''
    replacements=[]
    names=set(declarations)
    anchors=set()
    for group in groups:
        newname=group['name']
        require(re.fullmatch(r'[A-Za-z_]\w*',newname) and newname not in names,'Replica name exists or is invalid')
        names.add(newname)
        addition+=f'{indent}val {newname} = {expression}{newline}{indent}dontTouch({newname}){newline}'
        consumers=group.get('consumers')
        require(isinstance(consumers,list) and consumers,'Missing explicit consumer anchors')
        for anchor in consumers:
            require(isinstance(anchor,str) and anchor and text.count(anchor)==1 and anchor not in anchors,
                    'Missing, ambiguous or repeated consumer anchor')
            require(anchor not in match[0] and match[0] not in anchor,'Declaration cannot be a consumer anchor')
            changed,count=re.subn(r'\b'+re.escape(symbol)+r'\b',newname,anchor)
            require(count>0,'Consumer does not reference original symbol')
            anchors.add(anchor)
            replacements.append(dict(before=anchor,after=changed))
    replacements.insert(0,dict(before=match[0],after=match[0]+addition))
    return dict(schema=1,strategy='replicate_or_partition_consumers',reason=request['reason'],
                edits=[dict(path=name,replacements=replacements)],
                transformation='Duplicate the direct expression with dontTouch intent and retarget only explicit consumers.',
                retention_limit='dontTouch intent and source replicas do not prove separate mapped cells or reduced physical fanout.')


def stage_edits(analysis,spec,output):
    """Apply exact, reviewed edits to a fresh source preview and unified patch."""
    root=Path(analysis['cpu_root']).resolve()
    require(not output.exists(),'Candidate output already exists')
    resolved=output.resolve()
    for source_root in (root,Path(analysis.get('project_root',root)).resolve()):
        require(resolved!=source_root and source_root not in resolved.parents and resolved not in source_root.parents,
                'Candidate output must be separate from frozen source trees')
    require(spec.get('strategy') in ('logic_rewrite','replicate_or_partition_consumers','pipeline_two_stage'), 'Unknown edit strategy')
    require(bool(spec.get('reason','').strip()),'Missing change reason')
    edits=spec.get('edits')
    require(isinstance(edits,list) and edits,'No concrete source edits')
    if spec['strategy']=='pipeline_two_stage':
        contract=spec.get('latency_contract',{})
        require(type(contract.get('added_cycles')) is int and contract['added_cycles']>=1 and
                bool(contract.get('controls')) and bool(contract.get('validation')),'Missing pipeline latency/control contract')
    source_files=analysis['cpu_source_files']
    originals={}
    for name,expected in source_files.items():
        path=child(root,name)
        require(path.is_file(),'Missing bound CPU source: '+name)
        data=path.read_bytes()
        require(digest(data)==expected,'Stale CPU source: '+name)
        originals[name]=data
    changes={}
    for edit in edits:
        name=edit['path']
        child(root,name)
        require(name in originals and name not in changes,'Unbound or repeated source edit: '+name)
        before=originals[name].decode('utf-8')
        after=before
        replacements=edit.get('replacements')
        require(isinstance(replacements,list) and replacements,'No replacement context')
        for replace in replacements:
            old,new=replace['before'],replace['after']
            require(isinstance(old,str) and isinstance(new,str) and old and old!=new,'Empty/noop replacement')
            require(after.count(old)==1,'Missing or ambiguous replacement context')
            after=after.replace(old,new,1)
        original_decls=scala_declarations(before)
        new_decls=scala_declarations(after)
        protected={n:d['kind'] for n,d in original_decls.items() if d['kind'] in ('register','memory')}
        for name_,kind in protected.items():
            require(name_ in new_decls and new_decls[name_]['kind']==kind,
                    'Protected register/memory declaration removed: '+name_)
        changes[name]=(after.encode('utf-8'),protected)
    patch=''
    for name,(after,_) in changes.items():
        for line in difflib.unified_diff(originals[name].decode().splitlines(keepends=True),
                                        after.decode().splitlines(keepends=True),fromfile='a/'+name,tofile='b/'+name):
            patch+=line if line.endswith('\n') else line+'\n\\ No newline at end of file\n'
    require(patch,'No source change')
    output.mkdir(parents=True)
    for name,(after,_) in changes.items():
        path=child(output/'source',name)
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(after)
    (output/'candidate.patch').write_bytes(patch.encode('utf-8'))
    save(output/'edit-spec.json',spec)
    result=dict(schema=1,status='EDIT_CANDIDATE_NOT_GENERATED_OR_VALIDATED',tool_version=VERSION,
                strategy=spec['strategy'],reason=spec['reason'],source_root=str(root),run_id=analysis.get('run_id'),
                cpu_commit=analysis.get('cpu_commit'),patch_sha256=digest(patch.encode()),
                files={name:dict(before_sha256=digest(originals[name]),after_sha256=digest(data),
                                protected_declaration_hints=protected) for name,(data,protected) in changes.items()},
                checks=['Source hashes and unique replacement contexts verified','Existing lexical register/memory declarations retained'],
                required_validation=['Review complete affected data/control and source semantics','Generate paired RTL in an isolated candidate; verify actual registers/copies and resources',
                                     'Targeted transaction/latency/flush/backpressure regression and full CPU/SoC tests',
                                     'Compare workload cycles/throughput and existing performance contract','Final all-corner STA, independent review and board acceptance'],
                functional_validated=False,timing_validated=False,board_validated=False,
                limits='Lexical state-name preservation is not sequential equivalence or proof that mapped timing boundaries survive.')
    save(output/'candidate.json',result)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version',action='version',version=VERSION)
    commands=parser.add_subparsers(dest='command',required=True)
    p=commands.add_parser('analyze',help='Bind native paths to generated hierarchy and frozen Chisel sources')
    for name in ('project-root','cpu-root','report','binding','snapshot','output'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--clock',default='cpu_clk')
    p.add_argument('--fanout-threshold',type=int,default=32)
    p=commands.add_parser('edit',help='Stage exact microarchitecture source edits and a patch, leaving originals unchanged')
    for name in ('analysis','spec','output'):
        p.add_argument('--'+name,type=Path,required=True)
    p=commands.add_parser('replicate',help='Duplicate a supported Chisel expression for explicit consumer groups')
    for name in ('analysis','request','output'):
        p.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    try:
        if args.command=='analyze':
            require(args.fanout_threshold>0,'Fanout threshold must be positive')
            result=analyze(args.project_root.resolve(),args.cpu_root.resolve(),args.report.resolve(),
                           args.binding.resolve(),args.snapshot.resolve(),args.output.resolve(),args.clock,args.fanout_threshold)
            print(json.dumps(dict(status=result['status'],paths=result['path_count'],units=len(result['units']),worst_slack_ns=result['worst_slack_ns'])))
        else:
            analysis=load(args.analysis)
            spec=replication_spec(analysis,load(args.request)) if args.command=='replicate' else load(args.spec)
            result=stage_edits(analysis,spec,args.output.resolve())
            print(json.dumps(dict(status=result['status'],files=len(result['files']),patch_sha256=result['patch_sha256'])))
    except (ValueError,OSError,KeyError,subprocess.SubprocessError) as error:
        parser.exit(2,'MICROARCH_TOOL_ERROR: '+str(error)+'\n')


if __name__=='__main__':main()
