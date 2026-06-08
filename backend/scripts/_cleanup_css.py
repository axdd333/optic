#!/usr/bin/env python3
"""CSS cleanup script for app.css — merges Brand Pass, removes duplicates, consolidates classes."""

import re, os

CSS_PATH = os.path.join(os.path.dirname(__file__), "..", "src", "ctxorg", "static", "app.css")

with open(CSS_PATH, "r") as f:
    content = f.read()

orig_lines = content.count("\n") + 1
print(f"BEFORE: {orig_lines} lines, {len(content)} chars")

# ─── EDIT 1: Remove duplicate .home-sort-wrap, .home-sort (lines 1667-1701) ───
# JS uses .ws-sort-wrap and .ws-sort exclusively
content = re.sub(
    r'/\*.*?\*/\s*\n\s*\.home-sort-wrap\s*\{[^}]*\}\s*\n',
    '',
    content,
    count=1
)
content = re.sub(
    r'\.home-sort\s*\{[^}]*\}\s*\n',
    '',
    content,
    count=1
)

# ─── EDIT 2: Remove duplicate .home-view-toggle, .home-view-btn (lines 1703-1755) ───
# JS uses .ws-view and .ws-view-btn exclusively
content = re.sub(
    r'\.home-view-toggle\s*\{[^}]*\}\s*\n',
    '',
    content
)
# Remove .home-view-btn block (rules + hover + active)
content = re.sub(
    r'\.home-view-btn\s*\{[^}]*\}\s*\n',
    '',
    content
)
content = re.sub(
    r'\.home-view-btn:hover\s*\{[^}]*\}\s*\n',
    '',
    content
)
content = re.sub(
    r'\.home-view-btn\.active\s*\{[^}]*\}\s*\n',
    '',
    content
)

# ─── EDIT 3: Consolidate .view-list/.is-list/.list — keep only .view-list ───
# JS only uses cards-grid + view-list
content = content.replace(
    ".cards-grid.view-list,\n.cards-grid.is-list,\n.cards-grid.list,\n#workspace-cards[data-view=\"list\"] .cards-grid",
    ".cards-grid.view-list"
)

# ─── EDIT 4: Remove old .ws-card styles (lines ~1854-2016) but strip down ───
# JS uses BOTH ws-card AND ws-card2 on elements, so we need ws-card for 
# shared properties. Remove the visual overrides that ws-card2 provides.
# Keep only: display flex, flex-direction column, and animation.
old_ws_card_start = """.ws-card {
  background: rgba(255,255,255,0.85);
  border: 1px solid rgba(0,0,0,0.06);
  border-radius: 16px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  box-shadow: 0 1px 4px rgba(0,0,0,.05);
  transition: box-shadow .18s var(--ease), transform .18s var(--ease), border-color .15s;
  cursor: default;
  animation: cardIn .28s var(--ease) both;
}"""

new_ws_card = """.ws-card {
  display: flex;
  flex-direction: column;
  animation: cardIn .28s var(--ease) both;
}"""

content = content.replace(old_ws_card_start, new_ws_card)

# Remove ws-card hover, active (ws-card2 handles these)
content = re.sub(
    r'\.ws-card:hover\s*\{[^}]*\}\s*\n',
    '',
    content
)
content = re.sub(
    r'\.ws-card:active\s*\{[^}]*\}\s*\n',
    '',
    content
)

# Remove old ws-card sub-styles that are now handled by ws-card2:
# .ws-card-header, .ws-icon, .ws-card-body, .ws-name, .ws-desc
# .ws-badge, .ws-evidence, .ws-ev-label, .ws-ev-row, .ws-ev-ico
# .ws-ev-name, .ws-ev-loc, .ws-footer, .ws-act-link, .ws-act-btn
# and the stagger delays
old_subs = r"""\/\* Card header row: icon \+ body \+ badge \*\/.*?\.ws-card-header\s*\{[^}]*\}\s*\n""";
content = re.sub(old_subs, '', content, flags=re.DOTALL)

