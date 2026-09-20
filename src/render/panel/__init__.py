"""The e-paper panel, driven by code this repository tests.

PLAN.md M10. Two files sit here and they are deliberately separated along the
line the vendored driver collapses:

`transport.py` owns the electricity - four GPIO pins and one SPI device - and
imports `gpiozero` and `spidev` inside its constructor, so the module is
importable anywhere and only *constructing* it claims hardware.

`driver.py` owns the panel's command protocol and knows nothing about how a
byte reaches it. Every command, every byte and every delay it emits is pinned
to the transcripts recorded from the vendored driver in
`tests/fixtures/transcripts/`, and every deliberate difference is a named
assertion in `tests/test_panel_driver.py` rather than a surprise on the wall.

The vendored `src/epd7in5b_V2.py` and `src/epdconfig.py` stay in the tree,
imported by nothing but the transcript harness. They are the reference these
files were recorded from and the only way to re-record.
"""
