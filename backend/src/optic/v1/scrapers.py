from __future__ import annotations
import hashlib
import json
import os
import re
import sqlite3
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import Request, urlopen
from uuid import UUID, uuid4
from .models import Artifact
from .parsers import ParseResult, ParserRegistry
MAX_FETCH_BYTES = 2_000_000
USER_AGENT = "OpticV1/0.1 local-self-audit"
class ProviderError(Exception):
    pass
class RateLimitError(ProviderError):
    pass
@dataclass
class ProviderUIState:
    provider: str
    label: str
    enabled: bool
    provider_missing: bool = False
    missing_credentials: list[str] = field(default_factory=list)
    reason: str = ""
    limits: dict[str, Any] = field(default_factory=dict)
    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "label": self.label,
            "enabled": self.enabled,
            "provider_missing": self.provider_missing,
            "missing_credentials": self.missing_credentials,
            "reason": self.reason,
            "limits": self.limits,
        }
class RateLimiter:
    def __init__(self, per_minute: int = 30):
        self.per_minute = max(1, per_minute)
        self._hits: dict[str, list[float]] = {}
    def check(self, key: str) -> None:
        now = time.monotonic()
        window = now - 60
        hits = [t for t in self._hits.get(key, []) if t >= window]
        if len(hits) >= self.per_minute:
            raise RateLimitError(f"rate limit exceeded for {key}")
        hits.append(now)
        self._hits[key] = hits
class SourceProvider(ABC):
    id = "base"
    label = "Source provider"
    required_env: tuple[str, ...] = ()
    def __init__(
        self,
        source_id: UUID | None = None,
        *,
        rate_limit_per_minute: int = 30,
        timeout: float = 8.0,
    ):
        self.source_id = source_id or uuid4()
        self.registry = ParserRegistry(self.source_id)
        self.timeout = timeout
        self.rate_limiter = RateLimiter(rate_limit_per_minute)
    def ui_state(self) -> ProviderUIState:
        missing = [name for name in self.required_env if not os.getenv(name)]
        return ProviderUIState(
            provider=self.id,
            label=self.label,
            enabled=not missing,
            provider_missing=bool(missing),
            missing_credentials=missing,
            reason=("Missing " + ", ".join(missing)) if missing else "",
            limits=self.limits(),
        )
    def limits(self) -> dict[str, Any]:
        return {"max_fetch_bytes": MAX_FETCH_BYTES}
    @abstractmethod
    def fetch(self, scope: dict[str, Any]) -> ParseResult:
        """Fetch user-approved scope and return parsed artifacts."""
    def _require_user_triggered(self, scope: dict[str, Any]) -> None:
        if not isinstance(scope, dict) or scope.get("user_triggered") is not True:
            raise ProviderError("provider fetch requires user_triggered=true")
    def _require_keys(self, scope: dict[str, Any], keys: Iterable[str]) -> None:
        missing = [k for k in keys if not scope.get(k)]
        if missing:
            raise ProviderError("missing scope: " + ", ".join(missing))
    def _http_get(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        max_bytes: int = MAX_FETCH_BYTES,
    ) -> tuple[bytes, dict[str, str]]:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ProviderError("only absolute http(s) URLs are allowed")
        self.rate_limiter.check(parsed.netloc.lower())
        req_headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
        if headers:
            req_headers.update(headers)
        req = Request(url, headers=req_headers)
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                data = resp.read(max_bytes + 1)
                if len(data) > max_bytes:
                    raise ProviderError(f"response exceeds {max_bytes} bytes")
                meta = {k.lower(): v for k, v in resp.headers.items()}
                meta["status"] = str(resp.status)
                meta["url"] = resp.geturl()
                return data, meta
        except HTTPError as e:
            raise ProviderError(f"http {e.code}: {url}") from e
        except URLError as e:
            raise ProviderError(f"fetch failed: {e.reason}") from e
    def _artifact(self, kind: str, raw: bytes | str, metadata: dict[str, Any], preview: str) -> Artifact:
        blob = raw.encode("utf-8", errors="replace") if isinstance(raw, str) else raw
        return Artifact(
            id=uuid4(),
            source_id=self.source_id,
            type=kind,
            raw_hash=hashlib.sha256(blob).hexdigest(),
            metadata=metadata,
            is_public=metadata.get("is_public", False),
            content_preview=preview[:500],
            created_at=datetime.now(timezone.utc).isoformat(),
        )