content = re.sub(r'\.ws-icon\s*\{[^}]*\}\s*\n', '', content)
content = re.sub(r'\.ws-card-body\s*\{[^}]*\}\s*\n', '', content)
content = re.sub(r'\.ws-name\s*\{[^}]*\}\s*\n', '', content)
content = re.sub(r'\.ws-desc\s*\{[^}]*\}\s*\n', '', content)
content = re.sub(r'\.ws-badge\s*\{[^}]*\}\s*\n', '', content)
content = re.sub(r'\.ws-badge--high\s*\{[^}]*\}\s*\n', '', content)
content = re.sub(r'\.ws-badge--medium\s*\{[^}]*\}\s*\n', '', content)
content = re.sub(r'\.ws-badge--low\s*\{[^}]*\}\s*\n', '', content)

# Evidence section
content = re.sub(r'\.ws-evidence\s*\{[^}]*\}\s*\n', '', content)
content = re.sub(r'\.ws-ev-label\s*\{[^}]*\}\s*\n', '', content)
content = re.sub(r'\.ws-ev-row\s*\{[^}]*\}\s*\n', '', content)
content = re.sub(r'\.ws-ev-ico\s*\{[^}]*\}\s*\n', '', content)
content = re.sub(r'\.ws-ev-name\s*\{[^}]*\}\s*\n', '', content)
content = re.sub(r'\.ws-ev-loc\s*\{[^}]*\}\s*\n', '', content)

# Card footer actions
content = re.sub(r'\.ws-footer\s*\{[^}]*\}\s*\n', '', content)
content = re.sub(r'\.ws-act-link\s*\{[^}]*\}\s*\n', '', content)
content = re.sub(r'\.ws-act-link:hover\s*\{[^}]*\}\s*\n', '', content)
content = re.sub(r'\.ws-act-btn\s*\{[^}]*\}\s*\n', '', content)
content = re.sub(r'\.ws-act-btn:hover\s*\{[^}]*\}\s*\n', '', content)

# Remove stagger animation delays (now on ws-card2 instead)
content = re.sub(
    r'/\* Stagger card entrance \*/\s*\n\s*\.ws-card:nth-child.*?(?=\n/\*)',
    '',
    content,
    flags=re.DOTALL
)

# ─── EDIT 5: Fix #run { display:none } conflict ───
# Remove the Brand Pass line that hides #run (line 4602-4605)
content = re.sub(
    r'\.topbar-run,\s*\n#run\s*\{\s*\n\s*display:\s*none;\s*\n\s*\}\s*\n',
    '',
    content
)

# ─── EDIT 6: Merge Brand Pass — move valuable additions into original declarations ───
# Strategy: For each Brand Pass rule, integrate into the original declaration

# 6a: Add font-display to home-title, panel-title, rail-head, settings-title
# Find .home-title and add font-family
content = content.replace(
    ".home-title {\n  font-size: 26px;\n  font-weight: 700;\n  letter-spacing: -.7px;\n  color: var(--text);\n  margin-bottom: 6px;\n  line-height: 1.1;\n}",
    ".home-title {\n  font-family: var(--font-display);\n  font-size: 26px;\n  font-weight: 700;\n  letter-spacing: -.7px;\n  color: var(--text);\n  margin-bottom: 6px;\n  line-height: 1.1;\n}"
)

# Add font-display to .panel-title
content = content.replace(
    ".panel-title {\n  font-size: 15.5px;\n  font-weight: 680;\n  letter-spacing: -.3px;\n  color: var(--text);\n  padding: 22px 20px 6px;\n  line-height: 1.3;\n}",
    ".panel-title {\n  font-family: var(--font-display);\n  font-size: 15.5px;\n  font-weight: 680;\n  letter-spacing: -.3px;\n  color: var(--text);\n  padding: 22px 20px 6px;\n  line-height: 1.3;\n}"
)

