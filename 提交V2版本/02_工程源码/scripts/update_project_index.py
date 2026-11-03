"""Maintain a shallow directory inventory without traversing builds or datasets."""
import argparse
from datetime import datetime, timezone
import fnmatch
import hashlib
import json
from pathlib import Path


CATALOG = 'scripts/project_directory_catalog.json'
INVENTORY = 'docs/validation/project-directory-inventory.json'
INDEX = 'docs/Project_Directory_Index.md'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render(snapshot):
    lines = [
        '# 工程目录索引与简介', '',
        '本索引覆盖当前 SoC 工程及其所在工作区。只扫描一级目录，不扫描数据集、模型或 PDS 数据库。',
        '生成信息是目录快照，不能作为时序、板测或交付通过的证据。', '',
        '## 从哪里开始', '',
        '- 当前频率、候选、失败原因和恢复步骤：[CPU/SoC 交接](CPU_Frequency_Handoff.md)。',
        '- 提频及验收：[固定流程](FPGA_CPU_Frequency_Optimization_Workflow.md)。',
        '- 语音数据集录制：双击工程根目录 [批量录制](../Start_Voice_Batch_Recorder.cmd)；[普通录制](../Start_Voice_Recorder.cmd)。',
        '- 交付完成判定、整理规则与命令：[目录维护与清理](Project_Directory_Maintenance.md)。',
        '- 首先阅读工程根目录的 AGENTS.md；目录清理必须保持实际模型与构建来源可追溯。', '',
        '## 当前 SoC 工程', '',
        f"扫描工程：`{snapshot['project_root']}`。随包目录按交付白名单确定，本表不扩大打包范围。", '',
        '| 目录 | 简介 | 维护方式 | 扫描时存在 |', '|---|---|---|---|'
    ]
    for item in snapshot['project_directories']:
        lines.append(f"| `{item['name']}/` | {item['role']} | {item['policy']} | {'是' if item['exists'] else '否'} |")
    lines += ['', '## 工作区入口与历史目录', '',
              f"扫描工作区：`{snapshot['workspace_root']}`。下列路径相对该工作区，迁移后重新生成。", '',
              '| 用途 | 实际目录 | 保留/清理原则 |', '|---|---|---|']
    for group in snapshot['workspace_groups']:
        names = '、'.join('`' + name + '/`' for name in group['names'])
        lines.append(f"| {group['role']} | {names} | {group['policy']} |")
    if snapshot['unclassified_directories']:
        lines += ['', '### 待补充简介的目录', '', '、'.join('`' + x + '/`' for x in snapshot['unclassified_directories']),
                  '', '未知目录先保留；确认用途后修改 scripts/project_directory_catalog.json。']
    lines += ['', '## 工作区根文件', '',
              '根文件不自动移动。zip、sha256、备份、安装程序及仓库元数据分别保留其原路径；旧交付包需核对版本与引用后另行归档。', '',
              '、'.join('`' + x + '`' for x in snapshot['workspace_files']), '',
              '## 自动维护', '',
              '维护源：`scripts/project_directory_catalog.json`；快照：`docs/validation/project-directory-inventory.json`。',
              '打包前 create_delivery.ps1 自动刷新；verify_delivery.ps1 在解包后核对目录索引与快照一致。',
              '每次任务完成后先记录结论，再检查清理计划，归档校验后执行，并重新刷新索引。', '',
              f"快照时间：{snapshot['updated_utc']}；目录索引工具不会启动 PnR、板测、训练或远程推送。", '']
    return '\n'.join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--project-root', type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument('--workspace-root', type=Path)
    ap.add_argument('--check', action='store_true', help='Check stored snapshot/rendering; do not scan a different extraction workspace.')
    a = ap.parse_args()
    root = a.project_root.resolve()
    catalog_path = root / CATALOG
    catalog = json.loads(catalog_path.read_text(encoding='utf-8-sig'))
    if a.check:
        snapshot = json.loads((root / INVENTORY).read_text(encoding='utf-8'))
        if snapshot.get('schema') != 1 or snapshot['catalog_sha256'] != digest(catalog_path):
            raise ValueError('Directory catalog changed; refresh the index before delivery.')
        if (root / INDEX).read_text(encoding='utf-8') != render(snapshot):
            raise ValueError('Directory index differs from its stored inventory; refresh it.')
        print(json.dumps({'status': 'PROJECT_DIRECTORY_INDEX_PASS', 'mode': 'stored_snapshot', 'hardware_acceptance': False}))
        return
    workspace = (a.workspace_root or root.parent).resolve()
    groups = [dict(role=g['role'], policy=g['policy'], names=[]) for g in catalog['workspace_groups']]
    unknown = []
    for path in sorted(workspace.iterdir(), key=lambda p: p.name.casefold()):
        if not path.is_dir():
            continue
        for spec, group in zip(catalog['workspace_groups'], groups):
            if any(fnmatch.fnmatchcase(path.name, pattern) for pattern in spec['patterns']):
                group['names'].append(path.name)
                break
        else:
            unknown.append(path.name)
    project = [dict(name=name, role=value[0], policy=value[1], exists=(root/name).is_dir())
               for name, value in catalog['project_directories'].items()]
    known = set(catalog['project_directories']) | {'.git'}
    for path in sorted(root.iterdir(), key=lambda p: p.name.casefold()):
        if path.is_dir() and path.name not in known:
            project.append(dict(name=path.name, role='待确认用途', policy='保留；补充维护目录简介', exists=True))
    snapshot = dict(schema=1, updated_utc=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                    project_root=root.as_posix(), workspace_root=workspace.as_posix(),
                    catalog_sha256=digest(catalog_path), project_directories=project,
                    workspace_groups=[g for g in groups if g['names']], unclassified_directories=unknown,
                    workspace_files=sorted(p.name for p in workspace.iterdir() if p.is_file()))
    (root / INVENTORY).parent.mkdir(parents=True, exist_ok=True)
    (root / INVENTORY).write_bytes((json.dumps(snapshot, ensure_ascii=False, indent=2)+'\n').encode('utf-8'))
    (root / INDEX).write_bytes(render(snapshot).encode('utf-8'))
    print(json.dumps({'status': 'PROJECT_DIRECTORY_INDEX_UPDATED', 'project_directories': len(project),
                      'unclassified_workspace_directories': unknown, 'hardware_acceptance': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
