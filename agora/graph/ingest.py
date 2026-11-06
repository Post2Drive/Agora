"""Stage 1a - upload: turn documents into clean text chunks.

Supported: PDF, DOCX, TXT, MD, CSV, TSV, JSON, HTML. Files are copied into the
project's `sources/` folder so the project stays self-contained and portable.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import shutil
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree

SUPPORTED = {".pdf", ".docx", ".txt", ".md", ".markdown", ".csv", ".tsv", ".json",
             ".html", ".htm"}


class IngestError(ValueError):
    pass


# ------------------------------------------------------------------ readers
def _read_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as e:  # pragma: no cover - pypdf is a dependency
        raise IngestError("Reading PDFs needs pypdf: pip install pypdf") from e
    reader = PdfReader(str(path))
    pages = []
    for i, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ""
        if text.strip():
            pages.append(f"[page {i}]\n{text}")
    if not pages:
        raise IngestError(f"{path.name}: no text found (scanned PDF? OCR is not supported yet)")
    return "\n\n".join(pages)


def _read_docx(path: Path) -> str:
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError) as e:
        raise IngestError(f"{path.name}: not a valid .docx file") from e
    root = ElementTree.fromstring(xml)
    out = []
    body = root.find("w:body", ns)
    for block in (body if body is not None else []):
        tag = block.tag.split("}")[1]
        if tag == "p":
            out.append("".join(t.text or "" for t in block.iter(f"{{{ns['w']}}}t")))
        elif tag == "tbl":
            for row in block.iter(f"{{{ns['w']}}}tr"):
                cells = ["".join(t.text or "" for t in c.iter(f"{{{ns['w']}}}t"))
                         for c in row.iter(f"{{{ns['w']}}}tc")]
                out.append(" | ".join(cells))
    return "\n".join(out)


class _HTMLText(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "head"}
    BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section",
             "article", "table"}

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def _read_html(path: Path) -> str:
    p = _HTMLText()
    p.feed(path.read_text(encoding="utf-8", errors="replace"))
    return "".join(p.parts)


def _read_table(path: Path, delim: str) -> str:
    """Tables become one line per row: 'col: value; col: value' - easy for a model to read."""
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    if not rows:
        return ""
    head, body = rows[0], rows[1:]
    lines = [f"Table {path.name} with columns: {', '.join(head)}"]
    for r in body[:2000]:
        lines.append("; ".join(f"{h}: {v}" for h, v in zip(head, r) if v.strip()))
    if len(body) > 2000:
        lines.append(f"... {len(body) - 2000} more rows not shown")
    return "\n".join(lines)


def _read_json(path: Path) -> str:
    data = json.loads(path.read_text(encoding="utf-8"))
    return json.dumps(data, indent=1, ensure_ascii=False)


def read_text(path: str | Path) -> str:
    path = Path(path)
    ext = path.suffix.lower()
    if ext not in SUPPORTED:
        raise IngestError(f"{path.name}: unsupported file type. Use one of {sorted(SUPPORTED)}")
    if ext == ".pdf":
        text = _read_pdf(path)
    elif ext == ".docx":
        text = _read_docx(path)
    elif ext in (".html", ".htm"):
        text = _read_html(path)
    elif ext == ".csv":
        text = _read_table(path, ",")
    elif ext == ".tsv":
        text = _read_table(path, "\t")
    elif ext == ".json":
        text = _read_json(path)
    else:
        text = path.read_text(encoding="utf-8", errors="replace")
    return clean(text)


def clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace(" ", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ------------------------------------------------------------------ chunking
def chunk(text: str, size: int = 1500, overlap: int = 200) -> list[str]:
    """Split on paragraph boundaries into ~`size`-character chunks with overlap."""
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks, cur = [], ""
    for p in paras:
        while len(p) > size:                      # very long paragraph: hard split on sentences
            cut = p.rfind(". ", 0, size)
            cut = cut + 1 if cut > size // 2 else size
            pieces, p = p[:cut], p[cut:].strip()
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(pieces)
        if cur and len(cur) + len(p) + 2 > size:
            chunks.append(cur)
            tail = cur[-overlap:]
            tail = tail[tail.find(" ") + 1:] if " " in tail else tail
            cur = (tail + "\n\n" + p) if overlap else p
        else:
            cur = (cur + "\n\n" + p) if cur else p
    if cur:
        chunks.append(cur)
    return chunks


def file_id(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()[:16]


def ingest(store, project: Path, files: list[str | Path], *, size: int = 1500,
           overlap: int = 200) -> list[dict]:
    """Copy files into the project and store their chunks. Re-adding a file is a no-op."""
    src_dir = Path(project) / "sources"
    src_dir.mkdir(parents=True, exist_ok=True)
    added = []
    for f in files:
        f = Path(f)
        if not f.is_file():
            raise IngestError(f"File not found: {f}")
        fid = file_id(f)
        if store.rows("SELECT 1 FROM documents WHERE id=?", (fid,)):
            added.append({"file": f.name, "id": fid, "chunks": 0, "skipped": True})
            continue
        text = read_text(f)
        if not text:
            raise IngestError(f"{f.name}: no text found")
        dst = src_dir / f.name
        if dst.exists() and file_id(dst) != fid:
            dst = src_dir / f"{f.stem}-{fid[:6]}{f.suffix}"
        if f.resolve() != dst.resolve():
            shutil.copy2(f, dst)
        parts = chunk(text, size, overlap)
        with store.db:
            store.db.execute("INSERT INTO documents VALUES (?,?,?,?)",
                             (fid, dst.name, len(text), len(parts)))
            store.db.executemany(
                "INSERT INTO chunks (doc, idx, text, status) VALUES (?,?,?,'new')",
                [(fid, i, c) for i, c in enumerate(parts)])
        added.append({"file": f.name, "id": fid, "chunks": len(parts), "skipped": False})
    return added
