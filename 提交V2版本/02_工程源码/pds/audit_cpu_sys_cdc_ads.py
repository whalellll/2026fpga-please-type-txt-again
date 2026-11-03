#!/usr/bin/env python3
"""Fail-closed ADS and FDC audit for the five CPU/SYS AXI FIFOs."""

import argparse
import hashlib
import json
import re
import sys
from decimal import Decimal, ROUND_FLOOR
from pathlib import Path


FIFOS = ("ar", "aw", "w", "r", "b")
PAYLOAD_RAM = {
    "ar": ("sys_clk", 0, 19),
    "aw": ("sys_clk", 1, 18),
    "w": ("sys_clk", 1, 18),
    "r": ("cpu_clk", 0, 18),
    "b": ("cpu_clk", 1, 0),
}
SYNC_FIRST_STAGES = (
    ("cpu_ready_sys0", "cpu_clk", r".*u_axi_cdc/cpu_ready_sys\[1:0\]$",
     "u_cpu/u_cpu_wrapper/u_axi_cdc/cpu_ready_sys[1:0]",
     "axi_cpu_sys_cdc", "cpu_ready_sys", "cpu_ready_sys"),
    ("sys_ready_cpu0", "sys_clk", r".*u_axi_cdc/sys_ready_cpu\[1:0\]$",
     "u_cpu/u_cpu_wrapper/u_axi_cdc/sys_ready_cpu[1:0]",
     "axi_cpu_sys_cdc", "sys_ready_cpu", "sys_ready_cpu"),
    ("timer_c1", "sys_clk", r".*u_irq_sync/timer_c1$",
     "u_cpu/u_cpu_wrapper/u_irq_sync/timer_c1",
     "cpu_irq_sync", "timer_c1", "timer_c2"),
    ("software_c1", "sys_clk", r".*u_irq_sync/software_c1$",
     "u_cpu/u_cpu_wrapper/u_irq_sync/software_c1",
     "cpu_irq_sync", "software_c1", "software_c2"),
)
EXPECTED_CONSTRAINTS = 1171  # Reviewed baseline 1123, Gray 30, payload 10, sync 8.


class AuditError(RuntimeError):
    pass


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require(condition, message):
    if not condition:
        raise AuditError(message)


def module_body(netlist, name):
    match = re.search(
        r"(?ms)^module\s+" + re.escape(name) + r"\s*\n(.*?)^endmodule",
        netlist,
    )
    require(match is not None, "mapped module missing: " + name)
    return match.group(1)


def one_ff(body, name, bit, preserved):
    prefix = r'PAP_PRESERVE="TRUE"[^\n]*' if preserved else ""
    pattern = (
        prefix
        + r"GTP_DFF_[A-Z]+\s*/\*\s*\\"
        + re.escape(name)
        + r"\["
        + str(bit)
        + r"\]"
    )
    matches = list(re.finditer(pattern, body))
    require(
        len(matches) == 1,
        "mapped FF count is %d, expected 1: %s[%d] preserved=%s"
        % (len(matches), name, bit, preserved),
    )
    return matches[0].start()


def one_scalar_ff(body, name):
    pattern = (
        r'PAP_PRESERVE="TRUE"[^\n]*GTP_DFF_[A-Z]+\s*/\*\s*'
        + re.escape(name)
        + r"\s*\*/"
    )
    matches = list(re.finditer(pattern, body))
    require(
        len(matches) == 1,
        "mapped preserved scalar FF count is %d, expected 1: %s"
        % (len(matches), name),
    )
    return matches[0].start()


def connected_d(body, offset, expected):
    # A mapped FF has its port list within the next few hundred bytes.
    current_ff = body.find("GTP_DFF_", offset)
    next_ff = body.find("GTP_DFF_", current_ff + 8)
    cell = body[offset : next_ff if next_ff >= 0 else offset + 600]
    require(
        re.search(r"\.D\s*\(" + re.escape(expected) + r"\)", cell) is not None,
        "synchronizer D is not driven by " + expected,
    )