class _HTMLTextExtractor(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.title = ""
        self.links: list[str] = []
        self._in_title = False
        self._skip = 0
        self._chunks: list[str] = []
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript"}:
            self._skip += 1
        if tag == "title":
            self._in_title = True
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                absolute = urljoin(self.base_url, href)
                if urlparse(absolute).scheme in ("http", "https"):
                    self.links.append(absolute)
    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript"} and self._skip:
            self._skip -= 1
        if tag == "title":
            self._in_title = False
    def handle_data(self, data: str) -> None:
        text = re.sub(r"\s+", " ", data).strip()
        if not text:
            return
        if self._in_title:
            self.title = (self.title + " " + text).strip()
        elif not self._skip:
            self._chunks.append(text)
    @property
    def text(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self._chunks)).strip()
def _html_extract(url: str, content: bytes) -> tuple[str, str, list[str]]:
    parser = _HTMLTextExtractor(url)
    parser.feed(content.decode("utf-8", errors="replace"))
    links = list(dict.fromkeys(parser.links))[:200]
    return parser.title[:200], parser.text[:10_000], links
class ManualURLProvider(SourceProvider):
    id = "manual_url"
    label = "Manual URL"
    def limits(self) -> dict[str, Any]:
        return {"urls": 1, "max_fetch_bytes": MAX_FETCH_BYTES}
    def fetch(self, scope: dict[str, Any]) -> ParseResult:
        result = ParseResult()
        try:
            self._require_user_triggered(scope)
            self._require_keys(scope, ("url",))
            url = str(scope["url"])
            content, headers = self._http_get(url)
            ctype = headers.get("content-type", "")
            is_html = "html" in ctype or urlparse(url).path.lower().endswith((".html", ".htm", "/"))
            if is_html:
                title, text, links = _html_extract(headers.get("url", url), content)
                parsed = self.registry.parse(headers.get("url", url), content, "html")
                result.artifacts.extend(parsed.artifacts)
                result.warnings.extend(parsed.warnings)
                result.errors.extend(parsed.errors)
                artifact = result.artifacts[0] if result.artifacts else None
                if artifact:
                    artifact.metadata.update({"url": url, "final_url": headers.get("url", url), "title": title, "links": links})
                    artifact.content_preview = text[:500] or artifact.content_preview
                else:
                    result.artifacts.append(self._artifact("web_page", content, {
                        "url": url, "final_url": headers.get("url", url), "title": title, "links": links, "is_public": True
                    }, text))
            else:
                fmt = self.registry.detect_format(url, content)
                if fmt == "txt":
                    text = content.decode("utf-8", errors="replace")
                    result.artifacts.append(self._artifact("url_document", content, {"url": url, "content_type": ctype}, text))
                else:
                    parsed = self.registry.parse(url, content, fmt)
                    result.artifacts.extend(parsed.artifacts)
                    result.warnings.extend(parsed.warnings)
                    result.errors.extend(parsed.errors)
        except Exception as e:
            result.errors.append(str(e))
        return result
