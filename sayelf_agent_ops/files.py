"""Local, bounded file intake for Agent Ops work items.

Files stay under the configured workspace and are addressed by a short content
hash. Plain text, CSV/TSV, JSON, Markdown and safe ``.xlsx`` files are read
with the standard library. PDF, Office binary, drawings and images are stored
and listed honestly; this slice does not pretend to OCR or parse them.
"""
from __future__ import annotations

import hashlib
import json
import re
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_TEXT_CHARS = 200_000
MAX_XLSX_UNPACKED = 80 * 1024 * 1024
MAX_XLSX_ROWS = 20_000
ALLOWED = {
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".csv": "text/csv", ".tsv": "text/tab-separated-values", ".txt": "text/plain",
    ".md": "text/markdown", ".json": "application/json", ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".dwg": "application/acad", ".dxf": "image/vnd.dxf",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
}
TEXT_TYPES = {".csv", ".tsv", ".txt", ".md", ".json"}
_NAME_OK = re.compile(r'^[^\\/:*?"<>|\x00-\x1f]{1,120}$')
_ID_OK = re.compile(r"^F-[0-9a-f]{16}$")
_NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}


class FileRejected(ValueError):
    """A file failed a local safety or format boundary."""


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _xml(raw: bytes) -> ElementTree.Element:
    head = raw[:4096].upper()
    if b"<!DOCTYPE" in head or b"<!ENTITY" in raw.upper():
        raise FileRejected("XLSX_UNSAFE_XML")
    try:
        return ElementTree.fromstring(raw)
    except ElementTree.ParseError:
        raise FileRejected("XLSX_INVALID") from None


def _col_index(ref: str) -> int:
    letters = re.match(r"[A-Z]+", ref or "")
    n = 0
    for ch in (letters.group(0) if letters else "A"):
        n = n * 26 + ord(ch) - 64
    return n - 1


def xlsx_text(data: bytes) -> str:
    """Extract bounded tab-separated rows from every workbook sheet."""
    try:
        book = zipfile.ZipFile(BytesIO(data))
    except zipfile.BadZipFile:
        raise FileRejected("XLSX_INVALID") from None
    try:
        if sum(info.file_size for info in book.infolist()) > MAX_XLSX_UNPACKED:
            raise FileRejected("XLSX_TOO_LARGE_UNPACKED")
        names = set(book.namelist())
        shared: list[str] = []
        if "xl/sharedStrings.xml" in names:
            for si in _xml(book.read("xl/sharedStrings.xml")).findall("m:si", _NS):
                shared.append("".join(t.text or "" for t in si.iter(f"{{{_NS['m']}}}t")))
        workbook = _xml(book.read("xl/workbook.xml"))
        rels: dict[str, str] = {}
        if "xl/_rels/workbook.xml.rels" in names:
            for rel in _xml(book.read("xl/_rels/workbook.xml.rels")).findall("rel:Relationship", _NS):
                rels[rel.get("Id", "")] = rel.get("Target", "")
        out: list[str] = []
        rows_total = 0
        for sheet in workbook.findall("m:sheets/m:sheet", _NS):
            target = rels.get(sheet.get(f"{{{_NS['r']}}}id"), "")
            path = target.lstrip("/") if target.startswith("/") else f"xl/{target}"
            if path not in names:
                continue
            out.append(f"## 工作表：{sheet.get('name')}")
            for row in _xml(book.read(path)).iter(f"{{{_NS['m']}}}row"):
                cells: dict[int, str] = {}
                for cell in row.findall("m:c", _NS):
                    kind, value_node = cell.get("t"), cell.find("m:v", _NS)
                    if kind == "s" and value_node is not None and (value_node.text or "").isdigit():
                        index = int(value_node.text or "-1")
                        value = shared[index] if 0 <= index < len(shared) else ""
                    elif kind == "inlineStr":
                        value = "".join(t.text or "" for t in cell.iter(f"{{{_NS['m']}}}t"))
                    else:
                        value = value_node.text if value_node is not None and value_node.text else ""
                    cells[_col_index(cell.get("r", ""))] = value.replace("\t", " ").replace("\n", " ")
                if cells:
                    out.append("\t".join(cells.get(i, "") for i in range(max(cells) + 1)))
                    rows_total += 1
                    if rows_total >= MAX_XLSX_ROWS:
                        out.append("（行数超过上限，后面的行未读取）")
                        return "\n".join(out)
        return "\n".join(out)
    finally:
        book.close()


def extract_text(name: str, data: bytes) -> str | None:
    suffix = Path(name).suffix.lower()
    if suffix in TEXT_TYPES:
        text = _decode_text(data)
    elif suffix == ".xlsx":
        text = xlsx_text(data)
    else:
        return None
    return text[:MAX_TEXT_CHARS]


class FileStore:
    def __init__(self, root: Path):
        self.root = root

    def put(self, name: Any, data: bytes, uploaded_by: str) -> dict[str, Any]:
        if not isinstance(name, str) or not _NAME_OK.match(name.strip()) or name.strip() in (".", ".."):
            raise FileRejected("FILE_NAME_INVALID")
        name = name.strip()
        suffix = Path(name).suffix.lower()
        if suffix not in ALLOWED:
            raise FileRejected("FILE_TYPE_NOT_ALLOWED")
        if not isinstance(data, (bytes, bytearray)) or not data:
            raise FileRejected("FILE_EMPTY")
        if len(data) > MAX_FILE_BYTES:
            raise FileRejected("FILE_TOO_LARGE")
        data = bytes(data)
        sha = hashlib.sha256(data).hexdigest()
        file_id = f"F-{sha[:16]}"
        text = extract_text(name, data)
        self.root.mkdir(parents=True, exist_ok=True)
        blob = self.root / f"{sha}.bin"
        if not blob.exists():
            blob.write_bytes(data)
        if text is not None:
            (self.root / f"{file_id}.txt").write_text(text, encoding="utf-8")
        meta = {
            "id": file_id, "name": name, "media_type": ALLOWED[suffix], "size": len(data),
            "sha256": sha, "uploaded_by": uploaded_by,
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "text_extracted": text is not None, "text_chars": len(text or ""),
        }
        (self.root / f"{file_id}.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        return meta

    def meta(self, file_id: Any) -> dict[str, Any]:
        if not isinstance(file_id, str) or not _ID_OK.match(file_id):
            raise FileRejected("UNKNOWN_FILE")
        path = self.root / f"{file_id}.json"
        if not path.exists():
            raise FileRejected("UNKNOWN_FILE")
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raise FileRejected("UNKNOWN_FILE") from None

    def content(self, file_id: str) -> tuple[dict[str, Any], bytes]:
        meta = self.meta(file_id)
        try:
            return meta, (self.root / f"{meta['sha256']}.bin").read_bytes()
        except (KeyError, OSError):
            raise FileRejected("UNKNOWN_FILE") from None

    def text(self, file_id: str) -> str | None:
        meta = self.meta(file_id)
        path = self.root / f"{file_id}.txt"
        if not meta.get("text_extracted") or not path.exists():
            return None
        return path.read_text(encoding="utf-8")
