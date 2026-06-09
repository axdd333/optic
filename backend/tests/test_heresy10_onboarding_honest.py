"""
Regression tests for Heresy 10 fix (commit 4e8dd96):
  - Onboarding no longer has fake data.
  - No hardcoded numbers like '30+' or '115,000+'.
  - Source labels come from API (api('/sources')), not hardcoded arrays.
  - Counts show honest states ('—' or '0'), not fake defaults.
  - Lenses default to 0 not 9.
  - Health check uses api('/health') proxy, not localhost:3003 hardcode.

Before the fix — 5 violations:
  1. '30+'/'115,000+' defaults → — (honest empty state)
  2. Hardcoded mock names → real source labels via api('/sources')
  3. Math.random() fake counts → — (honest)
  4. '||9' lens default → '||0' (honest)
  5. localhost:3003 hardcode → api('/health') proxy path
"""

import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _onboarding_html_path() -> Path:
    return (
        Path(__file__).resolve().parent.parent
        / "src" / "optic" / "v1" / "static" / "onboarding.html"
    )


def _onboarding_js_text() -> str:
    """Extract the JavaScript body from onboarding.html (<script>...</script>)."""
    html = _onboarding_html_path().read_text()
    match = re.search(r"<script>(.*?)</script>", html, re.DOTALL)
    assert match is not None, "onboarding.html must contain a <script> block"
    return match.group(1)


# ---------------------------------------------------------------------------
# VIOLATION 1: No fake counts ('30+', '115,000+')
# ---------------------------------------------------------------------------

class TestNoFakeCounts:
    """Heresy 10 Violation 1: '30+'/'115,000+' defaults must be removed."""

    def test_no_30_plus_in_file(self):
        """onboarding.html must not contain the hardcoded '30+' default."""
        html = _onboarding_html_path().read_text()
        assert "30+" not in html, (
            "Violation 1: '30+' fake workstream count must be removed from onboarding.html"
        )

    def test_no_115000_plus_in_file(self):
        """onboarding.html must not contain the hardcoded '115,000+' default."""
        html = _onboarding_html_path().read_text()
        assert "115,000" not in html, (
            "Violation 1: '115,000+' fake file count must be removed from onboarding.html"
        )

    def test_honest_empty_state_shows_em_dash(self):
        """The file_count and ws_count defaults should show '—' (em dash) not fake numbers."""
        js = _onboarding_js_text()
        # After the fix, the onEnter handler for the scope step uses '—' as fallback
        assert "'—'" in js, (
            "Violation 1: Empty state should show '—' (em dash), not fake numbers"
        )

    def test_catch_block_also_uses_em_dash(self):
        """When the API call fails, both counts should fall back to '—'."""
        js = _onboarding_js_text()
        # The catch block should set both to '—'
        em_dash_count = js.count("'—'")
        assert em_dash_count >= 2, (
            f"Expected at least 2 '—' fallbacks (ws_count + file_count), found {em_dash_count}"
        )


# ---------------------------------------------------------------------------
# VIOLATION 2: No hardcoded mock source names
# ---------------------------------------------------------------------------

class TestNoHardcodedMockSources:
    """Heresy 10 Violation 2: Hardcoded mock names must be removed."""

    def test_no_mock_array_in_file(self):
        """The old mock array ['Optic','Gurm','Furion',...] must be gone."""
        html = _onboarding_html_path().read_text()
        # Check for the old hardcoded array
        assert "const mock=[" not in html, (
            "Violation 2: Hardcoded mock source array must be removed"
        )
        # Check that the old hardcoded array of 10 mock names is not present
        # as a JS array literal in the loadWorkstreams function
        js = _onboarding_js_text()
        assert "['Optic','Gurm','Furion'" not in js, (
            "Violation 2: Old mock array ['Optic','Gurm','Furion',...] must be removed"
        )
        # The old mock.forEach pattern must be gone
        assert "mock.forEach" not in js, (
            "Violation 2: Old mock.forEach pattern must be replaced with API fetch"
        )

    def test_load_workstreams_uses_api_sources(self):
        """loadWorkstreams() must call api('/sources') not use a mock array."""
        js = _onboarding_js_text()
        assert "api('/sources')" in js, (
            "Violation 2: loadWorkstreams() must fetch from api('/sources'), not mock data"
        )

    def test_source_labels_come_from_api_response(self):
        """Source labels should use s.user_label or s.type from API response."""
        js = _onboarding_js_text()
        assert "user_label" in js, (
            "Source labels should use s.user_label from API response"
        )
        assert "s.type" in js, (
            "Source fallback should use s.type from API response"
        )

    def test_empty_sources_shows_honest_message(self):
        """When API returns no sources, show honest message, not fake data."""
        js = _onboarding_js_text()
        assert "No workstreams found" in js, (
            "Empty sources should show 'No workstreams found' message"
        )


# ---------------------------------------------------------------------------
# VIOLATION 3: No Math.random() fake counts
# ---------------------------------------------------------------------------

class TestNoFakeRandomCounts:
    """Heresy 10 Violation 3: Math.random() fake counts must be removed."""

    def test_no_math_random_in_load_workstreams(self):
        """loadWorkstreams() must not use Math.random() to generate fake file counts."""
        js = _onboarding_js_text()
        assert "Math.random()" not in js, (
            "Violation 3: Math.random() fake file counts must be removed"
        )
        assert "Math.floor" not in js or "Math.floor(Math.random()" not in js, (
            "Violation 3: Math.floor(Math.random()*...) fake counts must be removed"
        )

    def test_file_counts_show_em_dash(self):
        """File counts in the source cards should show '—' (honest), not random numbers."""
        js = _onboarding_js_text()
        # The const count = '—' should be present
        assert "count='—'" in js or '"count":"—"' in js, (
            "Violation 3: Source file counts should show '—', not random numbers"
        )

    def test_no_dynamic_mock_file_count_generation(self):
        """No code should generate file counts like ~1234 files."""
        js = _onboarding_js_text()
        assert "~" not in js, (
            "Violation 3: No tilde-prefixed fake counts like '~1234 files'"
        )


