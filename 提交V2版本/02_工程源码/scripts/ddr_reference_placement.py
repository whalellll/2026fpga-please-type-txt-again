"""Reuse verified DDR data-path sites only for unambiguous, identical cell types.

Inputs are native PDS generate_constraint -prim exports and PNR netlists.
PDS exports some cells before the terminal _perm rename in its PNR netlist.
Only that suffix is normalized; packed-cell composition is never guessed.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

PHY = "I_ips_ddr_top/u_ddrphy_top/"
CONES = ("ddrphy_dqs_rddata_align/", "ddrphy_wdata_path_adj/",
         "ddrphy_dfi/", "u_dll_update_n_sync/",
         "ddrphy_data_slice_wrlvl/wrlvl_dqs/")
CRITICAL = ("/ck_dqs_diff[1]/", "/rdvalid_r1/", "/phy_wrdata_r[3]/",
            "/phy_wrdata_d[18]/", "/rddata_r1[39]/", "/wrlvl_dqs/",
            "/u_dll_update_n_sync/")
WRITE_CONTROL = ('/phy_wrdata_en_r[', '/phy_wrdata_mask_r[', '/N642_0/',
                 '/N659[', '/adj_wrdata_mask_3[')


def in_scope(name, scope):
    if not name.startswith(PHY) or not any(c in name for c in CONES):
        return False
    return (scope == "datapath" or (scope in ("registers", "closure") and "/rddata_r1[" in name)
            or (scope == "closure" and any(c in name for c in WRITE_CONTROL))
            or any(c in name for c in CRITICAL))


def canonical(name):
    return re.sub(r"_perm$", "", name)


def unique_index(values):
    result = {}
    for name, value in values.items():
        key = canonical(name)
        if key in result:
            raise ValueError(f"ambiguous cell alias: {key}")
        result[key] = (name, value)
    return result


def parse_sites(text):
    result = {}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.fullmatch(r"def_inst_site \{([^}]+)\} (\S+)(?: (\S+))?(?: -no_check)?", line)
        if not match:
            raise ValueError(f"unexpected placement command: {line}")
        name, site, impl = match.groups()
        if impl == "-no_check":
            impl = None
        if name in result:
            raise ValueError(f"duplicate placement: {name}")
        result[name] = (site, impl)
    return result


def parse_cells(text):
    cells = re.findall(r"(?m)^Inst\n([^;\n]+);([^;\n]+)", text)
    result = dict(cells)
    if len(result) != len(cells):
        raise ValueError("duplicate netlist cell")
    return result


def select_placements(reference, current, reference_cells, current_cells):
    a = unique_index(reference)
    b = unique_index(current)
    old_types = unique_index(reference_cells)
    new_types = unique_index(current_cells)
    result, missing = {}, []
    for key, (old_name, site) in a.items():
        if (key not in b or key not in old_types or key not in new_types or
                old_types[key][1] != new_types[key][1]):
            missing.append(old_name)
            continue
        # PNR constraints consume the mapped name before LUT pin permutation.
        # Native strict validation remains mandatory for each emitted name.
        result[key] = site
    return result, missing


def verify_placements(requested, actual):
    """Require actual post-route sites and implementations, not PCF presence."""
    actual = unique_index(actual)
    for name, placement in requested.items():
        key = canonical(name)
        if (key not in actual or actual[key][1][0] != placement[0] or
                (placement[1] is not None and actual[key][1][1] != placement[1])):
            raise ValueError(f"placement was not honored: {name}: {placement}")
    return len(requested)


def apply_overrides(selected, overrides):
    """Adjust only already matched cells; keep native placement validation mandatory."""
    result = dict(selected)
    index = unique_index(selected)
    for key, (_, placement) in unique_index(overrides).items():
        if key not in index:
            raise ValueError(f"unselected placement override: {key}")
        result[index[key][0]] = placement
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("reference", "current", "reference-netlist", "current-netlist", "output", "audit"):
        parser.add_argument("--" + option, type=Path, required=True)
    parser.add_argument("--scope", choices=("datapath", "registers", "critical", "closure"), default="registers")
    parser.add_argument("--override", type=Path,
                        help="Explicit placement adjustments for already matched cells")
    parser.add_argument("--site-only", action="store_true",
                        help="Fix CLM blocks; let PDS choose compatible internal slots")
    args = parser.parse_args()
    reference = parse_sites(args.reference.read_text())
    current = parse_sites(args.current.read_text())
    reference = {n: s for n, s in reference.items() if in_scope(n, args.scope)}
    selected, missing = select_placements(reference, current,
        parse_cells(args.reference_netlist.read_text()),
        parse_cells(args.current_netlist.read_text()))
    # Require the actual failing sequential cells, in addition to aggregate coverage.
    required = [n for n in reference if any(s in n for s in CRITICAL)]
    keys = {canonical(n) for n in selected}
    if not reference or len(selected) / len(reference) < 0.8 or any(canonical(n) not in keys for n in required):
        raise ValueError("insufficient reference coverage or missing critical register")
    if args.site_only:
        selected = {name: (site, None) for name, (site, _) in selected.items()}
    if args.override:
        selected = apply_overrides(selected, parse_sites(args.override.read_text()))
    lines = ["# Candidate DDR placement from verified banked baseline; no STA exceptions.",
             "# Generated by scripts/ddr_reference_placement.py; mismatched packing omitted."]
    for name, (site, impl) in sorted(selected.items()):
        if not re.fullmatch(r"CLM[AS]_\d+_\d+", site) or (impl is not None and not re.fullmatch(r"[A-Z0-9]+", impl)):
            raise ValueError(f"unexpected data-path site: {name}: {site}:{impl}")
        lines.append(f"def_inst_site {{{name}}} {site}" + (f" {impl}" if impl else ""))
    args.output.write_text("\n".join(lines) + "\n", encoding="ascii")
    audit = dict(scope=args.scope, fixed_implementations=not args.site_only,
                 fixed_implementation_count=sum(impl is not None for _, impl in selected.values()),
                 selected=len(selected), reference=len(reference), missing=missing,
                 critical_registers=len(required), no_check=False,
                 inputs={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (
                     args.reference, args.current, args.reference_netlist, args.current_netlist)},
                 output_sha256=hashlib.sha256(args.output.read_bytes()).hexdigest())
    if args.override:
        audit['inputs'][str(args.override)] = hashlib.sha256(args.override.read_bytes()).hexdigest()
        audit['overridden_positions'] = len(parse_sites(args.override.read_text()))
    args.audit.write_text(json.dumps(audit, indent=2) + "\n")
    print(f"DDR_REFERENCE_PLACEMENT_PASS selected={len(selected)}/{len(reference)} critical={len(required)}")


if __name__ == "__main__":
    main()