class GitHubProvider(SourceProvider):
    id = "github"
    label = "GitHub"
    def __init__(self, *args: Any, token: str | None = None, require_token: bool = False, **kwargs: Any):
        super().__init__(*args, rate_limit_per_minute=20, **kwargs)
        self.token = token or os.getenv("GITHUB_TOKEN")
        self.require_token = require_token
    def ui_state(self) -> ProviderUIState:
        if self.require_token and not self.token:
            return ProviderUIState(self.id, self.label, False, True, ["GITHUB_TOKEN"], "Missing GITHUB_TOKEN", self.limits())
        reason = "" if self.token else "No GITHUB_TOKEN. Public API works with low rate limits."
        return ProviderUIState(self.id, self.label, True, False, [], reason, self.limits())
    def limits(self) -> dict[str, Any]:
        return {"max_repos": 20, "readme_bytes": 200_000}
    def fetch(self, scope: dict[str, Any]) -> ParseResult:
        result = ParseResult()
        try:
            self._require_user_triggered(scope)
            if not self.ui_state().enabled:
                raise ProviderError(self.ui_state().reason)
            owner = str(scope.get("owner") or "").strip().lstrip("@")
            repo = str(scope.get("repo") or "").strip()
            if not owner:
                raise ProviderError("missing scope: owner")
            max_repos = max(1, min(int(scope.get("max_repos", 10)), 20))
            headers = {"Accept": "application/vnd.github+json"}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            repos = [self._repo(owner, repo, headers)] if repo else self._repos(owner, max_repos, headers)
            for item in repos:
                result.artifacts.append(self._repo_artifact(item))
                if scope.get("include_readme", True):
                    readme = self._readme(item["full_name"], headers)
                    if readme:
                        result.artifacts.append(self._artifact("github_readme", readme, {
                            "repo": item["full_name"], "url": item["html_url"], "is_public": True
                        }, readme))
        except Exception as e:
            result.errors.append(str(e))
        return result
    def _repos(self, owner: str, limit: int, headers: dict[str, str]) -> list[dict[str, Any]]:
        qs = urlencode({"per_page": limit, "sort": "updated", "type": "owner"})
        data, _ = self._http_get(f"https://api.github.com/users/{owner}/repos?{qs}", headers=headers)
        parsed = json.loads(data.decode("utf-8", errors="replace"))
        if not isinstance(parsed, list):
            raise ProviderError("GitHub repos response was not a list")
        return parsed[:limit]
    def _repo(self, owner: str, repo: str, headers: dict[str, str]) -> dict[str, Any]:
        data, _ = self._http_get(f"https://api.github.com/repos/{owner}/{repo}", headers=headers)
        parsed = json.loads(data.decode("utf-8", errors="replace"))
        if not isinstance(parsed, dict) or "full_name" not in parsed:
            raise ProviderError("GitHub repo response was invalid")
        return parsed
    def _readme(self, full_name: str, headers: dict[str, str]) -> str:
        raw_headers = dict(headers)
        raw_headers["Accept"] = "application/vnd.github.raw"
        try:
            data, _ = self._http_get(f"https://api.github.com/repos/{full_name}/readme", headers=raw_headers, max_bytes=200_000)
            return data.decode("utf-8", errors="replace")
        except ProviderError:
            return ""
    def _repo_artifact(self, repo: dict[str, Any]) -> Artifact:
        text = " ".join(str(repo.get(k) or "") for k in ("name", "description", "language"))
        return self._artifact("github_repo", json.dumps(repo, sort_keys=True), {
            "name": repo.get("name", ""),
            "full_name": repo.get("full_name", ""),
            "url": repo.get("html_url", ""),
            "stars": repo.get("stargazers_count", 0),
            "forks": repo.get("forks_count", 0),
            "language": repo.get("language", ""),
            "updated_at": repo.get("updated_at", ""),
            "is_public": True,
        }, text)