def ff_segment(body, offset):
    current_ff = body.find("GTP_DFF_", offset)
    next_ff = body.find("GTP_DFF_", current_ff + 8)
    return body[offset : next_ff if next_ff >= 0 else offset + 1500]


def mapped_fifo_audit(netlist):
    bridge = module_body(netlist, "axi_cpu_sys_cdc")
    records = []
    for fifo in FIFOS:
        instance = re.search(
            r"(?m)^\s*(axi_async_fifo\w*)\s+u_" + fifo + r"_fifo\s*\(",
            bridge,
        )
        require(instance is not None, "mapped FIFO instance missing: " + fifo)
        body = module_body(netlist, instance.group(1))
        for direction in ("wr", "rd"):
            gray = direction + "_gray"
            binary = direction + "_bin"
            stage1 = "wr_gray_rd1" if direction == "wr" else "rd_gray_wr1"
            stage2 = "wr_gray_rd2" if direction == "wr" else "rd_gray_wr2"
            for bit in range(5):
                one_ff(body, gray, bit, False)
            one_ff(body, binary, 4, False)
            for bit in range(5):
                pos1 = one_ff(body, stage1, bit, True)
                pos2 = one_ff(body, stage2, bit, True)
                connected_d(body, pos1, gray + "[" + str(bit) + "]")
                connected_d(body, pos2, stage1 + "[" + str(bit) + "]")
            records.append(
                {
                    "fifo": fifo,
                    "direction": direction,
                    "mapped_launch_ff": 5,
                    "mapped_stage1_ff": 5,
                    "mapped_stage2_ff": 5,
                    "pap_preserve": True,
                }
            )
    control = module_body(netlist, "cpu_core_top")
    for signal, address in (("ar_local", "araddr"), ("aw_local", "awaddr")):
        start = control.find(".Z (" + signal + ")")
        require(start >= 0, "mapped route-control LUT missing: " + signal)
        end = control.find(");", start)
        require(end >= 0, "mapped route-control LUT has no port end: " + signal)
        ports = control[start:end]
        require(
            re.search(r"[dl]_" + address + r"\[\d+\]", ports) is not None,
            "mapped route-control LUT lacks dynamic address: " + signal,
        )
    return records


def mapped_constraint_propagation_audit(netlist, fdc):
    bridge = module_body(netlist, "axi_cpu_sys_cdc")
    fdc_lines = fdc.splitlines()
    expected = expected_constraints(reviewed_cdc_limit(fdc))
    checked = 0
    for fifo in FIFOS:
        instance = re.search(
            r"(?m)^\s*(axi_async_fifo\w*)\s+u_" + fifo + r"_fifo\s*\(",
            bridge,
        )
        require(instance is not None, "mapped FIFO instance missing: " + fifo)
        body = module_body(netlist, instance.group(1))
        for direction in ("wr", "rd"):
            stage = "wr_gray_rd1" if direction == "wr" else "rd_gray_wr1"
            item = expected[(fifo, direction)]
            line_numbers = []
            for line in item["lines"].values():
                require(
                    fdc_lines.count(line) == 1,
                    "FDC line missing or duplicated for mapped propagation: %s %s"
                    % (fifo, direction),
                )
                line_numbers.append(fdc_lines.index(line) + 1)
            for bit in range(5):
                launch = ff_segment(body, one_ff(body, direction + "_gray", bit, False))
                capture = ff_segment(body, one_ff(body, stage, bit, True))
                for number in line_numbers:
                    from_tag = re.search(
                        r"// SDC constraint : \(object Q\) \(id \d+\) \(from\) \("
                        + str(number)
                        + r" :",
                        launch,
                    )
                    to_tag = re.search(
                        r"// SDC constraint : \(object D\) \(id \d+\) \(to\) \("
                        + str(number)
                        + r" :",
                        capture,
                    )
                    require(
                        from_tag is not None and to_tag is not None,
                        "directed FDC line %d did not propagate to mapped FF bit %d: %s %s"
                        % (number, bit, fifo, direction),
                    )
                    checked += 2
    require(checked == 300, "mapped FDC endpoint tag count is not 300")
    return checked


