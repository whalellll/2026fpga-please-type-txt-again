#!/usr/bin/env python3
"""Build a deterministic, readable DOCX from the current release Markdown."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parent.parent
SOURCES = (
    "README.md", "CHANGELOG.md", "docs/ARCHITECTURE.md", "docs/BUILD.md",
    "docs/COREMARK.md", "docs/Validation.md", "docs/SUPPORTED_HARDWARE.md",
    "docs/console调试命令.md",
)
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8-sig").strip()
OUTPUT = ROOT / f"docs/SOC_linux_V{VERSION}.docx"
RECORD = ROOT / f"docs/SOC_linux_V{VERSION}.docx.inputs.json"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
ET.register_namespace("w", W)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def element(parent: ET.Element, name: str, value: str | None = None, **attrs: str) -> ET.Element:
    item = ET.SubElement(parent, f"{{{W}}}{name}", {f"{{{W}}}{k}": v for k, v in attrs.items()})
    if value is not None:
        item.text = value
    return item


def paragraph(parent: ET.Element, value: str, style: str = "Normal") -> ET.Element:
    node = element(parent, "p")
    element(element(node, "pPr"), "pStyle", val=style)
    run = element(node, "r")
    text = element(run, "t", value)
    text.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    return node


def document_xml(source_text: dict[str, str]) -> bytes:
    document = ET.Element(f"{{{W}}}document")
    body = element(document, "body")
    paragraph(body, f"SOC_linux V{VERSION} 开发、集成与验证说明", "Title")
    paragraph(body, "由仓库当前 Markdown 生成；输入 SHA-256 见同名 .inputs.json", "Subtitle")
    for index, (relative, content) in enumerate(source_text.items()):
        if index:
            page = element(body, "p")
            element(element(page, "r"), "br", type="page")
        paragraph(body, relative, "Heading1")
        fenced = False
        for line in content.splitlines():
            if line.startswith("```"):
                fenced = not fenced
                continue
            if fenced:
                paragraph(body, line, "Code")
                continue
            heading = re.match(r"^(#{1,3})\s+(.*)$", line)
            if heading:
                paragraph(body, heading.group(2), f"Heading{min(len(heading.group(1)) + 1, 3)}")
            elif line:
                paragraph(body, line, "Normal")
        if fenced:
            raise ValueError(f"Unclosed Markdown fence: {relative}")
    sect = element(body, "sectPr")
    element(sect, "pgSz", w="11906", h="16838")
    element(sect, "pgMar", top="1134", bottom="1134", left="1134", right="1134")
    return ET.tostring(document, encoding="utf-8", xml_declaration=True)


def styles_xml() -> bytes:
    styles = ET.Element(f"{{{W}}}styles")
    for name, size, bold in (
        ("Normal", "21", False), ("Title", "40", True),
        ("Subtitle", "22", False), ("Heading1", "30", True),
        ("Heading2", "25", True), ("Heading3", "22", True),
        ("Code", "18", False),
    ):
        style = element(styles, "style", type="paragraph", styleId=name)
        element(style, "name", val=name)
        if name == "Normal":
            style.set(f"{{{W}}}default", "1")
        props = element(style, "rPr")
        element(props, "sz", val=size)
        element(props, "rFonts", ascii="Consolas" if name == "Code" else "Calibri",
                hAnsi="Consolas" if name == "Code" else "Calibri", eastAsia="Microsoft YaHei")
        if bold:
            element(props, "b")
    return ET.tostring(styles, encoding="utf-8", xml_declaration=True)


def write_docx(source_text: dict[str, str]) -> None:
    parts = {
        "[Content_Types].xml": b'''<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>''',
        "_rels/.rels": b'''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>''',
        "word/document.xml": document_xml(source_text),
        "word/styles.xml": styles_xml(),
    }
    with ZipFile(OUTPUT, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(parts.items()):
            info = ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, data, compress_type=ZIP_DEFLATED, compresslevel=9)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify DOCX and source hashes")
    args = parser.parse_args()
    hashes = {name: sha256((ROOT / name).read_bytes()) for name in SOURCES}
    generator = sha256(Path(__file__).read_bytes())
    if args.check:
        record = json.loads(RECORD.read_text(encoding="utf-8"))
        if record != {
            "schema": 1, "generator_sha256": generator,
            "source_sha256": hashes, "docx_sha256": sha256(OUTPUT.read_bytes()),
        }:
            raise SystemExit("DOCX or authoritative Markdown changed; regenerate release DOCX")
        with ZipFile(OUTPUT) as archive:
            if "word/document.xml" not in archive.namelist():
                raise SystemExit("DOCX is missing Word document content")
        print("SOC_DOCX_INPUTS_PASS")
        return
    source_text = {name: (ROOT / name).read_text(encoding="utf-8-sig") for name in SOURCES}
    write_docx(source_text)
    record = {
        "schema": 1, "generator_sha256": generator,
        "source_sha256": hashes, "docx_sha256": sha256(OUTPUT.read_bytes()),
    }
    RECORD.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"SOC_DOCX_EXPORTED {OUTPUT} sha256={record['docx_sha256']}")


if __name__ == "__main__":
    main()
