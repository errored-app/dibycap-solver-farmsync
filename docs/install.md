# Installing FarmsyncSolver

## First install

1. Download `FarmsyncSolver-Setup-<version>.exe` from the Releases page.
2. Double-click it.
3. Windows shows a blue box: **"Windows protected your PC"**. This is expected.
   The app is not signed with a paid certificate, so Windows does not know it yet.
   - Click **More info**.
   - Click **Run anyway**.
4. Click through the installer. It asks for no administrator password.
5. Open **FarmsyncSolver** from the Start menu, or from the desktop shortcut.

The app installs for your Windows user only, in
`%LOCALAPPDATA%\Programs\FarmsyncSolver`.

The installer also installs the **Microsoft Edge WebView2 Runtime**, but only if
your PC does not have it. The app draws its window with it. Without it, the
window opens white and empty.

The runtime is carried inside the installer, so this step needs no internet and
takes about a minute. This is why the download is around 250 MB.

## Updates

The app keeps itself up to date. You do nothing.

- Each time it opens, it looks for a newer version. If there is none, you see
  nothing at all.
- If there is one, a bar appears across the top of the Home screen: **"Version
  X is ready."** with an **Update now** button. It is not a pop-up. It waits
  until you press it.
- Press **Update now**. The app downloads the new version, checks it, closes
  itself, and installs. Then open it again from the Start menu.
- You can also look at any time: **Settings -> Check for updates**.

Three rules:

- **Not during a run.** Stop the run first. The button is greyed out until you
  do.
- **Your keys stay.** An update never asks you to type them again.
- **A failed update changes nothing.** No internet, or a bad download, and the
  app keeps working as before. Try again later.

The blue box is not shown again after the first install.

## One copy at a time

Only one FarmsyncSolver can run. If you start it a second time, nothing opens.
The first copy is still running. This is on purpose: two copies would both spend
solves on the same accounts.

## Uninstall

Uninstall from **Settings → Apps**, or from the Start menu folder.

The uninstaller asks: **"Also delete your saved keys and logs?"**

- **No** (the default) keeps your keys. You do not type them again if you
  install the app later.
- **Yes** deletes the folder `%APPDATA%\FarmsyncSolver`, with your keys and your
  logs in it.