class LocalFilesystemProvider(SourceProvider):
    id = "local_filesystem"
    label = "Local filesystem index"
    def __init__(self, *args: Any, db_path: str | Path | None = None, **kwargs: Any):
        super().__init__(*args, rate_limit_per_minute=60, **kwargs)
        self.db_path = Path(db_path) if db_path else self._default_ctx_db()
    def ui_state(self) -> ProviderUIState:
        exists = self.db_path.exists()
        return ProviderUIState(self.id, self.label, exists, not exists, [], "ctxorg scan database not found" if not exists else "", self.limits())
    def limits(self) -> dict[str, Any]:
        return {"max_items": 500, "source": "ctxorg.items"}
    def fetch(self, scope: dict[str, Any]) -> ParseResult:
        result = ParseResult()
        try:
            self._require_user_triggered(scope)
            if not self.db_path.exists():
                raise ProviderError(f"ctxorg scan database not found: {self.db_path}")
            roots = [str(Path(p).expanduser()) for p in scope.get("path_prefixes", [])]
            cluster = str(scope.get("cluster") or "")
            item_ids = set(str(x) for x in scope.get("item_ids", []))
            if not roots and not cluster and not item_ids and scope.get("allow_all_indexed") is not True:
                raise ProviderError("local scope must include path_prefixes, cluster, item_ids, or allow_all_indexed=true")
            max_items = max(1, min(int(scope.get("max_items", 100)), 500))
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT id,path,kind,size,mtime,ext,state,text,cluster FROM items WHERE kind='file' ORDER BY mtime DESC LIMIT ?",
                    (max_items * 5,),
                ).fetchall()
            for row in rows:
                rec = dict(row)
                path = rec.get("path", "")
                if roots and not any(path.startswith(root) for root in roots):
                    continue
                if cluster and rec.get("cluster") != cluster:
                    continue
                if item_ids and rec.get("id") not in item_ids:
                    continue
                text = rec.get("text") or Path(path).name
                result.artifacts.append(self._artifact("local_file", f"{path}{rec.get('mtime')}{rec.get('size')}{text[:200]}", {
                    "ctxorg_id": rec.get("id"), "path": path, "size": rec.get("size"),
                    "mtime": rec.get("mtime"), "ext": rec.get("ext"), "cluster": rec.get("cluster"),
                    "state": rec.get("state"), "is_public": False,
                }, text))
                if len(result.artifacts) >= max_items:
                    break
        except Exception as e:
            result.errors.append(str(e))
        return result
    @staticmethod
    def _default_ctx_db() -> Path:
        root = Path(__file__).resolve().parents[3]
        cfg_path = root / "config.json"
        if cfg_path.exists():
            try:
                cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
                home = Path(str(cfg.get("home") or root))
                return home / str(cfg.get("state_dir", ".ctxorg/state")) / "ctx.db"
            except Exception:
                pass
        return root / ".ctxorg" / "state" / "ctx.db"
class WebsiteSnapshotProvider(SourceProvider):
    id = "website_snapshot"
    label = "Website snapshot"
    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, rate_limit_per_minute=12, **kwargs)
    def limits(self) -> dict[str, Any]:
        return {"max_pages": 10, "single_domain": True, "max_fetch_bytes": MAX_FETCH_BYTES}
    def fetch(self, scope: dict[str, Any]) -> ParseResult:
        result = ParseResult()
        try:
            self._require_user_triggered(scope)
            self._require_keys(scope, ("start_url",))
            start_url = str(scope["start_url"])
            start = urlparse(start_url)
            if start.scheme not in ("http", "https") or not start.netloc:
                raise ProviderError("start_url must be absolute http(s)")
            max_pages = max(1, min(int(scope.get("max_pages", 5)), 10))
            queue = [start_url]
            seen: set[str] = set()
            while queue and len(seen) < max_pages:
                url = queue.pop(0).split("#", 1)[0]
                if url in seen or urlparse(url).netloc.lower() != start.netloc.lower():
                    continue
                content, headers = self._http_get(url)
                final_url = headers.get("url", url).split("#", 1)[0]
                if urlparse(final_url).netloc.lower() != start.netloc.lower():
                    continue
                seen.add(final_url)
                title, text, links = _html_extract(final_url, content)
                result.artifacts.append(self._artifact("website_page", content, {
                    "url": final_url, "title": title, "links": links[:50], "is_public": True,
                }, text))
                for link in links:
                    clean = link.split("#", 1)[0]
                    if urlparse(clean).netloc.lower() == start.netloc.lower() and clean not in seen and clean not in queue:
                        queue.append(clean)
        except Exception as e:
            result.errors.append(str(e))
        return result
PROVIDERS: dict[str, type[SourceProvider]] = {
    ManualURLProvider.id: ManualURLProvider,
    GitHubProvider.id: GitHubProvider,
    LocalFilesystemProvider.id: LocalFilesystemProvider,
    WebsiteSnapshotProvider.id: WebsiteSnapshotProvider,
}
def provider_ui_states() -> list[dict[str, Any]]:
    return [provider().ui_state().as_dict() for provider in PROVIDERS.values()]
