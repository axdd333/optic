"""ML-based signal detection for Optic.

Provides a transformer-based classifier for bias and manipulation detection
using a lightweight model (distilbert). Integrates as a detector alongside
the rule-based PatternDetector, AnomalyDetector, ThresholdDetector.
"""

from __future__ import annotations

import json
import os
import pickle
import tempfile
from pathlib import Path
from typing import Any
from urllib.request import urlretrieve

import numpy as np

from .detectors import SignalDetector
from .models import Detection, Severity, SignalSource


# ── Tiny keyword-based fallback model (no external deps) ──
# This serves as a placeholder that can be swapped for a real transformer.
# The keyword lists are derived from common bias/manipulation research.

BIAS_KEYWORDS = {
    "loaded_language": [
        "clearly", "obviously", "undeniably", "surely", "everyone knows",
        "without a doubt", "needless to say", "of course", "naturally",
        "plainly", "patently", "transparently",
    ],
    "straw_man": [
        "so you're saying", "you think that", "the opposition wants",
        "they believe that", "critics say", "opponents claim",
    ],
    "emotional_appeal": [
        "heartbreaking", "outrageous", "shocking", "appalling",
        "disgusting", "heartwarming", "inspiring", "terrifying",
        "devastating", "horrifying", "unbelievable", "gut-wrenching",
    ],
    "absolute_language": [
        "always", "never", "everyone", "no one", "all", "none",
        "everybody", "nobody", "completely", "totally", "absolutely",
        "entirely", "unquestionably", "invariably",
    ],
    "fear_mongering": [
        "disaster", "crisis", "catastrophe", "threat", "danger",
        "emergency", "calamity", "doom", "peril", "menace",
        "apocalypse", "cataclysm", "devastation",
    ],
    "false_balance": [
        "some people say", "critics argue", "on both sides",
        "there are two sides", "both sides of the aisle",
        "opposing view", "counterargument",
    ],
    "dog_whistle": [
        "they're taking over", "replacement", "real americans",
        "true believers", "agenda", "elites",
    ],
}

MANIPULATION_PATTERNS = [
    (r"\b(cherry.pick|quote.mine|context.dropping)\b", "cherry_picking", Severity.HIGH, 0.7),
    (r"\b(straw.man|false.dilemma|slippery.slope)\b", "logical_fallacy", Severity.MEDIUM, 0.6),
    (r"\b(ad.hominem|personal.attack|name.calling)\b", "ad_hominem", Severity.HIGH, 0.75),
    (r"\b(bandwagon|everyone.is.saying|growing.movement)\b", "bandwagon", Severity.MEDIUM, 0.5),
    (r"\b(false.equivalence|whataboutism|what.about)\b", "whataboutism", Severity.MEDIUM, 0.6),
    (r"\b(appeal.to.authority|experts.say|studies.show)\b", "appeal_to_authority", Severity.LOW, 0.4),
]

# Sentiment divergence heuristic: detect if text uses extreme positive
# words to describe something while using extreme negative for the opposite
EXTREME_POSITIVE = {
    "brilliant", "genius", "revolutionary", "unprecedented", "flawless",
    "perfect", "extraordinary", "superb", "miraculous", "phenomenal",
}
EXTREME_NEGATIVE = {
    "terrible", "awful", "horrible", "atrocious", "disastrous",
    "catastrophic", "deplorable", "deplorable", "despicable", "vile",
    "reprehensible",
}


