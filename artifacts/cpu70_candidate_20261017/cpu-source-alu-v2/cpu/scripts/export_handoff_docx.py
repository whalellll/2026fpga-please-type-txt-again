#!/usr/bin/env python3
"""Export the authoritative handoff Markdown to deterministic OOXML (stdlib only)."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML = "http://www.w3.org/XML/1998/namespace"
ET.register_namespace("w", W)
ROOT = Path(__file__).resolve().parent.parent
SOURCES = ("README.md", "handoff/ARCHITECTURE_INTERFACE_CLOCKS.md",
           "handoff/NEW_COMPUTER_GUIDE.md", "handoff/CODEX_HANDOVER.md",
           "handoff/V3_5_VALIDATION.md", "handoff/V3_1_VALIDATION.md", "handoff/VALIDATION.md")


def node(parent, tag, text=None, **attributes):
    item = ET.SubElement(parent, f"{{{W}}}{tag}", {f"{{{W}}}{k}": str(v) for k, v in attributes.items()})
    if text is not None:
        item.text = text
    return item


def text_run(paragraph, value, code=False, bold=False):
    run = node(paragraph, "r")
    if code or bold:
        props = node(run, "rPr")
        if code:
            node(props, "rFonts", ascii="Consolas", hAnsi="Consolas", eastAsia="Microsoft YaHei")
            node(props, "sz", val=18)
        if bold:
            node(props, "b")
    text = node(run, "t", value)
    text.set(f"{{{XML}}}space", "preserve")


def paragraph(parent, value, style=None, plain=False):
    p = node(parent, "p")
    if style:
        node(node(p, "pPr"), "pStyle", val=style)
    if plain:
        text_run(p, value)
    else:
        value = re.sub(r"\[([^]]+)\]\(([^)]+)\)", r"\1 (\2)", value)
        for part in re.split(r"(`[^`]*`|\*\*[^*]+\*\*)", value):
            if part.startswith("`") and part.endswith("`"):
                text_run(p, part[1:-1], code=True)
            elif part.startswith("**") and part.endswith("**"):
                text_run(p, part[2:-2], bold=True)
            elif part:
                text_run(p, part)
    return p


def table(parent, lines):
    rows = [[cell.strip() for cell in line.strip().strip("|").split("|")] for line in lines]
    rows = [row for row in rows if not all(re.fullmatch(r":?-+:?", cell) for cell in row)]
    tab = node(parent, "tbl")
    props = node(tab, "tblPr")
    node(props, "tblW", w=0, type="auto")
    borders = node(props, "tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        node(borders, side, val="single", sz=4, color="CBD5E1")
    grid = node(tab, "tblGrid")
    columns = max(len(row) for row in rows)
    for _ in range(columns):
        node(grid, "gridCol", w=9360 // columns)
    for index, row in enumerate(rows):
        tr = node(tab, "tr")
        if not index:
            node(node(tr, "trPr"), "tblHeader")
        for cell in row:
            tc = node(tr, "tc")
            tcpr = node(tc, "tcPr")
            node(tcpr, "tcW", w=9360 // columns, type="dxa")
            if not index:
                node(tcpr, "shd", fill="E8EEF6")
            paragraph(tc, cell, "TableText")
    paragraph(parent, "")


def markdown(parent, text):
    lines = text.splitlines()
    index = 0
    in_code = False
    while index < len(lines):
        line = lines[index]
        if line.startswith("```"):
            in_code = not in_code
            index += 1
            continue
        if in_code:
            # Let Word wrap visually; preserve a copyable command as one paragraph.
            paragraph(parent, line, "Code", plain=True)
        elif line.startswith("|"):
            block = []
            while index < len(lines) and lines[index].startswith("|"):
                block.append(lines[index])
                index += 1
            table(parent, block)
            continue
        elif line.strip():
            heading = re.match(r"^(#{1,3})\s+(.+)$", line)
            if heading:
                paragraph(parent, heading.group(2), f"Heading{len(heading.group(1))}")
            else:
                # Markdown soft line breaks belong to one readable paragraph.
                # Keep list items separate and leave fenced command lines intact.
                bullet = line.startswith("- ")
                parts = [line[2:] if bullet else line]
                while index + 1 < len(lines):
                    following = lines[index + 1]
                    if not following.strip() or re.match(
                        r"^(?:#{1,6}\s|[-*+]\s|\d+[.)]\s|```|\|)", following
                    ):
                        break
                    parts.append(following.strip())
                    index += 1
                value = " ".join(parts)
                paragraph(parent, "• " + value if bullet else value,
                          "ListText" if bullet else None)
        index += 1
    if in_code:
        raise ValueError("Unclosed Markdown code fence")


def xml_bytes(element):
    return ET.tostring(element, encoding="utf-8", xml_declaration=True)


def styles_xml():
    styles = ET.Element(f"{{{W}}}styles")
    defaults = node(styles, "docDefaults")
    run = node(node(defaults, "rPrDefault"), "rPr")
    node(run, "rFonts", ascii="Calibri", hAnsi="Calibri", eastAsia="Microsoft YaHei")
    node(run, "sz", val=21)
    node(run, "lang", val="en-US", eastAsia="zh-CN")
    pp = node(node(defaults, "pPrDefault"), "pPr")
    node(pp, "spacing", after=110, line=310, lineRule="auto")
    definitions = (
        ("Normal", 21, False, None), ("Title", 40, True, "17365D"),
        ("Subtitle", 22, False, "516274"), ("Heading1", 30, True, "17365D"),
        ("Heading2", 25, True, "24486C"), ("Heading3", 22, True, "24486C"),
        ("Code", 17, False, None), ("TableText", 18, False, None),
        ("ListText", 21, False, None),
    )
    for name, size, bold, color in definitions:
        style = node(styles, "style", type="paragraph", styleId=name)
        if name == "Normal":
            style.set(f"{{{W}}}default", "1")
        node(style, "name", val=name)
        if name != "Normal":
            node(style, "basedOn", val="Normal")
        props = node(style, "pPr")
        if name.startswith("Heading"):
            node(props, "keepNext")
            node(props, "spacing", before=220, after=100)
            node(props, "outlineLvl", val=int(name[-1]) - 1)
        if name == "Code":
            node(props, "spacing", before=0, after=0, line=240, lineRule="auto")
            node(props, "shd", fill="F1F5F9")
        if name == "ListText":
            node(props, "ind", left=200, hanging=160)
        rpr = node(style, "rPr")
        node(rpr, "sz", val=size)
        if bold:
            node(rpr, "b")
        if color:
            node(rpr, "color", val=color)
        if name == "Code":
            node(rpr, "rFonts", ascii="Consolas", hAnsi="Consolas", eastAsia="Microsoft YaHei")
    return xml_bytes(styles)


def export(output, check=False):
    release_version = (ROOT.parent / "VERSION").read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", release_version):
        raise ValueError("CPU VERSION must use major.minor.patch")
    release_name = "CPU V" + ".".join(release_version.split(".")[:2])
    document = ET.Element(f"{{{W}}}document")
    body = node(document, "body")
    paragraph(body, release_name + " 新电脑开发与集成指南", "Title")
    paragraph(body, "src：CPU 优化 / performance_soc：板级集成", "Subtitle")
    paragraph(body, "Markdown 为权威源；此文件由 scripts/export_handoff_docx.py 自动导出。")
    digests = []
    for relative in SOURCES:
        raw = (ROOT / relative).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        digests.append(f"{relative}: {digest}")
        p = paragraph(body, "")
        node(node(p, "r"), "br", type="page")
        paragraph(body, "来源：" + relative, "Subtitle")
        markdown(body, raw.decode("utf-8-sig"))
    section = node(body, "sectPr")
    node(section, "pgSz", w=11906, h=16838)
    node(section, "pgMar", top=1134, right=1134, bottom=1134, left=1134, header=567, footer=567, gutter=0)
    core = ET.Element("cp:coreProperties", {
        "xmlns:cp": "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
        "xmlns:dc": "http://purl.org/dc/elements/1.1/",
    })
    ET.SubElement(core, "dc:title").text = release_name + " 新电脑开发与集成指南"
    ET.SubElement(core, "dc:creator").text = release_name + " project"
    ET.SubElement(core, "dc:description").text = "Authoritative Markdown SHA256\n" + "\n".join(digests)
    settings = ET.Element(f"{{{W}}}settings")
    node(settings, "zoom", percent=100)
    parts = {
        "[Content_Types].xml": b'''<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
<Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
</Types>''',
        "_rels/.rels": b'''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
</Relationships>''',
        "word/_rels/document.xml.rels": b'''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/>
</Relationships>''',
        "word/document.xml": xml_bytes(document),
        "word/styles.xml": styles_xml(),
        "word/settings.xml": xml_bytes(settings),
        "docProps/core.xml": xml_bytes(core),
    }
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        for name, content in parts.items():
            ET.fromstring(content)  # Fail before delivering malformed XML.
            entry = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = ZIP_DEFLATED
            entry.external_attr = 0o600 << 16
            archive.writestr(entry, content)
    encoded = buffer.getvalue()
    with ZipFile(io.BytesIO(encoded)) as archive:
        if archive.testzip() is not None:
            raise ValueError("DOCX ZIP integrity check failed")
    record = {
        "schema": 1,
        "release_version": release_version,
        "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "source_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCES},
        "version_sha256": hashlib.sha256((ROOT.parent / "VERSION").read_bytes()).hexdigest(),
        "docx_sha256": hashlib.sha256(encoded).hexdigest(),
    }
    record_path = output.with_name(output.name + ".inputs.json")
    record_bytes = (json.dumps(record, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if check:
        if output.read_bytes() != encoded or record_path.read_bytes() != record_bytes:
            raise ValueError("DOCX or its input manifest differs from current authoritative Markdown")
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(encoded)
        record_path.write_bytes(record_bytes)
    print("DOCX_EXPORT_PASS:", output)
    print("SHA256:", hashlib.sha256(output.read_bytes()).hexdigest())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "handoff" / "新电脑开发与集成指南.docx")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    export(args.output.resolve(), check=args.check)
