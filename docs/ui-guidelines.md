# CodeVanguard UI & Design Guidelines

This document defines the canonical visual design system and component rules for CodeVanguard, derived from the design artboards in `docs/design/` (`Dashboard.dc.html`, `Main.dc.html`, and `Logo.dc.html`).

---

## 1. Core Visual Principles: Neo-Brutalist Minimalism

- **Strict Canvas Background**: `#F5F4EE`
- **Primary Ink / Contrast**: `#14141A`
- **Card Surfaces**: Pure white `#FFFFFF` with `border: 2px solid #14141A`, `border-radius: 18px`, and hard offset shadow `box-shadow: 5px 5px 0 #14141A`.
- **Button Surfaces**: Pill shapes (`border-radius: 999px`) with `border: 2px solid #14141A` and hard offset shadow `box-shadow: 3px 3px 0 #14141A`. Hover states translate down-right (`translate(2px, 2px)`) with shadow reduced to `1px 1px 0`.
- **Typography**:
  - Headings, navigation, action labels: `'Space Grotesk', system-ui, sans-serif`
  - Chips, commit SHAs, file paths, numbers, metadata: `'Space Mono', ui-monospace, monospace`
- **Color Palette**:
  - Lime Accent: `#D6F25B` (Brand accent, Safe, Low severity)
  - Purple Accent: `#B8A2FF` (Brand secondary, Medium severity)
  - Ink Black: `#14141A` (Primary borders, dark buttons, text)
  - Critical: `#FF6B3D` (Critical findings, block verdict, errors)
  - High / Warning: `#FFC93C` (High findings, attention status, review verdict)
  - Border Subdued / Divider: `#E2E0D6`
  - Subdued Text: `#55555F`

---

## 2. Reusable Component Primitives (`components/ui`)

All screens must reuse the standard primitives from `components/ui`:
- `Logo`: Standard CodeVanguard SVG mark with the lime V and orange dot.
- `Button`: Standard pill button (`variant: 'primary' | 'action' | 'secondary' | 'danger'`, `size: 'sm' | 'md'`).
- `Chip`: Monospace badge (`variant: 'critical' | 'high' | 'medium' | 'low' | 'attention' | 'safe' | 'block' | 'neutral'`). Every chip **must** have a clear text label.
- `StatusCard`: Summary card showing total issues to fix, status chip, scan age, severity split bar, and count breakdown.
- `SeverityBar`: 20px rounded pill showing proportional severity split.
- `RepoSwitcher`: Searchable repository picker dropdown for the signed-in header.
- `Tabs`: Segmented pill tab bar (`Overview`, `Settings`, etc.).
- `EmptyState`: Centered card with icon, clear title, concise description, and single call-to-action button.
- `Skeleton`: Monospace animated placeholder boxes matching the card layouts during loading.
- `ErrorState`: Alert card displaying error message and retry button.

---

## 3. Strict Screen Content Rules

1. **No duplicate facts**: Do not show the same metric or commit or count twice on any screen. For instance, the scan history list shows branch, commit SHA, timestamp, and status chip, and does **not** repeat the severity breakdown already shown in the `StatusCard`.
2. **Every chip has text**: Do not use naked color dots or icons without explicit text labels (e.g. `CRITICAL`, `HIGH`, `COMPLETED`, `QUEUED`, `BLOCK`).
3. **Responsive Width**: No horizontal page scrolling at phone width (`360px` - `414px`). All rows, toolbars, and split bars must wrap cleanly with `flex-wrap: wrap` and `max-width: 100%`.
4. **Clean Loading & Empty States**: Every screen must have dedicated Skeleton, Empty, and Error states.
