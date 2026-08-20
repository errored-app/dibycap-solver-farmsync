# Auto-update research: PyInstaller Windows app via GitHub Releases

**Checked on: 2026-08-17.** All maintenance/activity claims below (last commit, last release, open issues, archived status) reflect repo state as observed on this date; re-verify before relying on them again after any significant time has passed.

Target: a non-technical Windows user running a PyInstaller-frozen console app, installed via an Inno Setup `Setup.exe`, that needs to self-update from the public repo `errored-app/dibycap-solver-farmsync` on GitHub Releases.

---

## Answer up front

- **Library landscape:** PyUpdater is **archived/abandoned** (CONFIRMED). pywinsparkle (the Python WinSparkle binding) is **abandoned** — no activity since 2019 (CONFIRMED), even though the underlying WinSparkle C library is still maintained. tufup is **alive but low-activity/niche** (CONFIRMED — real releases, but a small single-maintainer project with an update-framework learning curve that's overkill for this use case). None of the three is a slam-dunk fit for "solo dev, simple console app, non-technical user."
- **Recommendation: build the plain custom updater** described in Question 2 (GitHub Releases API + download `Setup.exe` + run it with Inno Setup silent switches + exit). It's the least code, has zero extra runtime dependencies, needs no packaging-format lock-in, and every piece of its behavior is documented by a primary source (GitHub REST API docs, Inno Setup docs). This is the recommended overall mechanism.
- **Inno Setup switches:** Use `/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS /RESTARTAPPLICATIONS /LOG="path"` when invoking the new installer (CONFIRMED, jrsoftware.org). The running app must **exit itself first** — Inno Setup's `CLOSEAPPLICATIONS`/Restart Manager integration is a convenience/fallback, not a substitute for the app closing on its own (CONFIRMED + reasoning below).
- **GitHub Releases API:** Unauthenticated rate limit is **60 requests/hour** per IP (CONFIRMED, docs.github.com). `GET /repos/{owner}/{repo}/releases/latest` for the newest non-prerelease/non-draft release; each asset's `browser_download_url` is a stable direct-download link (CONFIRMED).
- **Version detection in the frozen app:** Bake the version into the source as a `__version__` constant (or a small `version.py` generated at build time) and read that directly — do **not** rely on `importlib.metadata` package metadata, which is unreliable/absent in a frozen build. Separately, embed a Windows version resource via PyInstaller's `--version-file` for the .exe's own file/product-version metadata (CONFIRMED, PyInstaller docs) — this is for Windows Explorer/Properties display, not for the app's internal update-check logic.
- **UX recommendation:** For this non-technical user, do a **background silent check** on startup (or on a timer), and only surface UI when an update *is* found: a simple "Update available — installing now" notice with a progress bar for the download, then auto-launch the installer and exit. Do not ask the user to approve/deny technical details; do not leave it fully invisible either (a corrupt/silent failure to update indefinitely is worse for a non-technical user than a brief, friendly notice). Reasoning detailed in Q5.
- **Failure handling:** Always download to a temp file first and atomically rename only after success; verify the file's SHA-256 against a checksum published alongside the release asset (GitHub does not compute/publish checksums for you — CONFIRMED); never touch the existing install until the new installer is verified and launched; let Inno Setup's own installation transaction (it only replaces files after the new installer itself has verified its payload) be the actual "point of no return," and keep the failure mode of the *checker* be "do nothing, keep running the current version" in every error case (no network, corrupt download, checksum mismatch).

---

## 1. Update library landscape

### PyUpdater
- Repo: `Digital-Sapphire/PyUpdater`.
- **CONFIRMED — archived.** `gh api repos/Digital-Sapphire/PyUpdater` returns `"archived": true`, `"pushed_at": "2022-09-25T22:41:26Z"` (last code push over 3.5 years before this check) and `"open_issues_count": 0` (issues are locked/disabled on archived repos, not "resolved"). Source: GitHub REST API, checked 2026-08-17.
- No releases were returned by the GitHub Releases API for this repo at check time.
- Verdict: **dead**. Do not build on it.

### WinSparkle / pywinsparkle
- **WinSparkle itself (the C/C++ framework)**, repo `vslavik/winsparkle`: **CONFIRMED alive**. `pushed_at: 2026-08-10`, `updated_at: 2026-08-17`, latest release `v0.9.4` published `2026-07-21`, with `v0.9.3` (2026-05-18) and `v0.9.2` (2025-10-13) before it — a healthy, actively-released project. Source: GitHub REST API on `vslavik/winsparkle`, checked 2026-08-17. Open issues: 22 (normal for an active project, not a red flag by itself).
- **However**, WinSparkle is a native DLL-based framework designed for C/C++/`.NET`-style apps with an installed "appcast" XML feed and its own UI; it's not a natural fit for a PyInstaller console app without a GUI toolkit already in play.
- **pywinsparkle** (the Python binding needed to actually use WinSparkle from Python), repo `dyer234/pywinsparkle`: **CONFIRMED abandoned**. `pushed_at: 2019-04-08T14:29:01Z` — over 7 years with no code push as of this check; only 1 open issue, no GitHub Releases published (tags only, latest tag `1.4.0`) — activity signal is essentially flat since 2019. Source: GitHub REST API, checked 2026-08-17. Also distributed on PyPI as `pywinsparkle` (per PyPI project page, secondary source since PyPI isn't strictly a "repo activity" source, but corroborates it's a thin, largely static wrapper).
- Verdict: the underlying C library is maintained, but the Python glue layer needed for this project is **dead**, and adopting WinSparkle would mean either resurrecting/forking that binding or writing new ctypes bindings — extra surface area for no real benefit over a custom HTTP-based approach, especially since this is a console app (WinSparkle's appcast+UI model targets desktop apps with a native update dialog).

### tufup
- Repo: `dennisvang/tufup`. **CONFIRMED alive but low-velocity.** `pushed_at: 2025-10-04T12:25:49Z` (about 10.5 months before this check), `updated_at: 2026-07-21`. Releases: `v0.10.0` (2025-10-03), `v0.9.0` (2024-06-11), `v0.8.0` (2024-04-19) — real, but infrequent, releases; 22 open issues on what is a small project. Source: GitHub REST API, checked 2026-08-17.
- tufup wraps [TUF (The Update Framework)](https://theupdateframework.io/) — a cryptographically-signed, key-rotation-capable update spec built for security-critical, high-value-target software (this is the same lineage as projects like PyPI's own package-signing work). It brings real security guarantees (protection against compromised/malicious update servers, rollback attacks, key compromise) that a plain HTTPS+GitHub-Releases approach does not fully replicate.
- Verdict: **alive, single-maintainer, functional**, but its threat model (defending against a compromised update *server* / CDN, not just a compromised *dev machine*) and operational overhead (managing signing keys, a TUF repository layout, key rotation ceremonies) are disproportionate for a small internal/console tool distributed straight from GitHub Releases over HTTPS with GitHub's own auth model protecting the repo. Worth revisiting only if this app's threat model changes (e.g., becomes high-value target, needs offline/mirrored distribution).

### Plain custom updater (GitHub Releases API)
- No "repo" to check — it's a pattern, built directly against GitHub's public REST API (`docs.github.com/en/rest/releases`) which is itself a maintained, stable, primary-source API (CONFIRMED — see Q3). Zero third-party runtime dependency risk; the only "maintenance" burden is the small amount of code you write and own.

**Summary table**

| Option | Alive? | Evidence (checked 2026-08-17) |
|---|---|---|
| PyUpdater | **No — archived** | `archived: true`, last push 2022-09-25 |
| WinSparkle (C lib) | Yes | last push 2026-08-10, release 2026-07-21 |
| pywinsparkle (Python binding) | **No — abandoned** | last push 2019-04-08, no GH Releases |
| tufup | Yes, low-velocity | last push 2025-10-04, releases roughly yearly |
| Custom / GitHub Releases API | N/A (no library) | API itself actively maintained by GitHub |

---

## 2. The plain custom pattern, in detail

Pattern: query GitHub Releases API for latest tag → compare to running version → download `Setup.exe` asset → run new installer with Inno Setup silent switches → exit running app so the installer can proceed.

### Exact Inno Setup command-line switches (CONFIRMED, source: [jrsoftware.org/ishelp — "Setup Command Line Parameters"](https://jrsoftware.org/ishelp/topic_setupcmdline.htm), checked 2026-08-17)

- **`/SILENT`** — "Instructs Setup to be silent... the wizard and the background window are not displayed but the installation progress window is [shown]."
- **`/VERYSILENT`** — same as `/SILENT` but the installation progress window is hidden too; if a restart is required and `/NORESTART` isn't used, Setup will restart without prompting. This is the switch to use for a truly hands-off update.
- **`/SUPPRESSMSGBOXES`** — "Instructs Setup to suppress message boxes. Only has an effect when combined with `/SILENT` or `/VERYSILENT`." Applies default (usually non-destructive) answers to Yes/No/OK-Cancel prompts. Note: per the docs, a small number of message-box types cannot be suppressed this way (e.g. certain fatal "Setup has detected..." errors) — a residual dialog is still possible in rare failure paths.
- **`/CLOSEAPPLICATIONS`** — "Instructs Setup to close applications using files that need to be updated by Setup if possible."
- **`/RESTARTAPPLICATIONS`** — "Instructs Setup to restart applications if possible" (i.e., relaunch whatever it force-closed, after install).
- **`/FORCECLOSEAPPLICATIONS`** — forces the close instead of asking/backing off, at the risk of the target app losing unsaved work.
- **`/NORESTART`** — "Prevents Setup from restarting the system following a successful installation, or after a *Preparing to Install* failure that requests a restart." Should almost always be included for an unattended update on a user's machine — an unexpected reboot is one of the worst outcomes for a non-technical user.
- **`/LOG` / `/LOG="filename"`** — writes an install log (auto-named in TEMP, or to a fixed path with `="filename"`); very useful for diagnosing failed silent updates after the fact, since there's no user watching the screen.
- **`/SP-`** — suppresses the initial "This will install... Do you wish to continue?" prompt (moot under `/VERYSILENT`, but harmless to include).
- **`/DIR="X:\dirname"`** — override install directory (only needed if the app doesn't always install to the same default path).

**Recommended invocation for this use case:**
`Setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS /RESTARTAPPLICATIONS /LOG="C:\path\to\update.log"`

### How Inno Setup overwrites files belonging to the currently-running app

**CONFIRMED**, source: [jrsoftware.org — `[Setup]` section `CloseApplications` directive](https://jrsoftware.org/ishelp/topic_setup_closeapplications.htm) and [`AppMutex` directive](https://jrsoftware.org/ishelp/topic_setup_appmutex.htm), checked 2026-08-17.

Windows will not let you overwrite or delete a file (particularly a running `.exe` or a loaded `.dll`) while a process has it open/mapped. Inno Setup has two complementary mechanisms for this, but **neither is a substitute for the app closing itself before/at the start of the update**:

1. **`CloseApplications` (default `yes`)** — Setup uses the **Windows Restart Manager** API to detect which running processes have a lock on files that `[Files]`/`[InstallDelete]` need to touch, and can close (and, with `RestartApplications`, later relaunch) those processes automatically. This works even without any code in the target app, but it is best-effort: Restart Manager can fail to enumerate/close a process (e.g., some processes decline gracefully, or the detection race with a just-launched process), and forcing closure (`/FORCECLOSEAPPLICATIONS`) risks lost state/unsaved work.
2. **`AppMutex`** — an explicit, deterministic alternative: the app creates a named Windows mutex on startup; Setup checks for that mutex's existence and, if found, blocks and tells the user (or, combined with silent switches' default handling, can be configured to wait/prompt) to close the app before installing. This requires a few lines of code in the app itself (creating the mutex) but gives Setup a much more reliable "is my target app running" signal than file-lock detection alone.

**Caveats to note explicitly in the spec:**
- Because the updater code that *launches* `Setup.exe` is itself part of the running app's process, the cleanest and most reliable sequence is: the app finishes downloading and verifying the new installer, then **launches `Setup.exe` as a detached/independent process and immediately exits itself**, rather than relying on `CLOSEAPPLICATIONS`/Restart Manager to kill its own parent process out from under it. Restart Manager + `AppMutex` should be treated as a safety net for edge cases (e.g., a second stray instance of the app, or a crashed instance that didn't clean up), not the primary mechanism.
- `/SUPPRESSMSGBOXES` does not suppress every dialog — a handful of critical error types still surface UI even in very-silent mode, so the calling code should still treat "installer process exit code" and the `/LOG` file as the authoritative success/failure signal, not "no visible window appeared."
- If the installer is code-signed and/or the user has UAC enabled, launching `Setup.exe` may still trigger a UAC elevation prompt unless the parent app is already elevated or the installer is set up to auto-elevate; this is worth flagging for the actual implementation spec even though Inno Setup's docs don't eliminate it via a command-line switch — it's inherent to running any admin-installing setup on Windows with UAC on.

---

## 3. GitHub Releases API specifics

**CONFIRMED**, source: [docs.github.com — REST API rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api) and [docs.github.com — REST API Releases reference](https://docs.github.com/en/rest/releases/releases) / [Release assets reference](https://docs.github.com/en/rest/releases/assets), checked 2026-08-17.

- **Unauthenticated rate limit:** 60 requests/hour, tracked per originating IP address. Authenticated requests (e.g. with a personal access token or `GITHUB_TOKEN`) get 5,000 requests/hour — roughly 83x higher. For a once-a-day (or even once-an-hour) update check from each end-user machine, the unauthenticated 60/hour limit is not a practical constraint (one check = one request), but it's worth not hammering the endpoint on every app launch in a tight loop, and worth handling HTTP 403/429 rate-limit responses gracefully (treat as "check failed, try again later," never as fatal).
- **Latest release endpoint:** `GET https://api.github.com/repos/{owner}/{repo}/releases/latest` — "View the latest published full release for the repository." For this project: `GET https://api.github.com/repos/errored-app/dibycap-solver-farmsync/releases/latest`. Note: this endpoint returns the most recent *non-prerelease, non-draft* release by creation time, so marking a release as a GitHub "pre-release" is the mechanism to ship a build without triggering auto-update.
- **Downloading a specific named asset:** the `releases/latest` (or `releases/{release_id}`) response includes an `assets` array; each asset object has a `name` (the filename, e.g. `Setup.exe`), a `content_type`, and a `browser_download_url` — a stable, directly-fetchable HTTPS URL requiring no auth for a public repo. The updater code should locate the asset by matching `name` (e.g. exact match or a pattern like `*Setup.exe`) rather than assuming array order, since asset ordering isn't guaranteed by contract.
- Per-asset endpoints also exist (`GET /repos/{owner}/{repo}/releases/assets/{asset_id}`, `GET /repos/{owner}/{repo}/releases/{release_id}/assets`) but for this use case the `assets` array embedded in the `releases/latest` response is sufficient — no extra request needed.

---

## 4. Version detection in a frozen app

**Two distinct, unrelated concerns** — conflating them is a common mistake:

### (a) The value your Python code compares against the GitHub release tag
**CONFIRMED reasoning from PyInstaller's own docs**, source: [pyinstaller.org — Runtime Information](https://pyinstaller.org/en/stable/runtime-information.html), checked 2026-08-17. PyInstaller's runtime docs describe how a frozen app detects it's running under the bootloader (`getattr(sys, 'frozen', False)` plus `sys._MEIPASS` for locating bundled resources) but say nothing about version numbers — versioning your *application logic* is explicitly outside PyInstaller's scope; it only concerns itself with freezing and Windows exe metadata.
Relying on `importlib.metadata.version(...)` (Python package metadata) is fragile once frozen: PyInstaller does not automatically preserve installed-package `dist-info`/`egg-info` metadata inside the bundle unless you explicitly collect it (via `--copy-metadata`), so a call that works fine from source (`pip install -e .` environment) can raise `PackageNotFoundError` in the frozen build unless that metadata is deliberately included. This is an easy, silent breakage point.
**Recommendation:** define `__version__ = "1.4.2"` (or similar) as a plain constant in a small, dependency-free module (e.g. `_version.py`) that's imported directly — not derived from installed package metadata — and have the build process (or a pre-build script) keep that string in sync with the Git tag / release version used to cut the GitHub Release. This value is what the updater compares to the tag from `releases/latest`.

### (b) The Windows Explorer-visible "Properties → Details" version on the `.exe` itself
**CONFIRMED**, source: [pyinstaller.org — Using PyInstaller, `--version-file` option](https://pyinstaller.org/en/stable/usage.html), checked 2026-08-17. PyInstaller supports `--version-file FILE` to "add a version resource from FILE to the exe" — a Windows `VS_VERSIONINFO` resource with `FileVersion`/`ProductVersion` fields (each a 4-element tuple) plus string fields (company name, product name, etc.). PyInstaller ships two companion CLI utilities: `pyi-grab_version <exe>` extracts an existing exe's version resource into an editable text template, and `pyi-set_version <version_text_file> <exe>` writes a version resource into an already-built exe. This is purely cosmetic/OS-level metadata (what a user sees right-clicking the .exe → Properties) and is unrelated to the update-check comparison logic in (a) — though the spec should keep both numbers in sync at build time for consistency, since a mismatch (e.g. Explorer says 1.3.0, the app's own "About" says 1.4.2) would confuse a non-technical user troubleshooting via right-click Properties.

---

## 5. UX for a non-technical user

Recommendation for **this specific target user** (non-technical, Windows-only, running a console app): **background silent check, minimal-friction install, no technical choices offered.**

Reasoning:
- A non-technical user cannot meaningfully evaluate an "update available — install now?" Y/N prompt (what would they weigh it against?), and an ignorable prompt risks the user permanently dismissing/avoiding updates, leaving them stuck on old, possibly-broken versions (this is a known real-world failure mode for consumer auto-updaters generally — UNVERIFIED as a cited stat, but a very standard UX rationale, noting explicitly here that this specific claim is reasoning/design judgment rather than a primary-sourced fact).
- Fully silent with **zero** visible feedback is also risky for this audience: if the update silently fails (no internet, blocked firewall, antivirus quarantining the download) the user has no way to know something's wrong, and will just report "the app is broken" or "it's not doing the thing the new version does" with no diagnostic trail.
- Therefore: check on startup (and/or a low-frequency background timer, e.g. once every 24h) with **no UI at all** if no update is found. If an update *is* found: show a small, simple, non-blocking notice — e.g. "A new version is available and will be installed now." — with a **download progress bar** (so the user sees the app is doing something rather than appearing frozen/hung, especially since a console window with a spinning progress indicator is a familiar-enough pattern even to non-technical users), then automatically launch the installer and exit the app. On next launch, the user is on the new version with no action required.
- Restart handling: use `/NORESTART` in the Inno Setup invocation (Section 2) so the update never triggers an unprompted Windows reboot — the *application* restarting (relaunching the frozen exe after install) is fine and expected, but the *machine* rebooting is a much bigger, scarier surprise for this audience and should never happen without explicit, separate user consent.
- If the check itself fails (no connectivity, GitHub unreachable, rate-limited) the correct UX is: do nothing, show nothing, let the app continue running normally on its current version — never block app startup or usage on the update check succeeding.

---

## 6. Failure handling

- **No internet during check/download:** the update check must be non-blocking and fail silently from the user's perspective — wrap the HTTP calls in a short timeout, catch connection errors, and simply skip the update this cycle; the app must always remain fully usable on its current installed version regardless of network state. This is a design requirement, not something documented by GitHub or PyInstaller (UNVERIFIED as a "spec," it's an implementation recommendation).
- **Half-downloaded/corrupt file:** always download to a temporary filename (e.g. `Setup.exe.download` or a temp-dir path) and only rename it to the final name the installer is launched from *after* the download completes fully and passes verification (size check at minimum, hash check ideally — see next point). Never launch a partially-written file. This atomic-rename pattern (write to temp name, verify, then rename into place) is a standard, well-established file-integrity pattern; it is not something GitHub's or Inno Setup's docs specify since it happens entirely on the client before the installer is ever invoked (UNVERIFIED against a specific primary source — this is general software-engineering practice, cited here as design guidance rather than a documented API/tool behavior).
- **Checksum/hash verification:** **CONFIRMED that GitHub does not generate or publish checksums for release assets automatically** — the Releases API asset object (per `docs.github.com/en/rest/releases/assets`, checked 2026-08-17) exposes `name`, `size`, `content_type`, `browser_download_url`, and similar metadata fields, but no hash/digest field. Therefore, checksum verification requires the release process itself to **publish a checksum file (e.g. `Setup.exe.sha256`) as a second asset in the same GitHub Release**, computed at build time, and have the updater download that small file first, then verify the downloaded `Setup.exe`'s SHA-256 against it before ever executing it. This also mitigates against (rare but real) partial-download corruption independent of TLS's own integrity guarantees.
- **Guaranteeing the update process cannot brick the app:**
  - The **existing installed application is never touched** by the updater's own code — no files are deleted, moved, or modified by the update-check/download logic itself. The *only* thing that modifies the existing install is Inno Setup's own installer, which is a separate, battle-tested, already-installed-on-the-user's-machine executable with its own robust file-replacement logic.
  - Inno Setup's install process itself is effectively transactional at the file level: it stages/writes new files via its own internal mechanism and only proceeds to update the Start Menu/registry/uninstall entries after files are in place; if Setup itself fails partway (disk full, permissions, an antivirus block), the previous version's files that weren't yet touched remain functional, and Inno Setup surfaces a failure exit code plus (with `/LOG`) a diagnostic log — but this is normal Inno Setup installer behavior generally, not something the linked `setupcmdline` docs assert as a formal "transactional guarantee" (UNVERIFIED as an explicit atomicity claim from jrsoftware.org — Inno Setup's docs describe the switches and directives but do not make a formal ACID-style promise about the underlying file-replace mechanism; treat this as reasonably-well-established behavior of a mature installer, not a documented guarantee).
  - Because of the above, the failure mode of the *entire pipeline* — network failure, corrupt download, checksum mismatch, or installer launch failure — should always resolve to "the currently running/installed version keeps working, nothing was modified, try again next check," never to a state where the old app is partially removed/broken while a new one only partially installed. This is achieved purely by sequencing: verify fully before ever invoking `Setup.exe`, and let `Setup.exe`'s own well-tested logic own the actual file replacement once invoked.
  - Recommendation for the spec: log every stage (check, download, hash-verify, launch) to a small local log file, so a failed silent update is diagnosable after the fact without needing the non-technical user to reproduce or describe what happened.

---

## Sources consulted

- Inno Setup — [Setup Command Line Parameters](https://jrsoftware.org/ishelp/topic_setupcmdline.htm), checked 2026-08-17
- Inno Setup — [`[Setup]` section: `CloseApplications`](https://jrsoftware.org/ishelp/topic_setup_closeapplications.htm), checked 2026-08-17
- Inno Setup — [`[Setup]` section: `AppMutex`](https://jrsoftware.org/ishelp/topic_setup_appmutex.htm), checked 2026-08-17
- Inno Setup — [isinfo.php](https://jrsoftware.org/isinfo.php) (general product reference)
- GitHub REST API — [Releases reference](https://docs.github.com/en/rest/releases/releases), checked 2026-08-17
- GitHub REST API — [Release assets reference](https://docs.github.com/en/rest/releases/assets), checked 2026-08-17
- GitHub REST API — [Rate limits for the REST API](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api), checked 2026-08-17
- PyInstaller — [Runtime Information](https://pyinstaller.org/en/stable/runtime-information.html), checked 2026-08-17
- PyInstaller — [Using PyInstaller (`--version-file`, `pyi-grab_version`, `pyi-set_version`)](https://pyinstaller.org/en/stable/usage.html), checked 2026-08-17
- GitHub repo activity via `gh api`, checked 2026-08-17: `Digital-Sapphire/PyUpdater`, `vslavik/winsparkle`, `dyer234/pywinsparkle`, `dennisvang/tufup`
- PyPI — [pywinsparkle project page](https://pypi.org/project/pywinsparkle/1.1.0/) (secondary source, used only to corroborate the binding is a thin/static wrapper — repo activity data above is the primary evidence for its abandonment)