def mapped_control_audit(netlist):
    bridge = module_body(netlist, "axi_cpu_sys_cdc")
    records = []
    for name, source, domain in (
        ("sys_ready_cpu", "sys_resetn", "cpu_clk"),
        ("cpu_ready_sys", "cpu_resetn", "sys_clk"),
    ):
        first = one_ff(bridge, name, 0, True)
        second = one_ff(bridge, name, 1, True)
        connected_d(bridge, first, source)
        connected_d(bridge, second, name + "[0]")
        records.append(
            {"name": name, "capture_clock": domain, "stages": 2,
             "pap_preserve": True, "first_stage_source": source}
        )
    irq = module_body(netlist, "cpu_irq_sync")
    for name, source in (
        ("timer", "timer_irq_sys"),
        ("software", "software_irq_sys"),
        ("external", "1'b0"),
    ):
        first = one_scalar_ff(irq, name + "_c1")
        second = one_scalar_ff(irq, name + "_c2")
        connected_d(irq, first, source)
        connected_d(irq, second, name + "_c1")
        records.append(
            {"name": name + "_irq", "capture_clock": "cpu_clk", "stages": 2,
             "pap_preserve": True, "first_stage_source": source}
        )
    return records


def reviewed_cdc_limit(fdc):
    periods = []
    for clock in ("cpu_clk", "sys_clk"):
        matches = re.findall(
            r"(?m)^create_clock -name \{" + clock + r"\} -period \{([0-9.]+)\}", fdc
        )
        require(len(matches) == 1, "CDC budget requires one FDC clock: " + clock)
        periods.append(Decimal(matches[0]))
    limit = min(Decimal("16"), min(periods) - Decimal("0.8"))
    limit = limit.quantize(Decimal("0.001"), rounding=ROUND_FLOOR)
    require(limit > 0, "CPU/SYS periods leave no CDC timing budget")
    literal = format(limit, "f").rstrip("0").rstrip(".")
    return literal if "." in literal else literal + ".0"


def expected_constraints(limit="16.0"):
    result = {}
    for fifo in FIFOS:
        for direction in ("wr", "rd"):
            source = (
                r".*u_axi_cdc/u_"
                + fifo
                + r"_fifo/"
                + direction
                + r"_gray\[4:0\]$"
            )
            stage = "wr_gray_rd1" if direction == "wr" else "rd_gray_wr1"
            capture = (
                r".*u_axi_cdc/u_"
                + fifo
                + r"_fifo/"
                + stage
                + r"\[4:0\]$"
            )
            start = "[get_cells -hierarchical -regexp {" + source + "}]"
            end = "[get_cells -hierarchical -regexp {" + capture + "}]"
            result[(fifo, direction)] = {
                "source_pattern": source,
                "capture_pattern": capture,
                "source_object": (
                    "u_cpu/u_cpu_wrapper/u_axi_cdc/u_"
                    + fifo
                    + "_fifo/"
                    + direction
                    + "_gray[4:0]"
                ),
                "capture_object": (
                    "u_cpu/u_cpu_wrapper/u_axi_cdc/u_"
                    + fifo
                    + "_fifo/"
                    + stage
                    + "[4:0]"
                ),
                "lines": {
                    "max_delay": "set_max_delay -from "
                    + start
                    + " -to "
                    + end
                    + " -datapath_only " + limit,
                    "max_skew": "set_max_skew -from "
                    + start
                    + " -to "
                    + end
                    + " " + limit,
                    "hold_cut": "set_false_path -hold -from "
                    + start
                    + " -to "
                    + end,
                },
            }
    return result


