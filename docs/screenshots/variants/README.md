# Archived Review layout study

The PNGs here preserve the A/B study before the UI round. The user selected A
(plots above the date table); it is now the only Review layout. The prototype
flag and renderer were removed. Use the ordinary `--export` options for current
screenshots, or `scripts/render_ui_round.py` for the full UI round set.

The 40-fraction layout fixture cycles through the six rows of
`tests/data/synthetic_template_2535.csv`, changing only Grain ID to
`SYN-{index // 6 + 1}_zircon_z{index + 1}a_long-label`. It exists only in a
temporary directory. This is a layout stress fixture, not a scientific sample:
repeating rows changes the aggregate mean naturally. It has 27 reduced
fractions and 13 known linked-error failures; the original template has four
reduced and two failures.
