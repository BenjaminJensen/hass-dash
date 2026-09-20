# Putting it on the wall

The bring-up runbook for `PLAN.md` M8.3 and the unit for M8.4. Everything above
this directory is proven in the tools container; nothing in this file can be,
which is why it is a runbook and not a test.

The target is the board surveyed in [`HARDWARE.md`](../HARDWARE.md) §6: a
Raspberry Pi 3B, arm64 Bookworm, SPI already enabled and usable without `sudo`,
time zone already `Europe/Copenhagen`, and no hardware clock.

---

## 1. A fresh checkout and a fresh virtual environment

Fresh on both counts, and both for reasons the survey found:

- **The existing checkout at `~/hass-dash` is dirty** — roughly 350 uncommitted
  lines of pre-rewrite work against the old coordinate-based `rooms.yml`. Move
  it aside rather than pulling onto it; it is kept as `~/hass-dash-old`.
- **Neither Python environment on the device is usable as it stands.** The
  system interpreter has Pillow but no PyYAML; the existing `~/py_envs` venv has
  neither and carries the `HomeAssistant-API` / `aiohttp` / `pydantic` stack
  that `sources/` was written to do without.

```bash
# Move the old one aside rather than pulling onto it, and take the name, so
# that the path in hass-dash.service is the path on disk.
mv ~/hass-dash ~/hass-dash-old

git clone -b rewrite/intent-architecture \
  https://github.com/BenjaminJensen/hass-dash ~/hass-dash
cd ~/hass-dash

# --system-site-packages so the venv can see the gpiozero and spidev that have
# already driven this panel, rather than building spidev from source.
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r deploy/requirements-device.txt
```

**Build the venv where it will live.** A venv records its own absolute path in
`pyvenv.cfg`, in `bin/activate` and in the shebang of every console script, and
none of those follow a `mv`. `bin/python` survives — it resolves its prefix
from its own location, so `app.py` and the unit keep working and the breakage
stays hidden — but `bin/pip` stops executing entirely. If the directory does
get renamed, `rm -rf .venv` and repeat the two commands above; there is nothing
in it worth preserving.

Check what that gave you before going further:

```bash
.venv/bin/python -c "import PIL, yaml, gpiozero, spidev; print(PIL.__version__)"
```

## 2. Credentials

