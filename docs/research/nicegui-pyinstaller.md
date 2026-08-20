# Research: NiceGUI native window + PyInstaller on Windows

Answers issue #2 (part of the map in #1). All facts below are sourced from primary docs/repos where possible, with version and fetch date noted. Fetched 2026-08-17.

## TL;DR

- **Native mode is one flag**: `ui.run(native=True, ...)`. It opens a real OS window via `pywebview` instead of a browser tab — no visible localhost URL. `window_size`, `fullscreen`, `frameless` all imply `native=True` too.
- **On Windows, pywebview picks `edgechromium` first, falling back to deprecated `mshtml`** (IE11 engine). EdgeChromium needs **.NET Framework ≥ 4.6.2** and the **Edge WebView2 Runtime** installed — both are preinstalled on current Windows 10/11, but can be missing on stripped-down or older machines. Ship the WebView2 bootstrapper if you need to be safe. Source: [pywebview web_engine.md](https://github.com/r0x0r/pywebview/blob/master/docs/guide/web_engine.md).
- **Port is auto-picked in native mode**, not fixed: `native.find_open_port()` scans ports 8000–8999 and NiceGUI uses whatever's free, so collisions are a non-issue and multiple instances can run side-by-side. In plain browser mode the port is a fixed default (8080) and you must call `find_open_port()` yourself if you want the same collision-avoidance. Source: [NiceGUI docs, section_configuration_deployment.py](https://github.com/zauberzeug/nicegui/blob/main/website/documentation/content/section_configuration_deployment.py).
- **NiceGUI ships its own PyInstaller wrapper, `nicegui-pack`** (source: [`nicegui/scripts/pack.py`](https://github.com/zauberzeug/nicegui/blob/main/nicegui/scripts/pack.py)), which auto-adds `--add-data <nicegui-pkg-dir>;nicegui` so static/frontend assets are bundled correctly. Use it (or replicate its `--add-data` flag) — a raw `pyinstaller main.py` will produce a blank/broken UI without it.
- **`onedir` is the safer default; `onefile` is measurably slower to start** because PyInstaller has to unzip to a temp dir on every launch, and standalone `--onefile` binaries are also the ones flagged most by AV heuristics. NiceGUI's own docs recommend `onedir` + zip-and-distribute unless a single .exe is a hard requirement.
- **`multiprocessing.freeze_support()` is mandatory** as the *first statement* in the `if __name__ == '__main__':` guard for any packaged native-mode app — NiceGUI's native window runs in a child process, and without `freeze_support()` a frozen exe re-spawns itself in an infinite loop on Windows. `app.native.*` settings must be set *outside* that guard.
- **PyInstaller executables (especially `--onefile`, especially PyInstaller ≥ v6) trigger Windows Defender / third-party AV false positives**; this is a widely reported, unresolved upstream issue, not a NiceGUI bug. Downgrading to `--onedir`, code-signing, and/or submitting the binary to AV vendors are the practical mitigations — no clean fix exists as of this writing.
- **All the UI-brief widgets exist as first-class NiceGUI elements**: `ui.notify`, `ui.dialog`, `ui.linear_progress`/`ui.circular_progress`, `ui.spinner`, `.tooltip()`, `ui.button(...).disable()/.enable()`, `ui.log` (append-only text log widget) and `ui.table` (or `ui.aggrid`), with `ui.timer` as the standard mechanism for periodic/live UI refresh.
- **Recommended pins**: NiceGUI's own `pyproject.toml` constrains `pywebview>=5.0.1,<7` and `python>=3.10,<4`; current stable NiceGUI is **3.16.0** (released 2026-08-12) — see the "Recommended version pins" section for the exact combo to lock in.

---

## 1. Native desktop-window mode

Enabled via `ui.run(native=True, ...)`. From the NiceGUI docs source (`section_configuration_deployment.py`, fetched from `main` branch 2026-08-17):

- `window_size`, `fullscreen`, and `frameless` are convenience params that each imply `native=True` even if you don't pass it explicitly.
- Extra kwargs for the underlying window/start calls go through `app.native.window_args` and `app.native.start_args` — these map 1:1 onto pywebview's `webview.create_window()` / `webview.start()` parameters ([pywebview API](https://pywebview.flowrl.com/api/)) and take precedence over `ui.run` params.
- `app.native.settings` maps to `webview.settings`.
- `app.native.main_window` gives async access to the live pywebview `Window` object.
- **Requirement**: "Native mode requires a browser engine with ES module and import map support (Chrome 89+)." On Windows this requires the **.NET Framework** because pywebview's EdgeChromium backend depends on it — normally preinstalled, but can be absent on minimal/fresh installs.
- Native mode runs the window in a **separate `multiprocessing.Process`** — config done inside `if __name__ == '__main__':` after `ui.run(native=True)` has no effect on the child process; `app.native.*` config must be set at module scope (outside the guard) to take effect. This is directly relevant to the `freeze_support()` requirement in section 4.
- **Storage caveat for native mode**: `NICEGUI_STORAGE_PATH` (default `.nicegui` in CWD) is shared by every instance launched from the same working directory. Because native mode makes running multiple copies of the same packaged exe simultaneously more likely, each process holds its own in-memory copy and will silently clobber another instance's writes. Give each instance its own `NICEGUI_STORAGE_PATH` or use Redis storage if concurrent instances must share state.

**Windows backend**: pywebview chooses, in order, `edgechromium` then falls back to `mshtml` (deprecated, IE11-based, only guaranteed-available renderer). A third option, `cef` (via CEF Python), can be forced with `PYWEBVIEW_GUI=cef` or `webview.start(gui='cef')`. Table from pywebview docs (`docs/guide/web_engine.md`, fetched 2026-08-17 from `r0x0r/pywebview@master`):

| Platform | Code | Renderer | Requirement |
|---|---|---|---|
| Windows | `edgechromium` (default/preferred) | Chromium (evergreen) | **.NET Framework ≥ 4.6.2** and **Edge WebView2 Runtime** installed |
| Windows | `mshtml` (fallback) | MSHTML/IE11 | Deprecated; only one guaranteed present on every Windows box |
| Windows | `cef` (opt-in) | CEF (Chrome 66) | Requires `cefpython3` extra dependency |

A real-world confirmation: [NiceGUI issue #2751](https://github.com/zauberzeug/nicegui/issues/2751) (March 2024) shows a blank native window on Windows 11 with console output `"[pywebview] MSHTML is deprecated... use Edge Chromium"` — i.e. the box had fallen back to MSHTML instead of EdgeChromium, which is a known cause of broken rendering. Also see the NiceGUI docs' own troubleshooting note about `WebView2Loader.dll` not being found (workaround: move the DLL up a directory from `.venv/Lib/site-packages/webview/lib/x64/` to `.venv/Lib/site-packages/webview/lib/`), referencing upstream [pywebview issue #1078](https://github.com/r0x0r/pywebview/issues/1078).

Extra dependency pulled in: `pywebview` is an **optional extra**, `nicegui[native]`, or installed automatically if you `pip install nicegui` and use `native=True`  in recent NiceGUI (it's a hard dependency of the base package as of 3.x — check `pyproject.toml`, see pins section). No separate download is normally required for the WebView2 runtime on a standard, up-to-date Windows 10/11 machine, since Microsoft now ships WebView2 in-box; a fresh/locked-down enterprise image is the risk case.

## 2. PyInstaller recipe for NiceGUI

**NiceGUI ships an official CLI wrapper, `nicegui-pack`**, installed as a console-script entry point and backed by [`nicegui/scripts/pack.py`](https://github.com/zauberzeug/nicegui/blob/main/nicegui/scripts/pack.py) (fetched 2026-08-17, `main` branch). This *is* the "hook" — there's no separate PyInstaller hook module under `nicegui/hooks/`; instead `pack.py` is a thin argparse wrapper around `pyinstaller`/`python -m PyInstaller` that:

- Always adds `--add-data "<path-to-installed-nicegui-package>;nicegui"` (or `:` separator on non-Windows) so NiceGUI's static/frontend assets (Vue/Quasar bundles, ESM modules, templates) are found at runtime. **This is the load-bearing flag** — a bare `pyinstaller main.py` without it produces a broken or blank UI (see [NiceGUI issue #4490](https://github.com/zauberzeug/nicegui/issues/4490) "PyInstaller fails to pack a simple NiceGui script" and [#2550](https://github.com/zauberzeug/nicegui/issues/2550) "Nicegui shows blank screen with pyinstaller").
- Also auto-detects and bundles `pyecharts` if installed.
- Invokes PyInstaller as `python -m PyInstaller` (not the `pyinstaller` shim) specifically so the venv's own PyInstaller install is used — the docs warn that using the wrong (e.g. globally installed) PyInstaller version produces broken apps.
- Exposes `--windowed`, `--onefile`, `--onedir`, `--icon`, `--clean`, `--noconfirm` passthroughs.

Minimal known-good example from NiceGUI docs:

```python
# main.py
from nicegui import native, ui

def root():
    ui.label('Hello from PyInstaller')

ui.run(root, reload=False, port=native.find_open_port())
```
```bash
nicegui-pack --onefile --name "myapp" main.py
```

**Required `ui.run` conditions for packaging** (from the docs): `reload=False` (the auto-reload dev server does not work frozen — [#3106](https://github.com/zauberzeug/nicegui/issues/3106) "auto-reload make pyinstaller build failed" is exactly this), and either pass a `root` page function to `ui.run` or define at least one `@ui.page` — a script with no page function will not bundle correctly.

**onefile vs onedir, NiceGUI-specific guidance** (same doc):
- `--onefile`: single exe, most convenient to hand to a non-technical user, but PyInstaller unzips to a fresh temp directory on **every launch**, so startup is measurably slower — this is inherent to how PyInstaller's onefile bootloader works, not a NiceGUI issue.
- `--onedir` (or omitting both flags, which is PyInstaller's own default): faster startup since nothing is unpacked at runtime; ship it as a zipped folder and have the user unzip once.
- NiceGUI's docs explicitly suggest: build without `--onefile`, zip the `dist/` folder yourself, and have users unzip once — avoiding the "constant expansion of files" onefile causes on every run.
- Official summary table from the docs (`nicegui-pack` flag × `ui.run(native=...)` → UX):

  | `nicegui-pack` | `ui.run(...)` | Result |
  |---|---|---|
  | `onefile` | `native=False` | single exe, runs in browser |
  | `onefile` | `native=True` | single exe, runs in popup window |
  | `onefile` + `windowed` | `native=True` | single exe, no console (correct combo for a desktop app) |
  | `onefile` + `windowed` | `native=False` | **avoid** — no way for the user to exit (no console, no window close = quit) |
  | neither flag | — | `dist/myapp/` directory, zip and distribute manually |

- `--windowed` should **only** be combined with `native=True`; without a native window and without a console, the process has no way for the user to signal shutdown (docs are explicit about this footgun).

**Nuitka** is mentioned in the docs as an alternative to PyInstaller (slower builds, harder to decompile) but is out of scope here since the map (#1) already decided on PyInstaller.

pywebview's own freezing guide ([`docs/guide/freezing.md`](https://github.com/r0x0r/pywebview/blob/master/docs/guide/freezing.md), fetched 2026-08-17) adds one more caveat worth carrying into the build: **PyInstaller bundles every backend pywebview supports, not just the one you use** — e.g. if `PyQt` happens to be importable in your environment, PyInstaller will pull it in even though the app only ever uses `edgechromium` on Windows. Add unwanted backends to `excludes` in a custom `.spec` file if bundle size/AV surface matters.

## 3. Port behavior

- **Native mode**: no fixed port. `native.find_open_port()` scans ports **8000–8999** for an open one and NiceGUI uses it automatically if you don't pass `port=`. This is by design specifically so that "multiple copies of the same packaged executable" (a very real scenario with PyInstaller-shipped consumer apps) **can run simultaneously without colliding**.
- **Browser/server mode**: port defaults to a fixed `8080` and is *not* auto-scanned — if you want the same collision-avoidance in browser mode (or want a specific deterministic port), call `native.find_open_port()` yourself and pass it to `port=`.
- Practical implication for this project: since the map (#1) has already decided on native mode, port collision is a non-issue out of the box — no code needed to handle "port already in use."

Source: NiceGUI docs `section_configuration_deployment.py` (`main`, fetched 2026-08-17), "Native Mode" section.

## 4. Startup time & Windows-specific pitfalls

- **`--onefile` startup penalty**: PyInstaller's own docs ([operating-mode.html](https://pyinstaller.org/en/stable/operating-mode.html), current stable) state the bootloader "uncompresses the support files and writes copies into the temporary folder" on every launch of a onefile build, making it slower than onedir. Their own recommendation: get the app working in onedir mode first, since onefile issues are harder to diagnose.
- **`multiprocessing.freeze_support()` — mandatory for packaged native apps.** NiceGUI's docs are explicit (`section_configuration_deployment.py`, "Packaging with Native Mode"): call `freeze_support()` as the *first statement* inside `if __name__ == '__main__':`, or the frozen app respawns itself in an endless process-spawn loop on Windows. This matches PyInstaller's own multiprocessing docs, which explain Windows' `spawn` start method re-invokes the exe with `--multiprocessing-fork` args that must be intercepted by `freeze_support()`. Any `app.native.*` config must live *outside* the guard (module scope) so it's applied before the freeze-support interception. Canonical snippet from the docs:

  ```python
  from multiprocessing import freeze_support
  from nicegui import app, ui

  app.native.window_args['transparent'] = True  # outside main guard

  if __name__ == '__main__':
      freeze_support()  # first statement in main guard
      ui.run(native=True, reload=False)
  ```

- **Antivirus false positives — real and unresolved upstream.** PyInstaller `--onefile` builds (and to a lesser extent onedir) are commonly flagged by Windows Defender and third-party AV as trojans/generic malware. This is a heuristic problem (self-extracting packed binary + unsigned + no reputation history), not a code bug. Documented in [PyInstaller issue #8164](https://github.com/pyinstaller/pyinstaller/issues/8164) (opened 2023-12-13): the reporter says false positives "exploded" starting with PyInstaller v6.x versus v5.13.2, across 15-18 AV engines including McAfee/Bitdefender. Secondary corroboration: [pythonguis.com FAQ on antivirus + PyInstaller](https://www.pythonguis.com/faq/problems-with-antivirus-software-and-pyinstaller/) (undated, but reflects the same v6 pattern) recommends onedir over onefile and code-signing as the two practical mitigations, plus submitting binaries to AV vendors for allow-listing. **This directly affects the "Not yet specified: code signing and SmartScreen" open question in issue #1** — recommend the map explicitly plan for either code signing or an onedir-based (not onefile) build to reduce false-positive risk.
- **Console window suppression**: PyInstaller's `--windowed` (aliases `-w`, `--noconsole`) suppresses the console on Windows/macOS (source: [pyinstaller.org usage docs](https://pyinstaller.org/en/stable/usage.html), current stable). Caveat from PyInstaller's own "Common Issues and Pitfalls" page: in `--noconsole` builds, `sys.stdout`/`sys.stderr` become `None`, so any code path touching them raises `AttributeError` unless redirected first. NiceGUI's docs independently confirm this exact failure mode for `nicegui-pack` apps ("`TypeError: a bytes-like object is required, not 'str'`") and give the same fix: redirect `sys.stdout = open('logs.txt', 'w')` at the top of `main.py` ([NiceGUI issue #681](https://github.com/zauberzeug/nicegui/issues/681)). As covered in section 2, `--windowed` should only be used together with `native=True` — otherwise there's no way for the user to close the app (no console to Ctrl-C, no window to close).
- Windows also caches app icons by exe path (stale icon after rebuild — restart or move the exe to refresh) and PyInstaller's Control-Flow-Guard-hardened bootloader can occasionally need a `--no-cfg` rebuild for compatibility with certain native libraries — both noted on PyInstaller's [common-issues-and-pitfalls](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html) page, current stable, fetched 2026-08-17.

## 5. Widget coverage for the UI brief

All confirmed present as documented elements in the NiceGUI docs source tree (`website/documentation/content/*.py`, `main` branch, fetched 2026-08-17):

- **Notifications** — `ui.notify(message, type=..., close_button=..., multi_line=...)`. Types include `'positive'`, `'negative'`, `'warning'`, etc. (`notify_documentation.py`, `notification_documentation.py`).
- **Dialogs** — `ui.dialog()` used as a context manager with `.open()`/`.close()`, and an *awaitable* form (`await dialog` returns a submitted result, or `None` on cancel/escape) — useful for confirmation dialogs called out in the #1 brief (`dialog_documentation.py`).
- **Progress bars** — `ui.linear_progress()` and `ui.circular_progress()`, settable via `.value` or bound reactively; `.props('instant-feedback')` available on linear progress for snappier updates (`linear_progress_documentation.py`, `circular_progress_documentation.py`).
- **Spinners** — `ui.spinner(...)` (`spinner_documentation.py`).
- **Tooltips** — `.tooltip('text')` chainable on most elements, or `ui.tooltip()` (`tooltip_documentation.py`).
- **Disabled buttons** — `ui.button(...).disable()` / `.enable()`, demonstrated in the docs with a context-manager pattern that disables a button for the duration of an async call and re-enables it in a `finally` block — a directly reusable pattern for the run-engine calls this app will make (`button_documentation.py`).
- **Live-updating log/table**:
  - `ui.log(max_lines=...)` — append-only scrolling text widget with a `.push(text)` method; can also be attached directly to a Python `logging.Logger` as a handler (with the docs' explicit warning to detach the handler on client disconnect to avoid leaking references) (`log_documentation.py`).
  - `ui.table` (row/column grid) and `ui.aggrid` (AG Grid wrapper, more feature-rich for large/sortable data) are both available for structured live data (`table_documentation.py`).
  - **Live refresh mechanism**: `ui.timer(interval_seconds, callback)` is the standard way to drive periodic UI updates — e.g. `ui.timer(1.0, lambda: label.set_text(...))`. Timers can be toggled via `.active` and stopped permanently via `.cancel()` (`timer_documentation.py`). This is the natural mechanism for a "live run log" or "live progress" panel in this app: a background thread/process pushes results, and a `ui.timer` on the UI side polls and refreshes the bound table/log/progress widgets.

## 6. Version pinning

From NiceGUI's own `pyproject.toml` (`main` branch, fetched 2026-08-17):

```
requires-python = ">=3.10,<4"
native = ["pywebview>=5.0.1,<7"]   # i.e. pywebview is constrained to the 5.x/6.x line
```

Current releases as of 2026-08-17:
- **NiceGUI**: latest stable tag `v3.16.0`, published 2026-08-12 ([releases](https://github.com/zauberzeug/nicegui/releases)).
- **pywebview**: latest `6.2.1`, published 2026-04-15 ([releases](https://github.com/r0x0r/pywebview/releases)) — within NiceGUI's `<7` ceiling.
- **PyInstaller**: latest `v6.22.2`, published 2026-08-17 ([releases](https://github.com/pyinstaller/pyinstaller/releases)).

**Known breakage between versions to watch for:**
- [NiceGUI #5020](https://github.com/zauberzeug/nicegui/issues/5020): `ui.echart()` renders a blank page under `native=True` starting in **NiceGUI v2.19.0** (worked fine on v2.18.0) — not directly relevant unless the app uses ECharts, but illustrates that native-mode rendering regressions do happen across NiceGUI minor versions; verify visually after any NiceGUI version bump, not just after major bumps.
- [PyInstaller #8164](https://github.com/pyinstaller/pyinstaller/issues/8164): antivirus false-positive rate "exploded" going from PyInstaller v5.13.2 to the v6.x line — if AV false positives become a blocking problem in practice, this is a documented, version-correlated regression, not random noise (see section 4).
- [pywebview #1078](https://github.com/r0x0r/pywebview/issues/1078) / NiceGUI docs troubleshooting note: `WebView2Loader.dll` not found at runtime in some venv layouts — documented workaround is to move the DLL up a directory under `site-packages/webview/lib/`. Worth a smoke test specifically on the frozen build, since PyInstaller's data-collection can interact with this differently than a plain venv run.
- [NiceGUI #1264](https://github.com/zauberzeug/nicegui/issues/1264): `RuntimeError: cannot call null pointer...` when packaging native mode with PyInstaller — reported against very old versions (NiceGUI 1.3.5, Python 3.8.9, PyInstaller 5.13) and tied to `pythonnet`/`clr_loader` resolution inside a frozen build; not expected to reproduce on the modern pins below, but worth knowing the failure signature if a similarly cryptic `RuntimeError` shows up during the actual build.

### Recommended version pins

| Package | Version | Rationale |
|---|---|---|
| Python | **3.12.x** (latest 3.12 patch) | Inside NiceGUI's `>=3.10,<4` requirement; 3.12 has the best PyInstaller compatibility track record of the actively-maintained versions as of 2026-08-17 (3.13 is newer and less battle-tested with PyInstaller/pywebview combos; avoid 3.10/3.11 only if there's no other reason to pin older). |
| NiceGUI | **3.16.0** (current stable, 2026-08-12) — or pin to whatever is current stable at build time and re-verify native-mode rendering, per the v2.19 ECharts regression above | Latest stable at time of research; ships `nicegui-pack`. |
| pywebview | Let NiceGUI's own constraint resolve it (`>=5.0.1,<7`), currently resolves to **6.2.1** | Matches NiceGUI's tested range; do not manually pin outside `<7` without re-testing native mode. |
| PyInstaller | **6.x, latest available at build time (currently 6.22.2)**, installed **inside the project's own venv** and invoked via `nicegui-pack` (which uses `python -m PyInstaller`) | Avoid a system-wide/global PyInstaller install — NiceGUI's docs warn this causes broken apps from version mismatches. If AV false-positive rate becomes a practical blocker, be aware v5.13.2 was the last version before the reported explosion in false positives (PyInstaller #8164) — re-test onedir + code-signing first before considering a downgrade, since v5.13.2 is now three-plus years old and lacks newer Python-version support. |

**Build flags to standardize on** (per section 2 and 4): `nicegui-pack --onedir --windowed --name "<AppName>" --icon <path.ico> main.py`, with `ui.run(native=True, reload=False, port=native.find_open_port())` and `freeze_support()` as the first statement under `if __name__ == '__main__':`. Prefer `--onedir` over `--onefile` for both startup speed and lower AV false-positive risk, packaged into a single installer via Inno Setup (already decided in #1) so the end user still only sees one "Setup.exe" and one Start-menu shortcut regardless of the onedir folder structure underneath.
