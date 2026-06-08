"""
Optic V1 — Parser Library
==========================
17 format parsers. Each parser takes raw bytes or file path and returns
ParseResult: artifacts list + errors list + warnings list.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import mailbox
import os
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

from .models import Artifact, SourceType


@dataclass
class ParseResult:
    artifacts: List[Artifact] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class ParserRegistry:
    """Maps source types to parsers and detects formats."""

    FORMAT_MAP = {
        ".zip": "zip",
        ".json": "json",
        ".csv": "csv",
        ".html": "html", ".htm": "html",
        ".pdf": "pdf",
        ".docx": "docx",
        ".txt": "txt", ".md": "txt", ".rst": "txt",
        ".mbox": "mbox",
        ".eml": "email",
        ".ics": "ics", ".ical": "ics",
        ".vcf": "vcard",
        ".jpg": "image", ".jpeg": "image", ".png": "image",
        ".heic": "image", ".webp": "image",
        ".xml": "xml", ".plist": "plist",
        ".sqlite": "sqlite", ".db": "sqlite",
    }

    MAGIC_BYTES = {
        b"PK\x03\x04": "zip",
        b"%PDF": "pdf",
        b"PK\x03\x04\x14\x00\x06\x00": "docx",
        b"From ": "mbox",
        b"BEGIN:VCALENDAR": "ics",
        b"\xff\xd8\xff": "image",
        b"\x89PNG": "image",
    }

    def __init__(self, source_id: UUID):
        self.source_id = source_id

    def detect_format(self, filepath: str = "", content: bytes = b"") -> str:
        ext = Path(filepath).suffix.lower() if filepath else ""
        if ext in self.FORMAT_MAP:
            return self.FORMAT_MAP[ext]
        for magic, fmt in self.MAGIC_BYTES.items():
            if content.startswith(magic):
                return fmt
        return "txt"

    def parse(self, filepath: str = "", content: bytes = b"", format_hint: str = "") -> ParseResult:
        fmt = format_hint or self.detect_format(filepath, content)
        parser = getattr(self, f"parse_{fmt}", None)
        if parser:
            return parser(filepath, content)
        return ParseResult(errors=[f"unsupported format: {fmt}"])

    def parse_zip(self, filepath: str = "", content: bytes = b"") -> ParseResult:
        result = ParseResult()
        try:
            if content:
                zf = zipfile.ZipFile(io.BytesIO(content))
            else:
                zf = zipfile.ZipFile(filepath)
            for name in zf.namelist():
                try:
                    inner = zf.read(name)
                    inner_fmt = self.detect_format(name, inner)
                    inner_result = self.parse(name, inner, inner_fmt)
                    result.artifacts.extend(inner_result.artifacts)
                    result.warnings.extend(inner_result.warnings)
                except Exception as e:
                    result.warnings.append(f"zip/{name}: {e}")
        except Exception as e:
            result.errors.append(f"zip error: {e}")
        return result

    def parse_json(self, filepath: str = "", content: bytes = b"") -> ParseResult:
        result = ParseResult()
        try:
            text = content.decode("utf-8", errors="replace") if content else Path(filepath).read_text(errors="replace")
            data = json.loads(text)
            artifacts = self._flatten_json(data, filepath or "inline")
            result.artifacts.extend(artifacts)
        except Exception as e:
            result.errors.append(f"json error: {e}")
        return result

    def parse_csv(self, filepath: str = "", content: bytes = b"") -> ParseResult:
        result = ParseResult()
        try:
            if content:
                text = content.decode("utf-8", errors="replace")
                reader = csv.DictReader(io.StringIO(text))
            else:
                with open(filepath, newline="", encoding="utf-8", errors="replace") as f:
                    reader = csv.DictReader(f)
            rows = list(reader)[:1000]
            preview = "\n".join(str(r) for r in rows[:5])[:500]
            result.artifacts.append(self._make_artifact(
                "csv", hashlib.sha256(content or Path(filepath).read_bytes()).hexdigest(),
                {"path": filepath, "row_count": len(rows), "columns": list(rows[0].keys()) if rows else []},
                preview
            ))
        except Exception as e:
            result.errors.append(f"csv error: {e}")
        return result

    def parse_html(self, filepath: str = "", content: bytes = b"") -> ParseResult:
        result = ParseResult()
        try:
            text = content.decode("utf-8", errors="replace") if content else Path(filepath).read_text(errors="replace")
            title = re.search(r"<title>(.*?)</title>", text, re.IGNORECASE)
            body = re.sub(r"<[^>]+>", " ", text)
            body = re.sub(r"\s+", " ", body).strip()[:2000]
            result.artifacts.append(self._make_artifact(
                "html", hashlib.sha256((content or Path(filepath).read_bytes())).hexdigest(),
                {"path": filepath, "title": title.group(1) if title else ""},
                body[:500]
            ))
        except Exception as e:
            result.errors.append(f"html error: {e}")
        return result

    def parse_pdf(self, filepath: str = "", content: bytes = b"") -> ParseResult:
        result = ParseResult()
        try:
            text = ""
            try:
                import fitz
                doc = fitz.open(stream=content, filetype="pdf") if content else fitz.open(filepath)
                text = " ".join(page.get_text() for page in doc)[:5000]
                doc.close()
            except ImportError:
                import subprocess
                proc = subprocess.run(["pdftotext", "--", filepath or "-", "-"], input=content, capture_output=True, text=True)
                text = proc.stdout[:5000]
            result.artifacts.append(self._make_artifact(
                "pdf", hashlib.sha256(content or Path(filepath).read_bytes()).hexdigest(),
                {"path": filepath, "pages": len(text.split("\f")) if text else 0},
                text[:500]
            ))
        except Exception as e:
            result.errors.append(f"pdf error: {e}")
        return result

    def parse_docx(self, filepath: str = "", content: bytes = b"") -> ParseResult:
        result = ParseResult()
        try:
            import docx
            doc = docx.Document(io.BytesIO(content)) if content else docx.Document(filepath)
            text = " ".join(p.text for p in doc.paragraphs)[:5000]
            result.artifacts.append(self._make_artifact(
                "docx", hashlib.sha256(content or Path(filepath).read_bytes()).hexdigest(),
                {"path": filepath, "paragraphs": len(doc.paragraphs)},
                text[:500]
            ))
        except Exception as e:
            result.errors.append(f"docx error: {e}")
        return result

    def parse_txt_md(self, filepath: str = "", content: bytes = b"") -> ParseResult:
        result = ParseResult()
        try:
            text = content.decode("utf-8", errors="replace") if content else Path(filepath).read_text(errors="replace")
            result.artifacts.append(self._make_artifact(
                "text", hashlib.sha256(content or Path(filepath).read_bytes()).hexdigest(),
                {"path": filepath, "lines": len(text.splitlines()), "chars": len(text)},
                text[:500]
            ))
        except Exception as e:
            result.errors.append(f"text error: {e}")
        return result

    def parse_mbox(self, filepath: str = "", content: bytes = b"") -> ParseResult:
        result = ParseResult()
        try:
            if content:
                mbox = mailbox.mbox(io.BytesIO(content))
            else:
                mbox = mailbox.mbox(filepath)
            for i, msg in enumerate(mbox):
                if i > 100:
                    result.warnings.append("mbox truncated at 100 messages")
                    break
                subject = msg.get("Subject", "")
                sender = msg.get("From", "")
                date = msg.get("Date", "")
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            body = str(part.get_payload(decode=True))[:1000]
                else:
                    body = str(msg.get_payload(decode=True) or "")[:1000]
                result.artifacts.append(self._make_artifact(
                    "email", hashlib.sha256((subject + sender + date).encode()).hexdigest(),
                    {"subject": subject, "from": sender, "date": date},
                    body[:300]
                ))
        except Exception as e:
            result.errors.append(f"mbox error: {e}")
        return result

    def parse_ics(self, filepath: str = "", content: bytes = b"") -> ParseResult:
        result = ParseResult()
        try:
            text = content.decode("utf-8", errors="replace") if content else Path(filepath).read_text(errors="replace")
            events = re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", text, re.DOTALL)
            for e in events[:200]:
                summary = re.search(r"SUMMARY:(.+)", e)
                dtstart = re.search(r"DTSTART[:;].*?(\d{8})", e)
                result.artifacts.append(self._make_artifact(
                    "calendar_event",
                    hashlib.sha256(e.encode()).hexdigest(),
                    {"summary": summary.group(1).strip() if summary else "",
                     "date": dtstart.group(1) if dtstart else ""},
                    (summary.group(1) if summary else "")[:200]
                ))
        except Exception as e:
            result.errors.append(f"ics error: {e}")
        return result

    def parse_image_metadata(self, filepath: str = "", content: bytes = b"") -> ParseResult:
        result = ParseResult()
        try:
            from PIL import Image, ExifTags
            img = Image.open(io.BytesIO(content)) if content else Image.open(filepath)
            meta = {"size": img.size, "format": img.format}
            exif = img._getexif()
            if exif:
                for tag_id, value in exif.items():
                    tag = ExifTags.TAGS.get(tag_id, str(tag_id))
                    if isinstance(value, bytes):
                        value = value.decode("utf-8", errors="replace")[:100]
                    meta[str(tag)] = str(value)[:200]
            img.close()
            result.artifacts.append(self._make_artifact(
                "image", hashlib.sha256(content or Path(filepath).read_bytes()).hexdigest(),
                meta, f"{img.size[0]}x{img.size[1]} {img.format}"
            ))
        except Exception as e:
            result.warnings.append(f"image metadata error: {e}")
        return result

    def parse_github_json(self, filepath: str = "", content: bytes = b"") -> ParseResult:
        result = ParseResult()
        try:
            text = content.decode("utf-8", errors="replace") if content else Path(filepath).read_text(errors="replace")
            data = json.loads(text)
            if isinstance(data, list):
                for repo in data[:50]:
                    result.artifacts.append(self._make_artifact(
                        "github_repo",
                        hashlib.sha256(json.dumps(repo).encode()).hexdigest(),
                        {"name": repo.get("name", ""), "language": repo.get("language", ""),
                         "stars": repo.get("stargazers_count", 0), "description": repo.get("description", "")},
                        repo.get("description", "")[:300]
                    ))
            else:
                result.artifacts.append(self._make_artifact(
                    "github_data",
                    hashlib.sha256(text.encode()).hexdigest(),
                    {"keys": list(data.keys())[:20]},
                    str(data)[:500]
                ))
        except Exception as e:
            result.errors.append(f"github json error: {e}")
        return result

    def parse_linkedin_profile(self, filepath: str = "", content: bytes = b"") -> ParseResult:
        result = ParseResult()
        try:
            text = content.decode("utf-8", errors="replace") if content else Path(filepath).read_text(errors="replace")
            name = re.search(r'"firstName":"([^"]+)".*?"lastName":"([^"]+)"', text)
            headline = re.search(r'"headline":"([^"]*)"', text)
            summary = re.search(r'"summary":"([^"]*)"', text)
            positions = re.findall(r'"title":"([^"]+)"', text)
            meta = {"name": f"{name.group(1)} {name.group(2)}" if name else "",
                    "headline": headline.group(1) if headline else "",
                    "positions": positions[:10]}
            result.artifacts.append(self._make_artifact(
                "linkedin_profile", hashlib.sha256(text.encode()).hexdigest(),
                meta, (headline.group(1) if headline else "")[:500]
            ))
        except Exception as e:
            result.errors.append(f"linkedin error: {e}")
        return result

    def parse_resume_pdf(self, filepath: str = "", content: bytes = b"") -> ParseResult:
        return self.parse_pdf(filepath, content)

    def parse_x_archive(self, filepath: str = "", content: bytes = b"") -> ParseResult:
        result = ParseResult()
        try:
            text = content.decode("utf-8", errors="replace") if content else Path(filepath).read_text(errors="replace")
            data = json.loads(text)
            tweets = []
            if isinstance(data, list):
                tweets = data
            elif isinstance(data, dict):
                tweets = data.get("tweets", data.get("data", []))
            for t in tweets[:200]:
                full_text = t.get("full_text", t.get("text", ""))
                created = t.get("created_at", "")
                result.artifacts.append(self._make_artifact(
                    "tweet", hashlib.sha256(full_text.encode()).hexdigest(),
                    {"created_at": created, "retweet_count": t.get("retweet_count", 0)},
                    full_text[:280]
                ))
        except Exception as e:
            result.errors.append(f"x archive error: {e}")
        return result

    def parse_browser_history(self, filepath: str = "", content: bytes = b"") -> ParseResult:
        result = ParseResult()
        try:
            if filepath.endswith(".sqlite") or filepath.endswith(".db"):
                import sqlite3
                conn = sqlite3.connect(filepath)
                conn.row_factory = sqlite3.Row
                rows = conn.execute("SELECT url, title, visit_count, last_visit_time FROM urls LIMIT 500").fetchall()
                for r in rows:
                    result.artifacts.append(self._make_artifact(
                        "browser_history", hashlib.sha256(r["url"].encode()).hexdigest(),
                        {"url": r["url"][:200], "title": r["title"] or "", "visits": r["visit_count"] or 1},
                        r["title"] or r["url"][:200]
                    ))
                conn.close()
            else:
                text = content.decode("utf-8", errors="replace") if content else Path(filepath).read_text(errors="replace")
                urls = re.findall(r"https?://[^\s\"<>]+", text)
                for u in urls[:500]:
                    result.artifacts.append(self._make_artifact(
                        "browser_history", hashlib.sha256(u.encode()).hexdigest(),
                        {"url": u[:200]}, u[:200]
                    ))
        except Exception as e:
            result.errors.append(f"browser history error: {e}")
        return result

    def parse_google_takeout(self, filepath: str = "", content: bytes = b"") -> ParseResult:
        result = ParseResult()
        try:
            if filepath.endswith(".zip"):
                return self.parse_zip(filepath, content)
            # For directories, walk and find known Takeout patterns
            takeout_path = Path(filepath)
            if takeout_path.is_dir():
                for root, dirs, files in os.walk(filepath):
                    for f in files[:1000]:
                        fp = Path(root) / f
                        try:
                            inner = fp.read_bytes()
                            fmt = self.detect_format(f, inner)
                            r = self.parse(str(fp), inner, fmt)
                            result.artifacts.extend(r.artifacts)
                        except Exception:
                            pass
        except Exception as e:
            result.errors.append(f"takeout error: {e}")
        return result

    def parse_meta_export(self, filepath: str = "", content: bytes = b"") -> ParseResult:
        return self.parse_google_takeout(filepath, content)

    def _make_artifact(self, type: str, raw_hash: str, metadata: dict, preview: str = "") -> Artifact:
        return Artifact(
            id=uuid4(), source_id=self.source_id, type=type,
            raw_hash=raw_hash, encrypted_path="",
            metadata=metadata, is_public=False,
            content_preview=preview[:500],
            created_at=datetime.now(timezone.utc).isoformat()
        )

    def _flatten_json(self, data: Any, source: str, prefix: str = "") -> List[Artifact]:
        artifacts = []
        if isinstance(data, dict):
            for k, v in list(data.items())[:20]:
                if isinstance(v, (dict, list)):
                    artifacts.extend(self._flatten_json(v, source, f"{prefix}{k}."))
                else:
                    artifacts.append(self._make_artifact(
                        "json_field",
                        hashlib.sha256(f"{prefix}{k}{v}".encode()).hexdigest(),
                        {"key": f"{prefix}{k}", "value": str(v)[:200], "source": source},
                        str(v)[:200]
                    ))
        elif isinstance(data, list):
            for i, item in enumerate(data[:50]):
                artifacts.extend(self._flatten_json(item, source, f"{prefix}[{i}]."))
        return artifacts