def expected_payload_constraints(limit="16.0"):
    result = {}
    for fifo, (clock, _, _) in PAYLOAD_RAM.items():
        source = r".*u_axi_cdc/u_" + fifo + r"_fifo/storage(_[0-9_]+)?$"
        start = "[get_cells -hierarchical -regexp {" + source + "}]"
        end = "[get_clocks {" + clock + "}]"
        result[fifo] = {
            "source_pattern": source,
            "source_object": (
                "u_cpu/u_cpu_wrapper/u_axi_cdc/u_" + fifo + "_fifo/storage"
            ),
            "capture_clock": clock,
            "lines": {
                "max_delay": "set_max_delay -from "
                + start + " -to " + end + " -datapath_only " + limit,
                "hold_cut": "set_false_path -hold -from " + start + " -to " + end,
            },
        }
    return result


def expected_sync_constraints(limit="16.0"):
    result = {}
    for name, source_clock, pattern, object_name, _, _, _ in SYNC_FIRST_STAGES:
        start = "[get_clocks {" + source_clock + "}]"
        end = "[get_cells -hierarchical -regexp {" + pattern + "}]"
        result[name] = {
            "source_clock": source_clock,
            "capture_pattern": pattern,
            "capture_object": object_name,
            "lines": {
                "max_delay": "set_max_delay -from "
                + start + " -to " + end + " -datapath_only " + limit,
                "hold_cut": "set_false_path -hold -from " + start + " -to " + end,
            },
        }
    return result


def mapped_payload_ram_audit(netlist, fdc):
    bridge = module_body(netlist, "axi_cpu_sys_cdc")
    fdc_lines = fdc.splitlines()
    expected = expected_payload_constraints(reviewed_cdc_limit(fdc))
    records = []
    checked_output_tags = 0
    ram_pattern = re.compile(
        r"(?ms)^[ \t]*GTP_RAM32X([12])DP\s*/\*\s*"
        r"(storage(?:_[0-9_]+)?)\s*\*/.*?\);"
    )
    for fifo in FIFOS:
        instance = re.search(
            r"(?m)^\s*(axi_async_fifo\w*)\s+u_" + fifo + r"_fifo\s*\(",
            bridge,
        )
        require(instance is not None, "mapped FIFO instance missing: " + fifo)
        instance_end = bridge.find(");", instance.end())
        require(instance_end >= 0, "mapped FIFO instance has no port end: " + fifo)
        instance_ports = bridge[instance.end() : instance_end]
        body = module_body(netlist, instance.group(1))
        item = expected[fifo]
        line_numbers = {}
        for kind, line in item["lines"].items():
            require(
                fdc_lines.count(line) == 1,
                "payload FDC line missing or duplicated: %s %s" % (fifo, kind),
            )
            line_numbers[kind] = fdc_lines.index(line) + 1
        cells = list(ram_pattern.finditer(body))
        clock, expected_x1, expected_x2 = PAYLOAD_RAM[fifo]
        launch_clock = "sys_clk" if clock == "cpu_clk" else "cpu_clk"
        for port, expected_clock in (("wr_clk", launch_clock), ("rd_clk", clock)):
            require(
                re.search(
                    r"\." + port + r"\s*\(\s*" + expected_clock + r"\s*\)",
                    instance_ports,
                ) is not None,
                "mapped payload FIFO clock changed: %s/%s expected=%s"
                % (fifo, port, expected_clock),
            )
        x1 = sum(cell.group(1) == "1" for cell in cells)
        x2 = sum(cell.group(1) == "2" for cell in cells)
        names = [cell.group(2) for cell in cells]
        require(
            x1 == expected_x1 and x2 == expected_x2 and len(names) == len(set(names)),
            "mapped payload RAM cardinality or primitive mix changed: %s X1=%d X2=%d"
            % (fifo, x1, x2),
        )
        output_bits = 0
        for cell in cells:
            mapped = cell.group(0)
            name = cell.group(2)
            for port, binary in (("RADDR", "rd"), ("WADDR", "wr")):
                address = (
                    r"\." + port + r"\s*\(\{1'b0,\s*"
                    + binary + r"_bin\[3\],\s*"
                    + binary + r"_bin\[2\],\s*"
                    + binary + r"_bin\[1\],\s*"
                    + binary + r"_bin\[0\]\}\)"
                )
                require(
                    re.search(address, mapped) is not None,
                    "mapped payload RAM address changed: %s/%s %s"
                    % (fifo, name, port),
                )
            for port, signal in (("WCLK", "wr_clk"), ("WE", "wr_fire")):
                require(
                    re.search(r"\." + port + r"\s*\(" + signal + r"\)", mapped)
                    is not None,
                    "mapped payload RAM write port changed: %s/%s %s"
                    % (fifo, name, port),
                )
            comments = []
            for line in body[cell.end() :].splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("//"):
                    break
                if stripped.startswith("// SDC constraint :"):
                    comments.append(stripped)
            pins = ("DO",) if cell.group(1) == "1" else ("DO[0]", "DO[1]")
            for pin in pins:
                output_bits += 1
                for kind, number in line_numbers.items():
                    tag = re.compile(
                        r"^// SDC constraint : \(object "
                        + re.escape(pin)
                        + r"\) \(id \d+\) \(from\) \("
                        + str(number)
                        + r" :"
                    )
                    require(
                        any(tag.search(comment) for comment in comments),
                        "payload FDC did not reach mapped RAM output: %s/%s %s %s"
                        % (fifo, name, pin, kind),
                    )
                    checked_output_tags += 1
        records.append(
            {
                "fifo": fifo,
                "launch_clock": launch_clock,
                "capture_clock": clock,
                "mapped_ram_cells": len(cells),
                "mapped_ram_x1dp": x1,
                "mapped_ram_x2dp": x2,
                "mapped_do_outputs": output_bits,
                "mapped_ram_instances": sorted(names),
            }
        )
    require(
        checked_output_tags == 298,
        "mapped payload RAM output FDC tag count is not 298",
    )
    return records, checked_output_tags


