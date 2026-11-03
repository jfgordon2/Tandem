# Translation audit, November 3, 2026

All twelve language catalogs contain 1,673 translated entries, including every plural form. This audit checks extraction, catalog structure, runtime lookup, fonts and sample layouts. The catalogs remain machine drafts; completion is not a native speaker's approval of their wording.

## Fixed

- Every PO header was missing gettext's `plural=` expression. The generator now writes expressions matching the runtime, including Arabic's six forms and Ukrainian's three. Tests compare both implementations across count boundaries.
- The plural reader carried the `action` context from “Set up” into the next unrelated plural entry. Plurals, translations and draw-time flags now use the same complete-entry reader, including continued PO lines and multiple flag comments. Tests check catalog metadata and duplicate keys as well as entry coverage.
- Sixteen Developer View labels and states were missing translation markers. All twelve catalogs now include drafts for them, with translator notes explaining abbreviated acceleration labels. Metric keys and saved selections are unchanged.
- Strip labels were joined to layout whitespace before lookup, leaving them untranslated. They are now translated first. An explicit measured gap keeps Arabic labels apart from values. Long labels shorten within their own cell; numeric values stay intact. Spanish and Portuguese drafts use shorter lateral-acceleration labels.
- Seven internal colors, keyboard rows, backend identifiers and shell commands were incorrectly marked as translation messages. Those markers and catalog entries were removed.
- The alert render scene could load native Linux messaging libraries on macOS. It now consistently installs its intended stand-ins. The hotspot render scene also discarded the global pseudo audit's collected text, and language variants polluted its results. It now preserves the collector; the pseudo run keeps these scenes in the pseudo language.
- The fallback font gained Simplified Chinese 闲 and two composed Thai clusters. Only the Chinese and Thai source subsets needed changes; other source fonts retain their original bytes.

## Validation

- Full stand-in suite: **672 passed, 2 skipped**. The skips are Linux parent-death signals and Linux scheduling. The four hardware-stack files listed in `AGENTS.md` were excluded: `test_headroom_warning.py`, `test_home_layout.py`, `test_limit_offers.py` and `test_onroad.py`.
- Ruff and `git diff --check` pass.
- All twelve PO files pass `msgfmt --check-format --check-header`. Tests also check placeholders, plural forms, markup, URLs, line breaks, source metadata, fallback glyphs and Thai cluster coverage.
- English screens were rendered at 2160×1080 and assembled into the 70-screen mock comparison. Developer View was rendered in all twelve languages, English and the pseudo language. Its five default strip metrics fit in all 70 measured language/metric combinations after shortening where necessary.
- The repaired full pseudo run captured 984 distinct strings and listed 141 unbracketed strings. The list was reviewed: it contains measurements, keyboard letters, param keys, service and sample names, addresses, dates, sample release notes and navigation/weather sentences supplied directly by scene fixtures. Real forecast sentences use marked runtime templates. The US speed sign deliberately retains “SPEED LIMIT.”

Generated review files are local and git-ignored:

- `tools/out/translation-audit/index.html`: language screenshots and links to the other evidence.
- `tools/out/translation-audit/compare/index.html`: all 70 mock comparisons.
- `tools/out/translation-audit/pseudo/missed.txt`: the unbracketed-string review list.
- `tools/out/translation-audit/strip-fit.json`: strip width measurements.

## Remaining review work

- Settings search still matches English names and keywords only, even when results are drawn in the selected language.
- Dates and 12-hour clock suffixes still use English formatting.
- Native speakers should review all catalogs, especially operational warnings and the new compact Developer View terminology. This audit does not certify linguistic accuracy across every sentence.
- Pseudo expansion still shortens text in some existing cards, row subtitles and controls. The fallback keeps text inside its bounds, but a native review may identify wording that needs a shorter translation or a separately approved layout change.

No approved mock or upstream integration hook changed.
