"""Signal detection algorithms for Optic.

Provides detector implementations that analyze signals and produce detections.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any

from .models import Detection, Severity, SignalSource


class SignalDetector(ABC):
    """Base class for all signal detectors."""

    name: str = "base_detector"

    @abstractmethod
    def detect(self, content: str, source: SignalSource, metadata: dict[str, Any] | None = None) -> list[Detection]:
        """Analyze content and return detections."""
        ...

    @classmethod
    def _make_detection(
        cls,
        attribute: str,
        severity: Severity,
        confidence: float,
        location: str = "",
        description: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> Detection:
        return Detection(
            attribute=attribute,
            severity=severity,
            confidence=max(0.0, min(1.0, confidence)),
            location=location,
            description=description,
            metadata=metadata or {},
        )


class PatternDetector(SignalDetector):
    """Detect specific patterns in text content (keywords, regex patterns).

    Useful for detecting known misinformation markers, biased language, etc.
    """

    name = "pattern_detector"

    def __init__(
        self,
        patterns: dict[str, tuple[str, Severity, float]] | None = None,
        case_sensitive: bool = False,
    ):
        """
        Args:
            patterns: Dict mapping attribute names to (regex_pattern, severity, confidence).
            case_sensitive: Whether pattern matching is case-sensitive.
        """
        self.case_sensitive = case_sensitive
        self._patterns: dict[str, tuple[re.Pattern, Severity, float]] = {}

        if patterns:
            for attribute, (pattern_str, severity, confidence) in patterns.items():
                flags = 0 if case_sensitive else re.IGNORECASE
                self._patterns[attribute] = (
                    re.compile(pattern_str, flags),
                    severity,
                    confidence,
                )

    @classmethod
    def default_bias_patterns(cls) -> "PatternDetector":
        """Create a detector with common bias/manipulation patterns."""
        return cls(
            patterns={
                "loaded_language": (
                    r"\b(clearly|obviously|undeniably|surely|everyone knows|"
                    r"it's obvious that|without a doubt|needless to say|"
                    r"of course|naturally)\b",
                    Severity.MEDIUM,
                    0.6,
                ),
                "straw_man": (
                    r"\b(so you're saying|you think that|"
                    r"the opposition wants|they believe that)\b",
                    Severity.MEDIUM,
                    0.5,
                ),
                "emotional_appeal": (
                    r"\b(heartbreaking|outrageous|shocking|appalling|"
                    r"disgusting|heartwarming|inspiring|terrifying|"
                    r"heart-rending|devastating)\b",
                    Severity.LOW,
                    0.4,
                ),
                "absolute_language": (
                    r"\b(always|never|everyone|no one|all|none|"
                    r"everybody|nobody|completely|totally|absolutely)\b",
                    Severity.LOW,
                    0.3,
                ),
                "fear_mongering": (
                    r"\b(disaster|crisis|catastrophe|threat|danger|"
                    r"emergency|calamity|doom|peril|menace)\b",
                    Severity.MEDIUM,
                    0.5,
                ),
                "false_balance": (
                    r"\b(some people say|critics argue|on both sides|"
                    r"there are two sides|both sides of the aisle)\b",
                    Severity.LOW,
                    0.3,
                ),
            }
        )

    def detect(self, content: str, source: SignalSource, metadata: dict[str, Any] | None = None) -> list[Detection]:
        detections: list[Detection] = []
        if source not in (SignalSource.TEXT, SignalSource.NEWS_ARTICLE, SignalSource.SOCIAL_MEDIA, SignalSource.SPEECH):
            return detections

        for attribute, (pattern, severity, confidence) in self._patterns.items():
            matches = list(pattern.finditer(content))
            if matches:
                for m in matches[:5]:  # cap at 5 per attribute
                    start = max(0, m.start() - 20)
                    end = min(len(content), m.end() + 20)
                    context = content[start:end].strip()
                    detections.append(self._make_detection(
                        attribute=attribute,
                        severity=severity,
                        confidence=min(1.0, confidence * (1.0 + 0.1 * len(matches))),
                        location=context,
                        description=f"Found {len(matches)} instance(s) of '{attribute}'",
                        metadata={"match_count": len(matches), "matched_text": m.group()},
                    ))

        return detections


class ThresholdDetector(SignalDetector):
    """Detect issues based on numeric thresholds in metadata.

    Useful for detecting anomalies in engagement metrics,
    source reliability scores, etc.
    """

    name = "threshold_detector"

    def __init__(self, thresholds: dict[str, tuple[float, float, Severity]] | None = None):
        """
        Args:
            thresholds: Dict mapping metric names to (min, max, severity).
                        Values outside [min, max] trigger detection.
        """
        self.thresholds: dict[str, tuple[float, float, Severity]] = thresholds or {}

    def detect(self, content: str, source: SignalSource, metadata: dict[str, Any] | None = None) -> list[Detection]:
        detections: list[Detection] = []
        meta = metadata or {}

        for metric, (min_val, max_val, severity) in self.thresholds.items():
            value = meta.get(metric)
            if value is None:
                continue
            try:
                float_val = float(value)
            except (ValueError, TypeError):
                continue

            if float_val < min_val or float_val > max_val:
                direction = "below" if float_val < min_val else "above"
                detections.append(self._make_detection(
                    attribute=f"metric_outlier_{metric}",
                    severity=severity,
                    confidence=0.7,
                    location=f"Metric '{metric}' = {float_val}",
                    description=f"Value {float_val} is {direction} threshold [{min_val}, {max_val}]",
                    metadata={"metric": metric, "value": float_val, "min": min_val, "max": max_val},
                ))

        return detections


class AnomalyDetector(SignalDetector):
    """Statistical anomaly detection in signal content.

    Detects unusual patterns like excessive repetition,
    abnormal length, unusual character distributions, etc.
    """

    name = "anomaly_detector"

    def __init__(self, repetition_threshold: float = 0.3):
        self.repetition_threshold = repetition_threshold

    def detect(self, content: str, source: SignalSource, metadata: dict[str, Any] | None = None) -> list[Detection]:
        detections: list[Detection] = []

        # Check for excessive repetition of words
        words = content.lower().split()
        if len(words) > 5:
            word_counts = {}
            for w in words:
                word_counts[w] = word_counts.get(w, 0) + 1
            most_common_word = max(word_counts, key=word_counts.get)
            most_common_ratio = word_counts[most_common_word] / len(words)

            if most_common_ratio > self.repetition_threshold:
                detections.append(self._make_detection(
                    attribute="excessive_repetition",
                    severity=Severity.LOW,
                    confidence=min(0.8, most_common_ratio),
                    location=f"Word '{most_common_word}' appears {word_counts[most_common_word]} times",
                    description=f"Repetition ratio {most_common_ratio:.2f} exceeds threshold {self.repetition_threshold}",
                    metadata={"most_common_word": most_common_word, "ratio": most_common_ratio, "total_words": len(words)},
                ))

        # Check for excessive ALL CAPS
        if len(content) > 50:
            upper_chars = sum(1 for c in content if c.isalpha() and c.isupper())
            total_alpha = sum(1 for c in content if c.isalpha())
            if total_alpha > 0 and upper_chars / total_alpha > 0.4:
                detections.append(self._make_detection(
                    attribute="excessive_caps",
                    severity=Severity.LOW,
                    confidence=0.6,
                    location=f"{upper_chars}/{total_alpha} uppercase characters",
                    description=f"Uppercase ratio {upper_chars/total_alpha:.2f} suggests shouting",
                    metadata={"upper_ratio": upper_chars / total_alpha},
                ))

        # Check for unusual number of punctuation marks
        excl_marks = content.count("!")
        if len(content) > 20:
            if excl_marks > 3:
                detections.append(self._make_detection(
                    attribute="excessive_exclamation",
                    severity=Severity.INFO,
                    confidence=0.4,
                    description=f"Found {excl_marks} exclamation marks",
                    metadata={"exclamation_count": excl_marks},
                ))

        return detections