Two lines in `.env` at the root of the checkout, in the format the
[README](../README.md#capturing-real-home-assistant-data) documents:

```
HASS_URL=http://homeassistant.local:8123
HASS_TOKEN=<a long-lived access token>
```

Two things the survey caught, both of which fail quietly rather than loudly:

- **The long-lived token in the old `.env` was revoked on 2026-09-20.** Mint a
  new one in Home Assistant (profile → security → long-lived access tokens).
- **`HASS_URL` must not end in `/api`.** The retired client wanted the suffix
  and this one appends `/api/states` itself, so a carried-over value produces
  `/api/api/states` — a 404 that reads like a broken instance. `app.py` refuses
  it at startup with the corrected URL in the message, so this is now loud.

## 3. One frame, to a file, before any electricity

The screen should be proven on this machine before the panel is involved, so
that a bad frame and a bad panel cannot be confused for each other:

```bash
.venv/bin/python src/app.py --source hass --target bmp --once --out /tmp/screen.bmp
```

That exercises the live instance, the config, the view and the renderer, and
writes the same BMP the container produces. Copy it off and look at it.

## 4. One frame, to the panel

```bash
.venv/bin/python src/app.py --source hass --target epd --once --verbose
```

Expect a single `refresh=full reason=first_frame … target=epd:7in5b_V2` line
about 30 seconds later. The panel flashes through its full 26-second cycle;
that is the only cycle it has.

**Then photograph it and compare against the BMP from step 3.** This is M8.3's
actual exit condition. Things worth looking at specifically, because they are
the ones the container cannot answer:

| Check | Why it is in doubt |
| --- | --- |
| Red is red, and black is black | The two planes are separate registers and swapping them is a one-line mistake that only hardware reveals (`HARDWARE.md` §4) |
| Nothing is inverted | `buffer()` inverts and `display()` inverts the black plane back |
| The text is legible from where people stand | `PLAN.md` M4: eleven rooms are comfortable at ~1,5 m and below the readable threshold at 3 m |
| Red is spent where it earns its keep | `INTENT.md` §2. With placeholder comfort bands most rooms alert; see slice 2.3 |

### 4.1 The driver bench check (`PLAN.md` M10.6)

The frame now goes out through this project's own driver rather than the
vendored one. A transcript proves the same bytes leave in the same order; it
cannot prove `spidev`'s chunking of a 48 000-byte write, `gpiozero`'s timing,
or that the BUSY deadline never fires early on a cold panel. So, once:

```bash
.venv/bin/python tools/panel_check.py frame
# wait 180 s — the vendor floor, and this script has no state to enforce it
.venv/bin/python tools/panel_check.py clear
```

Each prints `wall=` and `cpu=`. **The wall figure should be about 26 s and the
CPU figure a fraction of a second.** That second number is M10's one
measurable claim: the vendored `ReadBusy()` polled with no delay in the loop
and spent 29,9 s of CPU in a 32 s cycle (`HARDWARE.md` §4). If the CPU figure
comes back anywhere near the wall figure, the new poll delay is not doing what
it is supposed to.

Watch the clear as well as the frame. A `Clear()` is the one operation whose
result is unambiguous from across a room, and `HARDWARE.md` §3 wants it run
before a panel is ever put into storage anyway.

## 5. The loop, and then the unit

```bash
.venv/bin/python src/app.py --source hass --target epd --verbose
```

Leave it for an hour or so and read the log. What should be there: a first
frame, then `refresh=none reason=waiting`, then a full refresh on the
half-hour. What should **not** be there: any partial refresh at all. The panel
cannot write red outside a full refresh (`HARDWARE.md` §4), so `--target epd`
runs on a full-only cadence — `app.py`'s `policy_for()` is where that is
decided.

Then install the unit:

```bash
sudo cp deploy/hass-dash.service /etc/systemd/system/
sudoedit /etc/systemd/system/hass-dash.service   # check User= and the paths
sudo systemctl daemon-reload
sudo systemctl enable --now hass-dash
journalctl -u hass-dash -f
```

### What the unit is doing that is not obvious

**It passes `--state`, and that is the point of it.** The 180 s floor already
stops a process that restarts inside three minutes. What it does not stop is
one that restarts every four: without a file to read, each new process calls
itself a first frame and spends 26 seconds of high-voltage refresh on it, for
as long as the fault lasts. `/var/lib/hass-dash/refresh.json` is what makes the
second process wait for the cadence — and what carries the 24 h keep-alive
across a reboot. See `src/refresh/store.py`.

**It gives the panel time to be put to sleep.** systemd stops a unit with
SIGTERM; `app.py` turns that into the exception that unwinds through the
renderer's `finally`, and `TimeoutStopSec=45s` is long enough for a refresh
that is already running to finish first. A panel killed mid-cycle is left in a
high voltage state, which `HARDWARE.md` §3 says damages it permanently.

**It orders itself after `time-sync.target`, without requiring it.** The board
has no RTC, so at boot the clock is whatever `fake-hwclock` last wrote and the
first frame would be stamped with it. If you want the first frame to wait for a
real time rather than a plausible one:

```bash
sudo systemctl enable systemd-time-wait-sync
```

Without that, `time-sync.target` is simply never reached and the ordering line
does nothing — which is why it cannot deadlock the unit.

## 6. If it needs the memory back

Not a step, but the survey found it and this is where it belongs. A full
desktop is running — `lightdm`, X, CUPS, bluetooth, `wayvnc` — for roughly a
third of the 906 MiB. The dashboard peaks at 28 MB, so nothing needs reclaiming
today; if that changes, that is the obvious place, and `lightdm` plus
`NetworkManager-wait-online` are also what sit in front of this unit at boot.
