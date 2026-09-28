# Data sources

Hascone combines screenshot readers, equipment catalogs, probability tables and MapleScouter calculation/display modules.

Data sources retained in the individual catalog files:

- MapleScouter: https://maplescouter.com/en/input
- Flame tables: https://www.whackybeanz.com/calc/equips/flames
- Potential probabilities: https://brendonmay.github.io/cubingCalculator/
- Star Force reference: https://brendonmay.github.io/starforceCalculator/
- Equipment metadata/art: https://maplestorywiki.net/
- Character class/portrait: public Nexon GMS rankings and avatar CDN
- OCR model: PaddleOCR PP-OCRv6 medium recognition (model README in `models/`)


Equipment reader templates were captured from GMS. Per-character flame weights can use MapleScouter stat efficiencies.

MapleScouter manual preset v1 interoperability: https://maplescouter.com/en/input (public preset importer and template reviewed 2026-09-27). tests/fixtures/scouter_preset_template.json is its public template, retained only for schema compatibility tests.
