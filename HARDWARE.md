# Hardware Reference

Vendor facts about the panel, and the driver behaviour verified against the
vendored source. This is the reference; [`INTENT.md`](INTENT.md) §4 states the
policy that follows from it.

Sources: [Waveshare 7.5inch e-Paper HAT (B) Manual](https://www.waveshare.com/wiki/7.5inch_e-Paper_HAT_(B)_Manual),
the vendor spec table, and `src/epd7in5b_V2.py` / `src/epdconfig.py` as vendored
in this repo.

---

## 1. The panel

**Waveshare 7.5inch e-Paper HAT (B), revision V3.**

| Property | Value |
| --- | --- |
| Colours | Red / black / white |
| Grey scale | 2 |
| Resolution | 800 × 480 |
| Dot pitch | 0.205 × 0.204 mm |
| Display area | 163.20 × 97.92 mm |
| Outline | 170.20 × 111.20 × 1.18 mm |
| Driver board | 65 × 30.2 mm |
| **Full refresh time** | **26 s** |
| Partial refresh | Supported, with restrictions — see §3 |
| Interface | SPI, mode 0 (CPOL=0, CPHA=0) |
| Operating voltage | 3.3 V / 5 V |
| Refresh power | 48 mW typical |
| Standby current | < 0.01 µA |
| Operating temperature | 0 – 40 °C |
| Storage temperature | −25 – 40 °C |

## 2. Version — V3 panel, V2 driver, deliberately

The physical panel is **V3** — confirmed against the panel itself on
2026-09-20, not inferred. The vendored driver is **`epd7in5b_V2.py`**. This is
correct and must not be "fixed".

Waveshare's manual: *"the resolution is same with V2, and its hardware and
interfaces are compatible with V2. As V3 is totally compatible with V2, you can
use the V2 demo."*

**There is no `epd7in5b_V3.py`.** The vendor's driver directory contains
`epd7in5.py`, `epd7in5_HD.py`, `epd7in5_V2.py`, `epd7in5_V2_old.py`,
`epd7in5b_HD.py`, `epd7in5b_V2.py`, `epd7in5b_V2_old.py` and `epd7in5bc.py` —
and no V3 variant of any of them.

Revision history for orientation: V1 was 640 × 384; V2 and V3 are both
800 × 480, which is why a V1 would have announced itself immediately and a V2
would not. The revision is printed on a label on the back of the panel; ours
reads V3.

Our vendored copy is Waveshare demo **V4.2, dated 2022-01-08**.

## 3. Refresh — the binding constraints

These are hardware-safety and image-integrity rules, not preferences. Several
carry an explicit risk of permanent, unrepairable damage.

**Minimum interval — 180 s.** *"Recommended that the refresh interval be at
least 180s."* Any scheduler in this project treats 180 s as a hard floor
between refreshes of any class.

**Maximum interval — 24 h.** Three-colour panels must be *"updated at least
once every 24 hours"* to avoid burn-in. A quiet-hours rule may never push the
gap past this.

**Sleep is mandatory between refreshes.** *"Cannot be powered on for a long
time. When the screen is not refreshed, please set the screen to sleep mode or
power off it"* — otherwise *"the screen will remain in a high voltage state for
a long time, which will damage the e-Paper and cannot be repaired."*

This makes `sleep()` part of every refresh cycle, not an optional teardown. Note
the corollary: *"after the screen enters sleep mode, the sent image data will be
ignored"* — so waking, writing and sleeping is the unit of work, and an
`init()` is required after every wake.

**Partial refresh must be followed by a full one — after about 5 rounds.**
*"Cannot refresh them with the partial refresh mode all the time. After
refreshing partially several times, you need to fully refresh EPD once.
Otherwise, the display effect will be abnormal."* The manual recommends
limiting partial-refresh positions and clearing the screen after **5 rounds** of
partial refreshing.

**Cold hurts.** *"Refresh in a low temperature environment may appear colour
cast, it needs to be static in the environment of 25 °C for 6 hours before
refresh."* Operating range starts at 0 °C. Relevant if the panel ends up in an
unheated hallway.

**Storage.** If the panel is taken out of service, clear the screen with the
program before storing it.

## 4. Driver API as vendored

Verified by reading `src/epd7in5b_V2.py`, not assumed from the vendor demo.

| Call | Line | Behaviour |
| --- | --- | --- |
| `init()` | 89 | Full-refresh init sequence |
| `init_Fast()` | 133 | Faster full-refresh init, different LUT setup |
| `init_part()` | 164 | Partial-mode init — **a different sequence from `init()`** |
| `display(black, red)` | 211 | Writes `0x10` (black) **and** `0x13` (red), then `0x12` refresh. The full 26 s cycle. |
| `display_Base_color(color)` | 225 | Fills both planes with a flat colour |
| `display_Partial(img, x0, y0, x1, y1)` | 245 | Enters partial mode via `0x91`, sets the window via `0x90`, writes **`0x13` only** |
| `Clear()` | 296 | Blanks both planes |
| `sleep()` | 309 | Deep sleep — required, see §3 |

### The critical asymmetry

`display_Partial()` writes **only the `0x13` plane**. There is **no partial
path to the red plane.** Partial refresh on this panel is black-and-white only.

The register numbering is confusing and worth stating plainly: in `display()`,
`0x10` carries black and `0x13` carries red. `display_Partial()` writes `0x13`
as well — but only after `0x91` has put the controller into partial mode, and
after pre-filling `0x10` blank across the window. The driver's own comment on
that write reads *"Write Black and White image to RAM"*. Same register,
different role, depending on the mode. **Verify this on the bench before
building anything on it (M9).**

Consequences that the design has to absorb:

- Any region whose content can be red is full-refresh-only, for all inputs.
- Partial and full need different init sequences, so switching class means
  re-initialising.
- The x window is **byte-aligned**: `display_Partial` floors `Xstart` to a
  multiple of 8 and rounds `Xend` up. Partial regions snap to 8-pixel
  boundaries on x. Y is unconstrained.
- `partFlag` is set at construction and cleared on first partial refresh; the
  first partial after construction pre-fills the window white.

### Buffer convention

`getbuffer()` inverts every byte — PIL uses 0=black, the panel uses 0=white.
`display()` then inverts the black buffer *back* before sending. Any new
renderer must respect this double inversion rather than reimplementing it.

## 5. Wiring

`src/epdconfig.py` hardcodes `RaspberryPi()` (classes for `JetsonNano` and
`SunriseX3` exist but are unused). Pin assignments match the standard HAT
wiring:

| Signal | BCM | Physical | In `epdconfig.py` |
| --- | --- | --- | --- |
| VCC | — | 3.3 V | — |
| GND | — | GND | — |
| DIN (MOSI) | 10 | 19 | `MOSI_PIN = 10` |
| CLK (SCLK) | 11 | 23 | `SCLK_PIN = 11` |
| CS (CE0) | 8 | 24 | `CS_PIN = 8` |
| DC | 25 | 22 | `DC_PIN = 25` |
| RST | 17 | 11 | `RST_PIN = 17` |
| BUSY | 24 | 18 | `BUSY_PIN = 24` |
| PWR | 18 | 12 | `PWR_PIN = 18` |

GPIO via `gpiozero`, SPI via `spidev`. Neither is available in the tools
container, so nothing under test may import `epdconfig` at module scope.

That is now enforced rather than remembered. `epd7in5b_V2.py` runs
`epdconfig = RaspberryPi()` at module scope, and that constructor claims all
five pins above — so importing the driver is a *claim* on the hardware, not a
declaration that it exists. The import therefore lives inside
`render/epd.py`'s `open_panel()`, reached through `importlib`, and
`tests/test_hardware_boundary.py` checks from three sides that nothing else
pulls it in: the source tree, the test tree, and a real interpreter that
imports the composition root and reports what came with it.

## 6. The deployment target, as surveyed

Surveyed over SSH on 2026-09-20. Recorded because several of these were assumed
wrong while M4 was being built, and because M8's bring-up should discover as
little as possible.

| Property | Value |
| --- | --- |
| Board | **Raspberry Pi 3 Model B Rev 1.2** — not a 3B+ |
| CPU | 1.2 GHz quad Cortex-A53 (BCM2837) |
| RAM | **906 MiB usable** — a 1 GB board, not 2 GB |
| Architecture | `aarch64` / `arm64` |
| OS | Debian 12 (bookworm) |
| Python | 3.11.2, with `python3-venv` |
| Storage | 29 GB card, 21 GB free |
| Swap | 512 MB (`dphys-swapfile`) |
| Thermals | 50.5 °C idle, `get_throttled=0x0` — never throttled |
| Time zone | `Europe/Copenhagen`, NTP active, clock synchronised |
| Hardware clock | **none** — `fake-hwclock` only |

**arm64 is the load-bearing fact.** Pillow publishes official `aarch64` wheels,
so `pip install pillow` is a download rather than a source build. On a 32-bit
`armv7l` image the same install would compile from source on a 1.2 GHz A53.

**SPI is already enabled and usable without root.** `dtparam=spi=on` is set,
`/dev/spidev0.0` and `0.1` exist, and the deploying user is in the `spi`, `gpio`
and `i2c` groups. M8 needs no `raspi-config` step and no `sudo`.

**There is no hardware clock, and this constrains the refresh policy.** After a
cold boot with no network, the system time is whatever `fake-hwclock` last
wrote, and it jumps — possibly by days — when NTP lands. §3's 180 s floor must
therefore be enforced against a **monotonic** clock, never against wall time; a
backwards jump in wall time would otherwise permit a refresh inside the floor,
and a forwards jump would stall the panel. Wall time remains correct for the
24 h keep-alive and for the timestamp the screen displays.

### Verified on the device

**2026-09-20 — the vendored driver runs on this board and clears the panel.**
The pre-rewrite code in the on-device checkout was executed against the real
display and blanked it. That settles, without a bench session: the HAT wiring
of §5, SPI access, panel power, and `gpiozero` 2.0.1 finding a working pin
factory under Bookworm — the last of which is a common breakage on this OS and
would otherwise have surfaced as an M8 mystery.

**2026-09-20 — the panel is a V3.** Read off the label on the back. §2's
pairing of a V3 panel with the V2 driver is now a checked fact rather than a
documented assumption, and needs no revisiting.

**Still unverified:** everything about *partial* refresh, including the `0x13`
question raised in §4. `Clear()` and `display()` exercise the full path only.

**2026-09-20 — this project's own renderer drives this panel.** `EPDRenderer`
(PLAN.md M8.1) rendered the live house through `--target epd --once` and the
result was photographed (PLAN.md M8.3). That settles three things the tools
container cannot reach:

- **The planes are not swapped.** `0x10` carried black and `0x13` carried red on
  the glass, as §4 reads them.
- **The double inversion is intact.** `getbuffer()` inverts and `display()`
  inverts the black plane back; the layout's one white-on-black row renders as
  white on black, which is what a reimplemented inversion would have broken
  first.
- **The §5 wiring is the wiring on the desk**, now through this project's own
  lazy `importlib` path rather than the pre-rewrite code's module-scope import.

**Still unverified:** everything about *partial* refresh, per the paragraph
above — and legibility at the real viewing distance, which a photograph taken
at a desk cannot answer.
