# Changelog

Notable feature-level changes to Hascone.

## 1.1.1 - Toggle switches

- Checkbox settings now use teal toggle switches, including Scouter weights, item enhancement modes, Star Force options, and buffs.
- Switches retain keyboard operation, saved states, and disabled states, with visible focus indicators and support for reduced motion and high-contrast display settings.
- Compact Scouter buff controls place switches below their icons.
- The expanded character roster collapses when clicking outside it.

## 1.1.0 - Background scanning and character navigation

- Character-info captures now process in the background alongside equipment captures, allowing users to continue scanning other characters. Scan indicators show elapsed time, queued reads, and failures; OCR times out instead of waiting indefinitely.
- Background results stay attached to their captured character, preserve subsequent manual edits, and stop dependent saves when character verification fails.
- A slim teal arrow at the middle of the left edge opens the character roster, with per-character processing indicators.
- Individual equipment scan buttons name the item slot. Upgrade recommendations include flame, star, and cube icons.
- Scouter snapshots support custom names beside their date and time.
- Summed flame stats and inferred tier breakdowns appear side by side, with a tier badge on each breakdown line. Ambiguous or unsupported breakdowns are identified explicitly.

## 0.5.4 - Navigation and overview

The pinned header spans the window above the content scrollbar. It stays expanded at the top, shrinks after scrolling, and expands on hover or keyboard navigation. Character selection remains in the compact bar. The Home indicator returns to the vertical character roster. Character selection sits beside Add character. Potentials and Star Force show compact ordered upgrade cards; expand a card for the target, probability and plan details. Equipment and Scouter retain their comparison lists.

Current Star Force costs estimate the least-meso route from 0 to scanned stars, including recovery and current event discounts but excluding replacement equipment. Fixed/special or unread items are explicitly unpriced. Each enhancement tab groups upgrade order, current costs, then the detailed Scouter FD comparison. Zoom shortcuts are shown in Settings and below the page.

## 0.5.2 - Scouter potential weights

Potentials now has a per-character Use Scouter weights toggle. Saved percentage-stat efficiencies determine individual stat and All Stat equivalents, and ATT/MATT percentage efficiency divided by boss damage efficiency determines the boss-to-attack ratio. Displayed potentials, individual expected costs and aggregate costs use the same snapshot. Manual global/class weights remain available when switched off. The panel shows the calculation date; missing or invalid calculations fall back to manual weights. Crit Damage and cooldown retain their existing separate cost requirements.

## 0.5.0 - Roster and progression planning

The fixed header keeps character selection and navigation visible. Click Hascone to
open the roster overview; selecting a card opens that character's Equipment page.
Equipment, Flames, Potentials and Star Force show upgrade recommendations, refreshed
in the background when a current Scouter calculation and scanned equipment exist.
Failed comparisons require an explicit retry instead of repeatedly calling the API.

Comparison filters distinguish one best recommendation per slot from every modeled
target. All targets - meso optimized retains every cube/flame target and the
least-meso Star Force strategy. All options also includes the low-boom strategy.

Potential equivalent totals use configurable global weights with class overrides,
not Scouter efficiencies. Scouter comparisons use returned marginal efficiencies;
flame score rankings use the flame weight setting. Different qualifying gains can
therefore produce different costs and rankings.

Scouter includes a prominent guided scan, links to incomplete fields, contextual
error recovery and an Efficiencies page. The latter shows the saved API response.
