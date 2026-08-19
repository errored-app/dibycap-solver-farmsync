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

## Updates

The app updates itself. Updates are silent. The blue box is not shown again.

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