# Add font-display to .rail-head
content = content.replace(
    ".rail-head {\n  font-size: 33px;\n  letter-spacing: -.35px;\n}",
    ".rail-head {\n  font-family: var(--font-display);\n  font-size: 33px;\n  letter-spacing: -.35px;\n}"
)

# Add font-display to .settings-title
content = content.replace(
    ".settings-title {\n  font-size: 14px;\n  font-weight: 660;\n  letter-spacing: -.3px;\n  color: var(--text);\n}",
    ".settings-title {\n  font-family: var(--font-display);\n  font-size: 14px;\n  font-weight: 660;\n  letter-spacing: -.3px;\n  color: var(--text);\n}"
)

# 6b: Update .topbar with enhanced border-bottom and box-shadow
content = content.replace(
    ".topbar {\n  grid-column: 1 / 4;\n  grid-row: 1;\n  display: flex;\n  align-items: center;\n  height: 64px;\n  padding: 0 16px 0 0;\n  background: #fff;\n  backdrop-filter: none;\n  -webkit-backdrop-filter: none;\n  border-bottom: 1px solid var(--line);\n  z-index: 20;\n}",
    ".topbar {\n  grid-column: 1 / 4;\n  grid-row: 1;\n  display: flex;\n  align-items: center;\n  height: 64px;\n  padding: 0 12px 0 0;\n  gap: 8px;\n  background: #fff;\n  backdrop-filter: none;\n  -webkit-backdrop-filter: none;\n  border-bottom: 1px solid rgba(15,30,66,.14);\n  box-shadow: 0 12px 24px rgba(18,30,55,.05);\n  z-index: 20;\n}"
)

# 6c: Update .leftnav with enhanced styling
content = content.replace(
    ".leftnav {\n  grid-column: 1;\n  grid-row: 2;\n  display: flex;\n  flex-direction: column;\n  padding: 8px 0 12px;\n  background: rgba(248,248,252,0.88);\n  backdrop-filter: blur(16px) saturate(140%);\n  -webkit-backdrop-filter: blur(16px) saturate(140%);\n  border-right: 1px solid var(--line);\n  overflow: hidden;\n}",
    ".leftnav {\n  grid-column: 1;\n  grid-row: 2;\n  display: flex;\n  flex-direction: column;\n  padding: 8px 0 12px;\n  background: rgba(246,250,255,0.86);\n  backdrop-filter: blur(16px) saturate(140%);\n  -webkit-backdrop-filter: blur(16px) saturate(140%);\n  border-right: 1px solid rgba(16,31,71,.13);\n  box-shadow: 8px 0 22px rgba(12,26,58,.06);\n  overflow: hidden;\n}"
)

# 6d: Update .leftnav-item — add border-radius and enhanced transition
content = content.replace(
    ".leftnav-item {\n  display: flex;\n  align-items: center;\n  gap: 9px;\n  height: 34px;\n  padding: 0 10px;\n  border: 0;\n  background: transparent;\n  border-radius: var(--r-sm);\n  color: var(--muted);\n  font-size: 12.5px;\n  font-weight: 500;\n  transition: background 0.1s, color 0.1s;\n  text-align: left;\n  cursor: pointer;\n  white-space: nowrap;\n  position: relative;\n}",
    ".leftnav-item {\n  display: flex;\n  align-items: center;\n  gap: 9px;\n  height: 34px;\n  padding: 0 10px;\n  border: 0;\n  background: transparent;\n  border-radius: 10px;\n  color: var(--muted);\n  font-size: 12.5px;\n  font-weight: 500;\n  transition: background .16s, color .16s, transform .16s;\n  text-align: left;\n  cursor: pointer;\n  white-space: nowrap;\n  position: relative;\n}"
)

# 6e: Update .leftnav-item:hover
content = content.replace(
    ".leftnav-item:hover { background: rgba(0,0,0,0.04); color: var(--text); }",
    ".leftnav-item:hover {\n  background: rgba(10,42,112,.07);\n  color: var(--text);\n  transform: translateX(1px);\n}"
)