# ---------------------------------------------------------------------------
# VIOLATION 4: Lens default must be 0 not 9
# ---------------------------------------------------------------------------

class TestHonestLensDefault:
    """Heresy 10 Violation 4: '||9' lens default must be '||0'."""

    def test_lens_default_is_zero(self):
        """The lens count fallback must be 0, not 9."""
        js = _onboarding_js_text()
        assert "lenses.length||0" in js, (
            "Violation 4: Lens count default must be '||0', not '||9'"
        )
        assert "lenses.length||9" not in js, (
            "Violation 4: Old '||9' lens default must be removed"
        )

    def test_lenses_count_in_check_model(self):
        """checkModel() health response should default lenses to 0."""
        js = _onboarding_js_text()
        assert "lenses: ${d.lenses||0}" in js, (
            "checkModel() should default lenses to 0, not 9"
        )

    def test_stat_lens_renders_with_zero_default(self):
        """renderAuditReady() should default lenses to 0, not 9."""
        js = _onboarding_js_text()
        # Check the renderAuditReady function
        assert "'stat_lens'" in js
        lens_line = None
        for line in js.split("\n"):
            if "stat_lens" in line and "textContent" in line:
                lens_line = line
                break
        if lens_line:
            assert "||0" in lens_line or 'lenses.length||0' in js, (
                f"stat_lens default should be 0, found: {lens_line.strip()}"
            )


# ---------------------------------------------------------------------------
# VIOLATION 5: No localhost:3003 hardcode
# ---------------------------------------------------------------------------

class TestNoLocalhostHardcode:
    """Heresy 10 Violation 5: localhost:3003 hardcode must use api('/health')."""

    def test_check_model_uses_api_proxy(self):
        """checkModel() must use api('/health'), not fetch('http://localhost:3003/...')."""
        js = _onboarding_js_text()
        assert "api('/health')" in js, (
            "Violation 5: checkModel() must use api('/health') proxy, not localhost:3003"
        )
        # The old hardcoded fetch URL should be gone
        assert "fetch('http://localhost:3003/api/v1/health')" not in js, (
            "Violation 5: Old hardcoded fetch to localhost:3003/api/v1/health must be removed"
        )

    def test_no_localhost_hardcode_anywhere(self):
        """No URL should point to a hardcoded localhost:3003 beyond the API constant and docs link."""
        html = _onboarding_html_path().read_text()
        # API constant (line 68) and docs navigation link are the only allowed localhost:3003 refs
        localhost_count = html.count("http://localhost:3003")
        assert localhost_count <= 2, (
            f"Violation 5: Expected at most 2 localhost:3003 references (API constant + docs link), "
            f"found {localhost_count}"
        )

    def test_api_constant_still_present(self):
        """The API constant at top should still exist for api() helper."""
        html = _onboarding_html_path().read_text()
        assert "const API='http://localhost:3003/api/v1'" in html or \
               'const API="http://localhost:3003/api/v1"' in html, (
            "The API constant should still be defined for the api() helper function"
        )


# ---------------------------------------------------------------------------
# HONESTY — Additional cross-checks
# ---------------------------------------------------------------------------

class TestHonestSelectAll:
    """selectAllWS() must read real names from the DOM, not a hardcoded array."""

    def test_select_all_uses_dom_not_hardcoded_array(self):
        """The new selectAllWS() reads .card-title textContent, not a hardcoded list."""
        js = _onboarding_js_text()
        assert "querySelector('.card-title')" in js or \
               "querySelectorAll('#ws_list .card')" in js, (
            "selectAllWS() must read names from the DOM, not a hardcoded array"
        )
        # The old hardcoded array should be gone from selectAllWS
        # It used to be: ['Optic','Gurm',...]
        old_pattern = "['Optic','Gurm','Furion'"
        assert old_pattern not in js, (
            "selectAllWS() must not contain the old hardcoded mock source array"
        )

    def test_deselect_all_exists(self):
        """deselectAllWS should exist (it was always OK but verify)."""
        js = _onboarding_js_text()
        assert "deselectAllWS" in js, "deselectAllWS must exist"


class TestNoFakeDataRemnants:
    """Comprehensive check for any remaining fake/mock patterns."""

    def test_no_fabricated_numbers(self):
        """No made-up statistic numbers should appear."""
        html = _onboarding_html_path().read_text()
        # These patterns were in the old fake data
        fake_patterns = [
            r"30\+",          # fake workstream count
            r"115,000\+",     # fake file count
            r"Math\.random",  # fake count generation
            r"\|\|9",         # fake lens default (not the API version check)
        ]
        for pattern in fake_patterns:
            matches = re.findall(pattern, html)
            if pattern == r"\|\|9":
                # The pattern `||9` might match `||9000` — be precise
                matches = [m for m in matches if m == "||9"]
            assert len(matches) == 0, (
                f"Fake data remnant found: '{pattern}' appears in onboarding.html. "
                f"All onboarding data must come from the API."
            )

    def test_onboarding_is_self_contained_html(self):
        """Sanity: onboarding.html should be a valid HTML file."""
        html = _onboarding_html_path().read_text()
        assert html.startswith("<!DOCTYPE html>") or html.startswith("<!doctype html>"), \
               "onboarding.html should start with DOCTYPE"
        assert "</html>" in html, "onboarding.html should close with </html>"
