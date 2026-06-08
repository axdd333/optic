#!/usr/bin/env python3
"""Restore Ultra Route section + opticPulse from backup."""
import re, os

APP_CSS = os.path.join(os.path.dirname(__file__), "..", "src", "ctxorg", "static", "app.css")
APP_CSS_BAK = APP_CSS + ".bak"

with open(APP_CSS_BAK) as f:
    backup = f.read()

# Extract Ultra Route + Rail polish section (3437 to Scrollbars)
ultra_start = backup.find('/* ─── Ultra Route + Rail polish ─────────────────────────────────────────── */')
media_start = backup.find('/* ─── Scrollbars ─────────────────────────────────────────────────────────── */')
ultra_section = backup[ultra_start:media_start].strip()

# Extract opticPulse from Brand Pass
brand_start = backup.find('/* ─── Native Proprietary Brand Pass ─────────────────────────────────────── */')
brand_end = backup.find('/* ─── Onboarding step transitions')
brand_section = backup[brand_start:brand_end]

m = re.search(r'(\.topbar-presence-dot\s*\{[^}]+\})', brand_section, re.DOTALL)
presence_dot = m.group(1) if m else ''

m = re.search(r'(@keyframes opticPulse\s*\{[^}]+\})', brand_section, re.DOTALL)
optic_pulse = m.group(1) if m else ''

print(f"Ultra section: {len(ultra_section)} chars")
print(f"presence dot found: {bool(presence_dot)}")
print(f"opticPulse found: {bool(optic_pulse)}")

# Read current
with open(APP_CSS) as f:
    current = f.read()

# Find insertion point - before Scrollbars
idx = current.find('/* ─── Scrollbars ─────────────────────────────────────────────────────────── */')
if idx < 0:
    idx = current.find('/* ─── Card hover lift')

before = current[:idx].rstrip()
after = current[idx:]

# Build insert block
insert = '\n\n' + ultra_section + '\n\n'
if presence_dot:
    insert += presence_dot + '\n\n'
if optic_pulse:
    insert += optic_pulse + '\n\n'

new_content = before + insert + after

with open(APP_CSS, "w") as f:
    f.write(new_content)

lines = new_content.count('\n') + 1
print(f"AFTER: {lines} lines, {len(new_content)} chars")