# 6f: Update .leftnav-item.active
content = content.replace(
    ".leftnav-item.active {\n  background: var(--accent-dim);\n  color: var(--accent);\n  font-weight: 600;\n}",
    ".leftnav-item.active {\n  background: linear-gradient(180deg,\n    rgba(var(--accent-rgb),.17), rgba(var(--accent-rgb),.11));\n  color: #0b4fbe;\n  font-weight: 600;\n  box-shadow: inset 0 1px 0 rgba(255,255,255,.76);\n}"
)

# 6g: Update .statusbar with enhanced styling
content = content.replace(
    ".statusbar {\n  grid-column: 1 / 4;\n  grid-row: 3;\n  display: grid;\n  grid-template-columns: minmax(0,1fr) auto auto;\n  gap: 12px;\n  align-items: center;\n  height: 22px;\n  padding: 0 14px;\n  background: rgba(248,248,252,0.90);\n  backdrop-filter: blur(10px);\n  border-top: 1px solid var(--line);\n  color: var(--subtle);\n  font-size: 10.5px;\n  letter-spacing: .1px;\n}",
    ".statusbar {\n  grid-column: 1 / 4;\n  grid-row: 3;\n  display: grid;\n  grid-template-columns: minmax(0,1fr) auto auto;\n  gap: 12px;\n  align-items: center;\n  height: 22px;\n  padding: 0 14px;\n  background: linear-gradient(180deg,\n    rgba(255,255,255,.82), rgba(248,252,255,.92));\n  backdrop-filter: blur(10px);\n  border-top: 1px solid rgba(15,30,70,.14);\n  color: var(--subtle);\n  font-size: 10.5px;\n  letter-spacing: .1px;\n}"
)

# 6h: Update .ws-card2 border-radius from 18px to 20px (from Brand Pass)
content = content.replace(
    ".ws-card2 {\n  background: #fff;\n  border: 1px solid rgba(0,0,0,0.07);\n  border-radius: 18px;",
    ".ws-card2 {\n  background: #fff;\n  border: 1px solid rgba(15,34,79,.14);\n  border-radius: 20px;"
)

# 6i: Update .ws-card2 hover
content = content.replace(
    ".ws-card2:hover {\n  box-shadow: 0 14px 32px rgba(15,33,76,0.12), 0 3px 11px rgba(0,0,0,0.06);\n  border-color: rgba(13,42,108,0.20);\n  transform: translateY(-2px);\n}",
    ".ws-card2:hover {\n  box-shadow: 0 16px 34px rgba(15,33,76,.12), 0 3px 11px rgba(0,0,0,.06);\n  border-color: rgba(13,42,108,.20);\n  transform: translateY(-2px);\n}"
)

# 6j: Add opticPulse keyframes (put after .topbar-presence-dot)
# Already at bottom — will be kept

# ─── EDIT 7: Remove the entire "Brand Pass" and "Ultra Route + Rail polish" sections ───
# Remove "Ultra Route + Rail polish" section (lines 3437 to ~3680)
# Remove explicit "Brand Pass" section (lines 4457 to ~4640)

# First remove the Rail polish section that overrides .app grid, .topbar, etc.
# This section contains overrides already merged above.
ultra_start = "/* ─── Ultra Route + Rail polish ─────────────────────────────────────────── */"
ultra_end = "/* ─── Card hover lift with shadow change"

# Find and remove the Ultra section
idx1 = content.find(ultra_start)
idx2 = content.find(ultra_end)
if idx1 >= 0 and idx2 > idx1:
    # Keep the comment before removal
    before = content[:idx1]
    after = content[idx2:]
    # Remove empty lines left behind
    before = before.rstrip() + "\n\n"
    content = before + after