def mapped_sync_first_stage_audit(netlist, fdc):
    fdc_lines = fdc.splitlines()
    expected = expected_sync_constraints(reviewed_cdc_limit(fdc))
    records = []
    checked_tags = 0
    tagged_second_stage = 0
    for name, source_clock, _, object_name, module, first, second in SYNC_FIRST_STAGES:
        body = module_body(netlist, module)
        if module == "axi_cpu_sys_cdc":
            first_pos = one_ff(body, first, 0, True)
            second_pos = one_ff(body, second, 1, True)
        else:
            first_pos = one_scalar_ff(body, first)
            second_pos = one_scalar_ff(body, second)
        first_cell = ff_segment(body, first_pos)
        second_cell = ff_segment(body, second_pos)
        capture_clock = "sys_clk" if name == "cpu_ready_sys0" else "cpu_clk"
        for stage, cell in (("first", first_cell), ("second", second_cell)):
            require(
                re.search(r"\.CLK\s*\(" + capture_clock + r"\)", cell)
                is not None,
                "synchronizer FF capture clock changed: %s %s" % (name, stage),
            )
        require(
            source_clock != capture_clock,
            "first-stage CDC source clock equals capture clock: " + name,
        )
        connected_d(
            body,
            second_pos,
            (first + "[0]") if module == "axi_cpu_sys_cdc" else first,
        )
        second_tags = 0
        for kind, line in expected[name]["lines"].items():
            require(
                fdc_lines.count(line) == 1,
                "first-stage FDC line missing or duplicated: %s %s" % (name, kind),
            )
            number = fdc_lines.index(line) + 1
            tag = re.compile(
                r"// SDC constraint : \(object D\) \(id \d+\) \(to\) \("
                + str(number)
                + r" :"
            )
            require(
                tag.search(first_cell) is not None,
                "first-stage FDC did not reach mapped FF D: %s %s" % (name, kind),
            )
            if tag.search(second_cell) is not None:
                require(
                    module == "axi_cpu_sys_cdc",
                    "scalar first-stage FDC tagged second-stage FF: %s %s"
                    % (name, kind),
                )
                second_tags += 1
                tagged_second_stage += 1
            checked_tags += 1
        if module == "axi_cpu_sys_cdc":
            require(
                second_tags == 2,
                "vector first-stage FDC mapped second-stage tag count changed: "
                + name,
            )
        records.append(
            {
                "name": name,
                "source_clock": source_clock,
                "capture_clock": capture_clock,
                "capture_object": object_name,
                "mapped_first_stage_ff": 1,
                "mapped_second_stage_ff": 1,
                "mapped_second_stage_tags": second_tags,
                "second_stage_source_clock_filtered": True,
            }
        )
    require(checked_tags == 8, "mapped first-stage synchronizer tag count is not 8")
    return records, checked_tags, tagged_second_stage


