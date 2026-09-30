# Data sources

Hascone combines screenshot readers, equipment catalogs, probability tables and MapleScouter calculation/display modules.

Data sources retained in the individual catalog files:

- MapleScouter: https://maplescouter.com/en/input
- Flame tables: https://www.whackybeanz.com/calc/equips/flames
- Potential probabilities: https://brendonmay.github.io/cubingCalculator/
- Star Force reference: https://brendonmay.github.io/starforceCalculator/
- Equipment metadata/art: https://maplestorywiki.net/
- Character class/portrait: public Nexon GMS rankings and avatar CDN
- Boss crystal values (GMS v270, `src/bossing/data/bosses.json`): https://maplestorywiki.net/w/Intense_Power_Crystal (reviewed 2026-09-30)
- Boss categories, party limits and notable drop list (`src/bossing/data/`): MapleHub's boss tracker and diary, https://maplehub.app/ (reviewed 2026-09-30)
- Meso and Sol Erda Fragment icons (`web/meso.png`, `web/sol-erda-fragment.png`): MapleStory Wiki and maplestory.io item 4009547
- Boss portraits (`web/bosses/`): in-game Maple Guide art from https://maplestorywiki.net/w/Bosses (reviewed 2026-09-30)
- Boss drop item icons (`web/items/`): https://maplestory.io item icons, GMS v270
- OCR model: PaddleOCR PP-OCRv6 medium recognition (model README in `models/`)


Equipment reader templates were captured from GMS. Per-character flame weights can use MapleScouter stat efficiencies.

HEXA Stat I, II, and III icons (`src/scouter/data/icons/hexa-stat-*.png`) were cropped from the user's GMS HEXA Matrix window on 2026-09-28. MapleStory game artwork belongs to Nexon.

The Demon Slayer HEXA regression image (`tests/fixtures/demon_slayer_hexa.png`) is a cropped user-provided game window. Level 4 and 6 badge glyphs were extracted from the existing GMS 1366x768 HEXA fixture.

MapleScouter manual preset v1 interoperability: https://maplescouter.com/en/input (public preset importer and template reviewed 2026-09-27). tests/fixtures/scouter_preset_template.json is its public template, retained only for schema compatibility tests.