# Remove "Native Proprietary Brand Pass" section
brand_start = "/* ─── Native Proprietary Brand Pass ─────────────────────────────────────── */"
# Find the end — it's before the onboarding step transitions comment
brand_end_marker = "/* ─── Onboarding step transitions"
idx3 = content.find(brand_start)
idx4 = content.find(brand_end_marker)
if idx3 >= 0 and idx4 > idx3:
    before = content[:idx3]
    after = content[idx4:]
    before = before.rstrip() + "\n\n"
    content = before + after

# Also remove Shell polish hardening comment + rules that remain between 
# Brand Pass end and Onboarding transitions
content = re.sub(
    r'/\* Shell polish hardening \*/\s*\n[^/]*?(?=/\* ─── Onboarding)',
    '',
    content,
    flags=re.DOTALL
)
# And remove the responsive media overrides leftover from Brand Pass
content = re.sub(
    r'@media \(max-width: 900px\) \{\s*\n\s*\.topbar-avatar.*?\}\s*\n\s*\.logo-lockup.*?\}\s*\n\s*\.home-title.*?\}\s*\n\s*\.rail-head.*?\}\s*\n\}\s*\n',
    '',
    content
)
content = re.sub(
    r'@media \(max-width: 680px\) \{\s*\n\s*\.topbar-actions \{\s*\n\s*grid-template-columns.*?\}\s*\n\s*\.topbar-presence.*?\}\s*\n\s*\.topbar-avatar.*?\}\s*\n\}\s*\n',
    '',
    content
)

# Also remove the redundant .topbar overrides from the Brand Pass area
# that hadn't been caught yet: .topbar { gap, padding }, .topbar-logo overrides
content = re.sub(
    r'/\* ─── Card hover lift.*?\*/\s*\n/\* Cards that benefit.*?\*/\s*\n\.route-card,\s*\n\.rail-card,\s*\n\.settings-panel,\s*\n\.audience-modal \{\s*\n\s*transition:.*?\}\s*\n\s*\n\.route-card:hover,\s*\n\.rail-card:hover \{\s*\n\s*transform:.*?\}\s*\n\s*\n\.route-card:active,\s*\n\.rail-card:active \{\s*\n\s*transform:.*?\}\s*\n',
    '',
    content,
    flags=re.DOTALL
)

# Also fix .topbar-actions gap (was overridden to 9px, 7px in multiple places — keep 8px)
content = re.sub(
    r'\.topbar-actions \{\s*\n\s*margin-left: auto;\s*\n\s*min-width: 0;\s*\n\s*flex: 1 1 auto;\s*\n\s*justify-content: flex-end;\s*\n\s*gap: 8px;\s*\n\s*\}',
    '',
    content
)

# Remove leftover .ws-card2 from Brand Pass that overrides border-radius/box-shadow
# (we already merged the values into the main .ws-card2 rule above)
content = re.sub(
    r'\.ws-card2 \{\s*\n\s*border-radius: 20px;\s*\n\s*box-shadow:.*?\}\s*\n',
    '',
    content
)
content = re.sub(
    r'\.ws-card2:hover \{\s*\n\s*box-shadow:.*?\}\s*\n',
    '',
    content
)

# Remove leftover shared card overrides
content = re.sub(
    r'\.ws-card2,\s*\n\.route-card,\s*\n\.rail-card,\s*\n\.settings-panel,\s*\n\.audience-modal \{\s*\n\s*border-radius: 16px;\s*\n\s*border-color:.*?\}\s*\n',
    '',
    content
)

# Remove leftover .messages, .chatbox from Brand Pass
content = re.sub(
    r'\.messages \{\s*\n\s*background: linear-gradient\(180deg,\s*\n\s*rgba\(255,255,255,\.64\), rgba\(251,253,255,\.88\)\);\s*\n\}\s*\n',
    '',
    content
)
content = re.sub(
    r'\.chatbox \{\s*\n\s*border-top:.*?\}\s*\n',
    '',
    content
)