def constraint_audit(ccr, fdc, records, payloads, syncs):
    summary = re.search(
        r"Found\s+(\d+) error\(s\),\s+(\d+) critical warning\(s\),\s+"
        r"(\d+) warning\(s\),\s+out of\s+(\d+) constraint\(s\)",
        ccr,
    )
    require(summary is not None, "FDC constraint summary missing")
    errors, critical, warnings, total = map(int, summary.groups())
    require(errors == 0, "FDC constraint errors=%d" % errors)
    require(
        critical == 39 and warnings == 0,
        "FDC warnings changed: critical=%d warning=%d (reviewed baseline: 39 shared-pin critical warnings)"
        % (critical, warnings),
    )
    require(
        total == EXPECTED_CONSTRAINTS,
        "FDC constraint count=%d, expected %d" % (total, EXPECTED_CONSTRAINTS),
    )
    inapplicable = ccr.split(
        "Inapplicable constraints(except overwritten constraints):", 1
    )
    require(len(inapplicable) == 2, "FDC inapplicable section missing")
    inapplicable = inapplicable[1].split("Constraints with issues:", 1)[0]
    require(
        "u_axi_cdc" not in inapplicable and "u_irq_sync" not in inapplicable,
        "CDC FDC constraint is inapplicable",
    )
    issues = ccr.split("Constraints with issues:", 1)
    require(len(issues) == 2, "FDC issues section missing")
    issues = issues[1].split("Issues without commands:", 1)[0]
    require(
        "u_axi_cdc" not in issues and "u_irq_sync" not in issues,
        "CDC FDC constraint has an issue",
    )
    unexpected_critical = re.findall(r"(?m)^\s*C:\s+([^\n]+)", ccr)
    require(
        len(unexpected_critical) == 39
        and all("ConstraintEditor-2002" in item and "share pin" in item for item in unexpected_critical),
        "FDC critical warning is not one of the 39 reviewed share-pin placements",
    )
    wildcard = ccr.split("Constraints with matching wildcard expressions:", 1)
    require(len(wildcard) == 2, "FDC wildcard match section missing")
    wildcard_lines = wildcard[1].splitlines()
    expected = expected_constraints(reviewed_cdc_limit(fdc))
    payload_expected = expected_payload_constraints(reviewed_cdc_limit(fdc))
    require(
        len(re.findall(
            r"(?m)^set_(?:max_delay|max_skew|false_path).*"
            r"(?:u_axi_cdc|u_irq_sync)", fdc
        )) == 48,
        "FDC must contain exactly 30 Gray, 10 payload and 8 first-stage constraints",
    )
    false_paths = re.findall(r"(?m)^set_false_path[^\n]*", fdc)
    require(
        len(false_paths) == 19
        and all(line.startswith("set_false_path -hold ") for line in false_paths),
        "FDC must contain only nineteen directed, hold-only CDC false paths",
    )
    for line in fdc.splitlines():
        if line.startswith("set_clock_groups "):
            require(
                not ("cpu_clk" in line and "sys_clk" in line),
                "CPU and SYS clocks must not be placed in an asynchronous clock group",
            )
    for record in records:
        key = (record["fifo"], record["direction"])
        item = expected[key]
        counts = {}
        for kind, line in item["lines"].items():
            require(
                fdc.splitlines().count(line) == 1,
                "FDC directive missing or duplicated: %s %s %s" % (*key, kind),
            )
            positions = [i for i, value in enumerate(wildcard_lines) if value == line]
            require(
                len(positions) == 2,
                "FDC report did not register both selector matches: %s %s %s"
                % (*key, kind),
            )
            actual = []
            objects = []
            for position in positions:
                following = wildcard_lines[position + 1 : position + 4]
                report = next(
                    (
                        re.search(r"match\s+(\d+) objects below:", value)
                        for value in following
                        if "match " in value
                    ),
                    None,
                )
                require(
                    report is not None,
                    "FDC object count missing: %s %s %s" % (*key, kind),
                )
                actual.append(int(report.group(1)))
                instance = next(
                    (
                        re.search(r"^\s*I: instance (\S+)$", value)
                        for value in following
                        if "I: instance " in value
                    ),
                    None,
                )
                require(
                    instance is not None,
                    "FDC selected-object name missing: %s %s %s" % (*key, kind),
                )
                objects.append(instance.group(1))
            require(
                actual == [1, 1],
                "FDC vector-object counts %s, expected [1, 1]: %s %s %s"
                % (actual, *key, kind),
            )
            require(
                objects == [item["source_object"], item["capture_object"]],
                "FDC selected objects %s are not the reviewed pointer vectors: %s %s %s"
                % (objects, *key, kind),
            )
            counts[kind] = {
                "launch_vector_objects": actual[0],
                "capture_vector_objects": actual[1],
                "launch_object": objects[0],
                "capture_object": objects[1],
            }
        record["fdc_matches"] = counts
    for payload in payloads:
        fifo = payload["fifo"]
        item = payload_expected[fifo]
        counts = {}
        for kind, line in item["lines"].items():
            require(
                fdc.splitlines().count(line) == 1,
                "payload FDC directive missing or duplicated: %s %s" % (fifo, kind),
            )
            positions = [i for i, value in enumerate(wildcard_lines) if value == line]
            require(
                len(positions) == 1,
                "payload FDC wildcard source registration differs: %s %s"
                % (fifo, kind),
            )
            following = wildcard_lines[positions[0] + 1 : positions[0] + 4]
            count = next(
                (
                    re.search(r"match\s+(\d+) objects below:", value)
                    for value in following
                    if "match " in value
                ),
                None,
            )
            selected = next(
                (
                    re.search(r"^\s*I: instance (\S+)$", value)
                    for value in following
                    if "I: instance " in value
                ),
                None,
            )
            require(
                count is not None and count.group(1) == "1"
                and selected is not None
                and selected.group(1) == item["source_object"],
                "payload FDC must select one exact logical storage array: %s %s"
                % (fifo, kind),
            )
            counts[kind] = {
                "launch_array_objects": 1,
                "launch_object": selected.group(1),
                "capture_clock": item["capture_clock"],
            }
        payload["fdc_matches"] = counts
    sync_expected = expected_sync_constraints(reviewed_cdc_limit(fdc))
    for sync in syncs:
        name = sync["name"]
        item = sync_expected[name]
        counts = {}
        for kind, line in item["lines"].items():
            require(
                fdc.splitlines().count(line) == 1,
                "first-stage FDC directive missing or duplicated: %s %s"
                % (name, kind),
            )
            positions = [i for i, value in enumerate(wildcard_lines) if value == line]
            require(
                len(positions) == 1,
                "first-stage FDC wildcard registration differs: %s %s"
                % (name, kind),
            )
            following = wildcard_lines[positions[0] + 1 : positions[0] + 4]
            count = next(
                (
                    re.search(r"match\s+(\d+) objects below:", value)
                    for value in following
                    if "match " in value
                ),
                None,
            )
            selected = next(
                (
                    re.search(r"^\s*I: instance (\S+)$", value)
                    for value in following
                    if "I: instance " in value
                ),
                None,
            )
            require(
                count is not None and count.group(1) == "1"
                and selected is not None
                and selected.group(1) == item["capture_object"],
                "first-stage FDC must select one exact FF: %s %s"
                % (name, kind),
            )
            counts[kind] = {
                "capture_ff_objects": 1,
                "capture_object": selected.group(1),
                "source_clock": item["source_clock"],
            }
        sync["fdc_matches"] = counts
    return {
        "total_constraints": total,
        "cdc_directives": 48,
        "gray_directives": 30,
        "payload_directives": 10,
        "first_stage_directives": 8,
        "errors": errors,
        "critical_warnings": critical,
        "warnings": warnings,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--netlist", type=Path, required=True)
    parser.add_argument("--ccr", type=Path, required=True)
    parser.add_argument("--adf", type=Path, required=True)
    parser.add_argument("--fdc", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    paths = (args.netlist, args.ccr, args.adf, args.fdc, args.snapshot)
    for path in paths:
        require(path.is_file(), "input missing: " + str(path))
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8-sig"))
    run_id = snapshot.get("run_id")
    require(
        isinstance(run_id, str) and re.fullmatch(r"[0-9a-f]{32}", run_id),
        "snapshot run_id missing or invalid",
    )
    fdc_sha = sha256(args.fdc)
    expected_fdc_sha = snapshot.get("inputs", {}).get("pds/soc.fdc")
    require(
        fdc_sha == expected_fdc_sha,
        "FDC hash does not match frozen input snapshot",
    )
    fdc = args.fdc.read_text(encoding="utf-8")
    netlist = args.netlist.read_text(encoding="utf-8", errors="replace")
    records = mapped_fifo_audit(netlist)
    controls = mapped_control_audit(netlist)
    mapped_tags = mapped_constraint_propagation_audit(netlist, fdc)
    payloads, payload_tags = mapped_payload_ram_audit(netlist, fdc)
    syncs, sync_tags, second_stage_tags = mapped_sync_first_stage_audit(netlist, fdc)
    del netlist
    ccr = args.ccr.read_text(encoding="utf-8", errors="replace")
    constraints = constraint_audit(ccr, fdc, records, payloads, syncs)
    constraints["mapped_endpoint_tags"] = mapped_tags
    constraints["mapped_payload_output_tags"] = payload_tags
    constraints["mapped_first_stage_tags"] = sync_tags
    constraints["mapped_second_stage_tags"] = second_stage_tags
    result = {
        "schema": 1,
        "status": "PASS",
        "run_id": run_id,
        "snapshot_sha256": sha256(args.snapshot),
        "vm_sha256": sha256(args.netlist),
        "adf_sha256": sha256(args.adf),
        "ccr_sha256": sha256(args.ccr),
        "fdc_sha256": fdc_sha,
        "constraints": constraints,
        "fifos": records,
        "payloads": payloads,
        "first_stage_crossings": syncs,
        "single_bit_synchronizers": controls,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(args.output)
    print(
        "CPU_SYS_CDC_ADS_PASS run_id=%s directions=%d constraints=%d vm_sha256=%s"
        % (run_id, len(records), constraints["total_constraints"], result["vm_sha256"])
    )


if __name__ == "__main__":
    try:
        main()
    except (AuditError, OSError, ValueError, json.JSONDecodeError) as error:
        print("CPU_SYS_CDC_ADS_FAIL " + str(error), file=sys.stderr)
        sys.exit(1)