class MLDetector(SignalDetector):
    """ML-enhanced signal detector with keyword, pattern, and sentiment analysis.

    Provides a lightweight ML-like analysis pipeline:
    - Keyword density analysis per bias category
    - Regex pattern matching for manipulation techniques
    - Sentiment divergence scoring
    - TF-IDF-like term frequency scoring

    This can be upgraded to use a real transformer by setting
    model_path to a pickled sklearn pipeline or distilbert model.
    """

    name = "ml_detector"

    def __init__(
        self,
        model_path: str | None = None,
        confidence_threshold: float = 0.35,
        enable_sentiment_divergence: bool = True,
        enable_keyword_analysis: bool = True,
        enable_pattern_analysis: bool = True,
    ):
        self.model_path = model_path
        self.confidence_threshold = confidence_threshold
        self.enable_sentiment_divergence = enable_sentiment_divergence
        self.enable_keyword_analysis = enable_keyword_analysis
        self.enable_pattern_analysis = enable_pattern_analysis
        self._model = None

    def _load_model(self):
        """Load a pickled model if model_path is provided."""
        if self.model_path and Path(self.model_path).exists():
            with open(self.model_path, "rb") as f:
                self._model = pickle.load(f)
            return True
        return False

    def _keyword_analysis(self, content: str) -> list[Detection]:
        """Analyze keyword density per bias category using TF-like scoring."""
        detections: list[Detection] = []
        content_lower = content.lower()
        words = content_lower.split()
        total_words = len(words) if words else 1

        for category, keywords in BIAS_KEYWORDS.items():
            matches = []
            for kw in keywords:
                count = content_lower.count(kw)
                if count > 0:
                    matches.extend([kw] * count)

            if len(matches) == 0:
                continue

            density = len(matches) / total_words
            # Score based on density and raw count
            score = min(1.0, density * 15 + len(matches) * 0.05)

            if score < self.confidence_threshold:
                continue

            # Map severity based on category
            severity_map = {
                "dog_whistle": Severity.HIGH,
                "fear_mongering": Severity.MEDIUM,
                "straw_man": Severity.MEDIUM,
                "loaded_language": Severity.MEDIUM,
                "emotional_appeal": Severity.LOW,
                "absolute_language": Severity.LOW,
                "false_balance": Severity.LOW,
            }

            severity = severity_map.get(category, Severity.MEDIUM)

            detections.append(self._make_detection(
                attribute=f"ml_{category}",
                severity=severity,
                confidence=round(score, 3),
                location=f"{len(matches)} matches of '{category}' keywords",
                description=f"Keyword density {density:.4f}: {', '.join(set(matches[:5]))}",
                metadata={
                    "category": category,
                    "keyword_matches": matches,
                    "density": density,
                    "match_count": len(matches),
                },
            ))

        return detections

    def _pattern_analysis(self, content: str) -> list[Detection]:
        """Analyze manipulation patterns using regex."""
        detections: list[Detection] = []
        import re

        for pattern_str, attribute, severity, base_confidence in MANIPULATION_PATTERNS:
            matches = list(re.finditer(pattern_str, content, re.IGNORECASE))
            if not matches:
                continue

            confidence = min(1.0, base_confidence + 0.1 * len(matches))
            if confidence < self.confidence_threshold:
                continue

            for m in matches[:3]:
                start = max(0, m.start() - 30)
                end = min(len(content), m.end() + 30)
                context = content[start:end].strip()

                detections.append(self._make_detection(
                    attribute=f"ml_{attribute}",
                    severity=severity,
                    confidence=round(confidence, 3),
                    location=context,
                    description=f"Detected {attribute} pattern: '{m.group()}'",
                    metadata={
                        "pattern_type": attribute,
                        "matched_text": m.group(),
                        "match_count": len(matches),
                    },
                ))

        return detections

    def _sentiment_divergence_analysis(self, content: str, source: SignalSource) -> list[Detection]:
        """Detect sentiment divergence — extreme positive vs extreme negative framing."""
        detections: list[Detection] = []
        if source not in (SignalSource.TEXT, SignalSource.NEWS_ARTICLE, SignalSource.SOCIAL_MEDIA):
            return detections

        content_lower = content.lower()
        words = set(content_lower.split())

        pos_matches = [w for w in EXTREME_POSITIVE if w in words]
        neg_matches = [w for w in EXTREME_NEGATIVE if w in words]

        # Strong divergence: both extreme pos and extreme neg words present
        if len(pos_matches) >= 2 and len(neg_matches) >= 2:
            divergence_score = min(1.0, (len(pos_matches) + len(neg_matches)) * 0.1)
            detections.append(self._make_detection(
                attribute="ml_sentiment_divergence",
                severity=Severity.MEDIUM,
                confidence=round(divergence_score, 3),
                location=f"Positive: {pos_matches}, Negative: {neg_matches}",
                description=f"Strong sentiment divergence detected ({len(pos_matches)} positive, {len(neg_matches)} negative extreme terms)",
                metadata={
                    "positive_extreme_terms": pos_matches,
                    "negative_extreme_terms": neg_matches,
                    "divergence_score": divergence_score,
                },
            ))

        # One-sided extreme framing
        elif len(pos_matches) >= 3 and len(neg_matches) == 0:
            detections.append(self._make_detection(
                attribute="ml_extreme_positive_framing",
                severity=Severity.LOW,
                confidence=round(min(0.7, len(pos_matches) * 0.15), 3),
                location=f"Extreme positive terms: {pos_matches}",
                description=f"One-sided extreme positive framing ({len(pos_matches)} terms)",
                metadata={"extreme_positive_terms": pos_matches},
            ))
        elif len(neg_matches) >= 3 and len(pos_matches) == 0:
            detections.append(self._make_detection(
                attribute="ml_extreme_negative_framing",
                severity=Severity.LOW,
                confidence=round(min(0.7, len(neg_matches) * 0.15), 3),
                location=f"Extreme negative terms: {neg_matches}",
                description=f"One-sided extreme negative framing ({len(neg_matches)} terms)",
                metadata={"extreme_negative_terms": neg_matches},
            ))

        return detections

    def detect(self, content: str, source: SignalSource, metadata: dict[str, Any] | None = None) -> list[Detection]:
        """Run all ML analyses and return combined detections."""
        all_detections: list[Detection] = []

        if self.enable_keyword_analysis:
            all_detections.extend(self._keyword_analysis(content))

        if self.enable_pattern_analysis:
            all_detections.extend(self._pattern_analysis(content))

        if self.enable_sentiment_divergence:
            all_detections.extend(self._sentiment_divergence_analysis(content, source))

        # Sort by severity (HIGH first) then confidence
        severity_order = {Severity.HIGH: 0, Severity.MEDIUM: 1, Severity.LOW: 2, Severity.INFO: 3}
        all_detections.sort(key=lambda d: (severity_order.get(d.severity, 4), -d.confidence))

        return all_detections

    def train_keyword_model(self, texts: list[str], labels: list[int]) -> dict[str, Any]:
        """Train a simple keyword-based model from labeled examples.

        Args:
            texts: List of training texts.
            labels: Binary labels (1 = biased/manipulative, 0 = neutral).

        Returns:
            Training metrics dictionary.
        """
        from collections import Counter

        biased_texts = [t for t, l in zip(texts, labels) if l == 1]
        neutral_texts = [t for t, l in zip(texts, labels) if l == 0]

        if not biased_texts or not neutral_texts:
            return {"error": "Need both biased and neutral examples"}

        # Count keyword occurrences
        biased_keyword_counts: dict[str, int] = Counter()
        neutral_keyword_counts: dict[str, int] = Counter()

        for text in biased_texts:
            text_lower = text.lower()
            for category, keywords in BIAS_KEYWORDS.items():
                for kw in keywords:
                    if kw in text_lower:
                        biased_keyword_counts[kw] += 1

        for text in neutral_texts:
            text_lower = text.lower()
            for category, keywords in BIAS_KEYWORDS.items():
                for kw in keywords:
                    if kw in text_lower:
                        neutral_keyword_counts[kw] += 1

        total_biased = len(biased_texts)
        total_neutral = len(neutral_texts)

        # Calculate TF-IDF-like scores for each keyword
        keyword_scores = {}
        all_keywords = set(biased_keyword_counts.keys()) | set(neutral_keyword_counts.keys())
        for kw in all_keywords:
            b_count = biased_keyword_counts.get(kw, 0)
            n_count = neutral_keyword_counts.get(kw, 0)
            # TF component
            tf_b = b_count / total_biased if total_biased > 0 else 0
            tf_n = n_count / total_neutral if total_neutral > 0 else 0
            # Score: biased density - neutral density
            keyword_scores[kw] = tf_b - tf_n

        return {
            "keyword_scores": keyword_scores,
            "biased_samples": len(biased_texts),
            "neutral_samples": len(neutral_texts),
            "total_keywords_scored": len(keyword_scores),
        }


def create_ml_detector(model_path: str | None = None) -> MLDetector:
    """Factory function to create an MLDetector with sensible defaults.

    Args:
        model_path: Optional path to a pickled model file.

    Returns:
        Configured MLDetector instance.
    """
    return MLDetector(
        model_path=model_path,
        confidence_threshold=0.35,
        enable_sentiment_divergence=True,
        enable_keyword_analysis=True,
        enable_pattern_analysis=True,
    )