# Remove .topbar-presence-dot from Brand Pass (keep the opticPulse keyframes)
content = re.sub(
    r'\.topbar-presence-dot \{\s*\n\s*box-shadow:.*?\}\s*\n',
    '',
    content
)

# Also remove #search, .topbar-btn overrides from Brand Pass
content = re.sub(
    r'#search,\s*\n\.topbar-btn,\s*\n\.scan-folders-btn,\s*\n\.topbar-run,\s*\n#run \{\s*\n\s*border-radius: 11px;\s*\n\}\s*\n',
    '',
    content
)
content = re.sub(
    r'#search \{\s*\n\s*background:.*?\}\s*\n',
    '',
    content
)
content = re.sub(
    r'#search:focus \{\s*\n\s*border-color:.*?\}\s*\n',
    '',
    content
)
content = re.sub(
    r'\.topbar-btn,\s*\n\.scan-folders-btn,\s*\n\.topbar-run,\s*\n#run \{\s*\n\s*background:.*?\}\s*\n',
    '',
    content
)

# Remove leftover .topbar height overrides
content = re.sub(
    r'#search,\s*\n\.topbar-btn,\s*\n\.scan-folders-btn,\s*\n\.topbar-run,\s*\n#run \{\s*\n\s*height: 35px;\s*\n\}\s*\n',
    '',
    content
)

# Remove .topbar-avatar, .topbar-presence height overrides from Brand Pass
content = re.sub(
    r'\.topbar-avatar \{\s*\n\s*height: 35px;\s*\n\s*min-width: 35px;\s*\n\s*padding:.*?\}\s*\n',
    '',
    content
)
content = re.sub(
    r'\.topbar-presence \{\s*\n\s*width: 35px;\s*\n\s*height: 35px;\s*\n\}\s*\n',
    '',
    content
)

# Remove leftover .app grid override
content = re.sub(
    r'\.app \{\s*\n\s*grid-template-columns: 184px minmax\(0,1fr\) clamp\(360px,31vw,460px\);\s*\n\}\s*\n',
    '',
    content
)

# Remove .topbar padding override
content = re.sub(
    r'\.topbar \{\s*\n\s*padding-right: 14px;\s*\n\s*gap: 10px;\s*\n\}\s*\n',
    '',
    content
)

# Remove .topbar-logo overrides
content = re.sub(
    r'\.topbar-logo \{\s*\n\s*flex: 0 0 auto;\s*\n\}\s*\n',
    '',
    content
)

# Remove .topbar-actions override
content = re.sub(
    r'\.topbar-actions \{\s*\n\s*margin-left: auto;\s*\n\s*min-width: 0;\s*\n\s*flex: 1 1 auto;\s*\n\s*justify-content: flex-end;\s*\n\s*gap: 8px;\s*\n\}\s*\n',
    '',
    content
)

# Remove #search override
content = re.sub(
    r'#search \{\s*\n\s*min-width: 0;\s*\n\s*flex: 1 1 280px;\s*\n\s*width: clamp\(210px, 22vw, 320px\);\s*\n\}\s*\n',
    '',
    content
)

# Remove .topbar-run, #run flex override
content = re.sub(
    r'\.topbar-run, #run \{\s*\n\s*flex: 0 0 clamp\(132px, 15vw, 190px\);\s*\n\s*width: clamp\(132px, 15vw, 190px\);\s*\n\s*min-width: 132px;\s*\n\s*max-width: 190px;\s*\n\}\s*\n',
    '',
    content
)

# Remove .side grid-template-rows override
content = re.sub(
    r'\.side \{\s*\n\s*grid-template-rows: minmax\(0,1fr\);\s*\n\}\s*\n',
    '',
    content
)

# Remove .side-chat override
content = re.sub(
    r'\.side\.side-chat \{\s*\n\s*grid-template-rows: minmax\(340px,58%\) minmax\(260px,42%\);\s*\n\}\s*\n',
    '',
    content
)

