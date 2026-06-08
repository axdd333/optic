"""Dependency-free entity extraction and linking for Optic V1 evidence."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from email.utils import getaddresses
from pathlib import Path
from typing import Any, DefaultDict, Iterable, Optional
from urllib.parse import urlparse
from uuid import UUID, uuid4

from .models import Artifact, Entity, ParsedSpan


EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
URL_RE = re.compile(r"https?://[^\s\"'<>),]+", re.I)
HANDLE_RE = re.compile(r"(?<![\w.])@([A-Za-z0-9_][A-Za-z0-9_.-]{1,38})\b")
ORG_RE = re.compile(r"\b([A-Z][A-Za-z0-9&'.-]*(?:\s+[A-Z][A-Za-z0-9&'.-]*){0,5}\s+(?:Inc|LLC|Ltd|Corp|Corporation|Company|Labs?|Studio|University|College|Institute|Foundation|Ventures|Capital|Partners|Group|Bank|School))\b")
PERSON_RE = re.compile(r"\b([A-Z][a-z]+(?:[-'][A-Z][a-z]+)?(?:\s+[A-Z][a-z]+(?:[-'][A-Z][a-z]+)?){1,3})\b")
PLATFORM_HANDLE_RE = re.compile(r"(?:github|linkedin|twitter|x|instagram|tiktok|reddit)\.com/(?:in/|u/|user/)?([A-Za-z0-9_.-]{2,64})", re.I)

GENERIC_LOCAL_PARTS = {"admin", "billing", "contact", "hello", "help", "hi", "info", "mail", "no-reply", "noreply", "notifications", "privacy", "sales", "security", "support", "team"}
COMMON_NAME_FALSE_POSITIVES = {"All Rights", "Best Regards", "Browser History", "Calendar Event", "Content Type", "Created At", "Dear Sir", "From The", "Google Takeout", "Local Folder", "New York", "Optic V", "Parse Result", "Privacy Policy", "Raw Hash", "Source Type", "Terms Of", "United States"}
CONTACT_KEYS = {"author", "by", "creator", "display_name", "from", "full_name", "name", "owner", "sender", "to", "user", "user_label"}
TEXT_KEYS = {"bio", "company", "description", "employer", "headline", "key", "path", "source", "subject", "summary", "title", "url", "value"}


@dataclass
class _Mention:
    kind: str
    value: str
    artifact_id: UUID
    source_id: UUID
    span_id: Optional[UUID] = None
    name_hint: str = ""
    handle_hint: str = ""
    confidence: float = 0.6
    aliases: set[str] = field(default_factory=set)


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[int, int] = {}

    def add(self, i: int) -> None:
        self.parent.setdefault(i, i)

    def find(self, i: int) -> int:
        p = self.parent.setdefault(i, i)
        if p != i:
            self.parent[i] = self.find(p)
        return self.parent[i]

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


class EntityResolver:
    """Extract and link named entities from Artifact and ParsedSpan data."""

    def __init__(self, min_name_confidence: float = 0.55) -> None:
        self.min_name_confidence = min_name_confidence

    def resolve(self, artifacts: Iterable[Artifact], spans: Optional[Iterable[ParsedSpan]] = None) -> list[Entity]:
        artifact_list = list(artifacts)
        mentions: list[_Mention] = []
        for artifact in artifact_list:
            mentions.extend(self.extract_from_artifact(artifact))

        artifact_sources = {a.id: a.source_id for a in artifact_list}
        for span in spans or []:
            source_id = artifact_sources.get(span.artifact_id, uuid4())
            mentions.extend(self.extract_from_span(span, source_id))

        if not mentions:
            return []

        groups = self._link_mentions(mentions)
        entities = [self._group_to_entity(group) for group in groups]
        self._attach_domain_email_groups(entities, mentions)
        return sorted(
            entities,
            key=lambda e: (-e.confidence, e.type, e.name.lower(), e.canonical_handle),
        )

    def extract_from_artifact(self, artifact: Artifact) -> list[_Mention]:
        mentions: list[_Mention] = []
        metadata = artifact.metadata or {}
        contact_texts = self._contact_values(metadata)
        text = self._artifact_text(artifact)

        for display, email in getaddresses(contact_texts):
            if email:
                mentions.append(self._email_mention(email, artifact, name_hint=display))
            if display and self._looks_like_person(display):
                mentions.append(self._person_mention(display, artifact, 0.78))

        mentions.extend(self._extract_text_mentions(text, artifact.id, artifact.source_id))
        return mentions

    def extract_from_span(self, span: ParsedSpan, source_id: UUID) -> list[_Mention]:
        return self._extract_text_mentions(
            span.text or "",
            span.artifact_id,
            source_id,
            span.id,
            base_confidence=0.58,
        )

    def _extract_text_mentions(
        self,
        text: str,
        artifact_id: UUID,
        source_id: UUID,
        span_id: Optional[UUID] = None,
        base_confidence: float = 0.6,
    ) -> list[_Mention]:
        mentions: list[_Mention] = []
        if not text:
            return mentions

        for email in sorted(set(EMAIL_RE.findall(text))):
            mentions.append(self._email_mention(email, artifact_id, source_id, span_id=span_id))

        for domain in self._domains_from_text(text):
            mentions.append(_Mention(kind="domain", value=domain, artifact_id=artifact_id, source_id=source_id, span_id=span_id, confidence=0.7))

        for handle in self._handles_from_text(text):
            norm = self._norm_handle(handle)
            mentions.append(_Mention(kind="account", value=norm, artifact_id=artifact_id, source_id=source_id, span_id=span_id, handle_hint=norm, confidence=0.72, aliases={f"@{norm}"}))

        for org in sorted(set(m.group(1).strip() for m in ORG_RE.finditer(text))):
            mentions.append(_Mention(kind="org", value=self._clean_name(org), artifact_id=artifact_id, source_id=source_id, span_id=span_id, confidence=0.74))

        for name in sorted(set(m.group(1).strip() for m in PERSON_RE.finditer(text))):
            if self._looks_like_person(name):
                mentions.append(_Mention(kind="person", value=self._clean_name(name), artifact_id=artifact_id, source_id=source_id, span_id=span_id, confidence=base_confidence))

        return mentions

    def _link_mentions(self, mentions: list[_Mention]) -> list[list[_Mention]]:
        uf = _UnionFind()
        keys: DefaultDict[str, list[int]] = defaultdict(list)

        for i, mention in enumerate(mentions):
            uf.add(i)
            for key in self._link_keys(mention):
                keys[key].append(i)

        for indices in keys.values():
            if len(indices) < 2:
                continue
            first = indices[0]
            for other in indices[1:]:
                uf.union(first, other)

        # Link names, handles, and emails that co-occur in the same artifact.
        by_artifact: DefaultDict[UUID, list[int]] = defaultdict(list)
        for i, mention in enumerate(mentions):
            by_artifact[mention.artifact_id].append(i)
        for indices in by_artifact.values():
            people = [i for i in indices if mentions[i].kind == "person"]
            identities = [i for i in indices if mentions[i].kind in {"account", "email"}]
            if len(people) == 1 and identities:
                for other in identities:
                    if self._handle_matches_name(mentions[other], mentions[people[0]].value):
                        uf.union(people[0], other)

        grouped: DefaultDict[int, list[_Mention]] = defaultdict(list)
        for i, mention in enumerate(mentions):
            grouped[uf.find(i)].append(mention)
        return list(grouped.values())

    def _group_to_entity(self, group: list[_Mention]) -> Entity:
        kind = self._entity_type(group)
        names = [m.name_hint or m.value for m in group if m.kind == "person"]
        names.extend(m.name_hint for m in group if m.name_hint and kind == "person")
        names.extend(m.value for m in group if m.kind in {"org", "domain"} and kind == m.kind)
        handles = [m.handle_hint or m.value for m in group if m.kind == "account"]
        emails = [m.value for m in group if m.kind == "email"]
        domains = sorted({self._email_domain(e) for e in emails if self._email_domain(e)})
        domains.extend(m.value for m in group if m.kind == "domain")

        canonical_name = self._canonical_name(kind, names, handles, emails, domains)
        canonical_handle = self._canonical_handle(handles, emails)
        aliases = self._aliases(group, canonical_name, canonical_handle)
        artifact_ids = sorted({str(m.artifact_id) for m in group})
        source_ids = sorted({str(m.source_id) for m in group})
        span_ids = sorted({str(m.span_id) for m in group if m.span_id})

        return Entity(
            id=uuid4(), type=kind, name=canonical_name, canonical_handle=canonical_handle,
            aliases=aliases, confidence=self._confidence(group),
            metadata={"artifact_ids": artifact_ids, "source_ids": source_ids, "span_ids": span_ids, "mention_count": len(group), "emails": sorted(set(emails)), "domains": sorted(set(domains)), "handles": sorted(set(handles))},
        )

    def _link_keys(self, mention: _Mention) -> list[str]:
        keys: list[str] = []
        if mention.kind == "email" and "@" in mention.value:
            local, _domain = mention.value.split("@", 1)
            keys.append(f"email:{mention.value}")
            if mention.name_hint:
                keys.append(f"name:{self._slug(mention.name_hint)}")
            if local not in GENERIC_LOCAL_PARTS:
                keys.append(f"local:{self._slug(local)}")
        elif mention.kind == "domain":
            keys.append(f"domain:{mention.value}")
        elif mention.kind == "account":
            handle = self._norm_handle(mention.value)
            keys.append(f"handle:{handle}")
            slug = self._slug(handle)
            if slug and slug not in GENERIC_LOCAL_PARTS:
                keys.append(f"local:{slug}")
                keys.append(f"name:{slug}")
        elif mention.kind in {"person", "org"}:
            keys.append(f"{mention.kind}:{self._slug(mention.value)}")
            if mention.kind == "person":
                keys.append(f"name:{self._slug(mention.value)}")
        return keys

    def _entity_type(self, group: list[_Mention]) -> str:
        counts = Counter(m.kind for m in group)
        if counts["person"] or any(m.name_hint for m in group):
            return "person"
        if counts["org"]:
            return "org"
        if counts["account"]:
            return "account"
        if counts["email"]:
            return "email_domain" if len({self._email_domain(m.value) for m in group}) == 1 else "email"
        return "domain"

    def _attach_domain_email_groups(self, entities: list[Entity], mentions: list[_Mention]) -> None:
        by_domain: DefaultDict[str, set[str]] = defaultdict(set)
        for mention in mentions:
            if mention.kind == "email":
                by_domain[self._email_domain(mention.value)].add(mention.value)
        for entity in entities:
            domains = entity.metadata.get("domains", [])
            if entity.type == "domain" and entity.name in by_domain:
                entity.metadata["emails"] = sorted(by_domain[entity.name])
            elif domains:
                entity.metadata["domain_email_count"] = sum(len(by_domain[d]) for d in domains)

    def _canonical_name(self, kind: str, names: list[str], handles: list[str], emails: list[str], domains: list[str]) -> str:
        if names:
            return Counter(self._clean_name(n) for n in names).most_common(1)[0][0]
        if kind in {"domain", "email_domain"} and domains:
            return Counter(domains).most_common(1)[0][0]
        if handles:
            return self._handle_to_name(Counter(handles).most_common(1)[0][0])
        if emails:
            return Counter(emails).most_common(1)[0][0]
        return "Unknown entity"

    def _canonical_handle(self, handles: list[str], emails: list[str]) -> str:
        if handles:
            return f"@{Counter(handles).most_common(1)[0][0]}"
        if emails:
            local = Counter(e.split("@", 1)[0] for e in emails).most_common(1)[0][0]
            return "" if local in GENERIC_LOCAL_PARTS else f"@{local}"
        return ""

    def _aliases(self, group: list[_Mention], name: str, handle: str) -> list[str]:
        aliases: set[str] = set()
        for mention in group:
            aliases.add(mention.value)
            aliases.update(mention.aliases)
            if mention.name_hint:
                aliases.add(mention.name_hint)
            if mention.handle_hint:
                aliases.add(f"@{mention.handle_hint}")
        aliases.discard(name)
        if handle:
            aliases.discard(handle)
        return sorted(a for a in aliases if a)

    def _confidence(self, group: list[_Mention]) -> float:
        base = max(m.confidence for m in group)
        evidence_bonus = min(0.2, (len({m.artifact_id for m in group}) - 1) * 0.05)
        link_bonus = 0.08 if len({m.kind for m in group}) > 1 else 0.0
        return round(min(0.99, base + evidence_bonus + link_bonus), 3)

    def _artifact_text(self, artifact: Artifact) -> str:
        parts = [artifact.content_preview or "", artifact.type or ""]
        for key, value in (artifact.metadata or {}).items():
            key_l = str(key).lower()
            if key_l in CONTACT_KEYS or key_l in TEXT_KEYS:
                parts.append(self._stringify(value))
        return "\n".join(p for p in parts if p)[:10000]

    def _contact_values(self, metadata: dict[str, Any]) -> list[str]:
        values: list[str] = []
        for key, value in metadata.items():
            if str(key).lower() in CONTACT_KEYS:
                values.append(self._stringify(value))
        return values

    def _email_mention(
        self,
        email: str,
        artifact: Artifact | UUID,
        source_id: Optional[UUID] = None,
        name_hint: str = "",
        span_id: Optional[UUID] = None,
    ) -> _Mention:
        artifact_id = artifact.id if isinstance(artifact, Artifact) else artifact
        sid = artifact.source_id if isinstance(artifact, Artifact) else source_id
        value = email.strip().lower().strip(".,;:)]}")
        local = value.split("@", 1)[0]
        return _Mention(kind="email", value=value, artifact_id=artifact_id, source_id=sid or uuid4(), span_id=span_id, name_hint=self._clean_name(name_hint) if self._looks_like_person(name_hint) else "", handle_hint="" if local in GENERIC_LOCAL_PARTS else self._norm_handle(local), confidence=0.86, aliases={value, self._email_domain(value)})

    def _person_mention(self, name: str, artifact: Artifact, confidence: float) -> _Mention:
        return _Mention(kind="person", value=self._clean_name(name), artifact_id=artifact.id, source_id=artifact.source_id, confidence=confidence)

    def _domains_from_text(self, text: str) -> list[str]:
        domains = {self._email_domain(email) for email in EMAIL_RE.findall(text)}
        for url in URL_RE.findall(text):
            host = urlparse(url).netloc.lower().split("@")[-1].split(":")[0]
            if host.startswith("www."):
                host = host[4:]
            if self._valid_domain(host):
                domains.add(host)
        return sorted(d for d in domains if d)

    def _handles_from_text(self, text: str) -> list[str]:
        handles = {m.group(1) for m in HANDLE_RE.finditer(text)}
        handles.update(m.group(1) for m in PLATFORM_HANDLE_RE.finditer(text))
        return sorted(h for h in handles if not self._valid_domain(h))

    @staticmethod
    def _email_domain(email: str) -> str:
        return email.split("@", 1)[1].lower() if "@" in email else ""

    @staticmethod
    def _valid_domain(value: str) -> bool:
        return bool(value and "." in value and not value.endswith("."))

    @staticmethod
    def _norm_handle(value: str) -> str:
        return value.strip().lstrip("@").strip("/").lower()

    @staticmethod
    def _handle_to_name(handle: str) -> str:
        return re.sub(r"[_ .-]+", " ", handle).strip().title()

    @staticmethod
    def _slug(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", value.lower())

    @staticmethod
    def _clean_name(value: str) -> str:
        value = re.sub(r"\s+", " ", str(value).strip().strip("\"'`.,;:"))
        return value[:120]

    def _looks_like_person(self, value: str) -> bool:
        value = self._clean_name(value)
        if not value or value in COMMON_NAME_FALSE_POSITIVES:
            return False
        if "@" in value or self._valid_domain(value.lower()):
            return False
        words = value.split()
        if not 2 <= len(words) <= 4:
            return False
        if any(len(w) < 2 for w in words):
            return False
        return all(w[:1].isupper() for w in words)

    def _handle_matches_name(self, mention: _Mention, name: str) -> bool:
        handle = mention.handle_hint or mention.value.split("@", 1)[0]
        return self._slug(handle) == self._slug(name)

    def _stringify(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, (list, tuple, set)):
            return " ".join(self._stringify(v) for v in value)
        if isinstance(value, dict):
            return " ".join(self._stringify(v) for v in value.values())
        if isinstance(value, Path):
            return str(value)
        return str(value)