# Remove .iris-console[hidden] override
content = re.sub(
    r'\.iris-console\[hidden\] \{\s*\n\s*display: none !important;\s*\n\}\s*\n',
    '',
    content
)

# Remove .statusbar override
content = re.sub(
    r'\.statusbar \{\s*\n\s*grid-template-columns: minmax\(170px,1\.2fr\) repeat\(3, minmax\(0,1fr\)\) auto;\s*\n\s*height: 54px;\s*\n\s*padding: 0 14px;\s*\n\s*gap: 10px;\s*\n\}\s*\n',
    '',
    content
)

# Remove the .topbar [data-mode] hide rules
content = re.sub(
    r'/\* Shell polish hardening \*/\s*\n\s*\.topbar \[data-mode\],\s*\n.*?(?=@keyframes)',
    '',
    content,
    flags=re.DOTALL
)

# ─── EDIT 8: Apply white frost-glass backdrop-filter on glass elements ───
# Set --glass-blur to actually blur (was blur(0px))
content = content.replace(
    '--glass-blur:   blur(0px) saturate(100%) contrast(100%);',
    '--glass-blur:   blur(12px) saturate(140%);'
)

# Add CLAUDE.md CSS variables: --color-cream, --color-ink, --color-muted, --color-border
# Find the :root block and add them after the existing variables
cream_vars = """\n  /* Optic brand tokens (from CLAUDE.md) */
  --color-cream:  #faf8f5;
  --color-ink:    #111118;
  --color-border: rgba(0,0,0,0.07);"""

content = content.replace(
    '  color-scheme: light;',
    '  color-scheme: light;' + cream_vars
)

# ─── Clean up: collapse multiple blank lines ───
import re as re_mod
content = re_mod.sub(r'\n\n\n+', '\n\n', content)

# ─── Write back ───
with open(CSS_PATH, "w") as f:
    f.write(content)

new_lines = content.count("\n") + 1
print(f"AFTER:  {new_lines} lines, {len(content)} chars")
print(f"Removed {orig_lines - new_lines} lines ({((orig_lines-new_lines)/orig_lines*100):.0f}%)")

# Verify key changes
checks = [
    ("home-sort-wrap", "home-sort-wrap should be removed"),
    ("home-sort {", "home-sort should be removed"),
    ("home-view-btn", "home-view-btn should be removed"),
    (".cards-grid.is-list", "is-list should be removed"),
    (".cards-grid.list", ".list should be removed (except view-list)"),
    ("#run {\n  display: none", "#run display:none should be removed"),
]
print("\n--- Verification ---")
for pattern, desc in checks:
    if pattern in content:
        print(f"  FAIL: {desc}")
    else:
        print(f"  OK: {desc}")

# Verify key keeps
keep_checks = [
    (".ws-sort-wrap", "ws-sort-wrap should be kept"),
    (".ws-sort", "ws-sort should be kept"),
    (".ws-view-btn", "ws-view-btn should be kept"),
    ("ws-card2", "ws-card2 should be kept"),
    (".ws-card {", "ws-card should be kept (stripped)"),
    ("font-family: var(--font-display)", "font-display should be merged"),
    ("--color-cream", "color-cream var should exist"),
    ("opticPulse", "opticPulse keyframes should be kept"),
    ("backdrop-filter: blur(12px) saturate(140%)", "glass-blur should be active"),
]
print("\n--- Keep Verification ---")
for pattern, desc in keep_checks:
    if pattern in content:
        print(f"  OK: {desc}")
    else:
        print(f"  FAIL: {desc}")

print("\nDone.")
/bin/bash: line 4: /var/folders/tv/lg7jqd1d73z30x9slxb_7_140000gn/T/hermes-snap-a86862506dbb.sh: No space left on device
/bin/bash: line 5: /var/folders/tv/lg7jqd1d73z30x9slxb_7_140000gn/T/hermes-cwd-a86862506dbb.txt: No space left on device
