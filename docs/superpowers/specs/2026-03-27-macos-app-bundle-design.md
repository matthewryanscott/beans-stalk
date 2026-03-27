# Beans Stalk — macOS .app Bundle Design

**Date:** 2026-03-27
**Status:** Approved

## Goal

Bundle Beans Stalk as `Beans Stalk.app` so it can run as a long-running macOS app from the dock. The `stalk` CLI becomes a thin client that launches the `.app` if needed and sends paths over the existing Unix domain socket IPC.

## Constraints

- Personal use only (no signing, notarization, or embedded runtime)
- Minimal shell `.app` bundle — no py2app or similar tooling
- `.app` lives in the repo at `dist/Beans Stalk.app/`
- Placeholder icon at `resources/icon.png` for later replacement

## .app Bundle Structure

```
dist/Beans Stalk.app/
  Contents/
    Info.plist
    MacOS/
      beans-stalk       # Shell launcher script (executable)
    Resources/
      icon.icns         # Converted from resources/icon.png
```

### Info.plist

Standard macOS app metadata:
- `CFBundleName`: Beans Stalk
- `CFBundleIdentifier`: com.versafeed.beans-stalk
- `CFBundleIconFile`: icon
- `CFBundleExecutable`: beans-stalk
- `LSUIElement`: false (show in dock)

### Launcher Script (`MacOS/beans-stalk`)

A shell script that:
1. Resolves the project directory (relative to the `.app` location)
2. Activates the uv venv (`.venv/bin/python`)
3. Executes `beans_stalk.app:run_server`

## Build Script

`scripts/build_app.sh` — assembles the `.app` directory. Idempotent.

1. Creates the directory structure under `dist/Beans Stalk.app/Contents/`
2. Writes `Info.plist`
3. Writes the launcher shell script and `chmod +x`
4. Converts `resources/icon.png` → `.icns` using `sips` + `iconutil` (macOS built-ins)
5. Copies `.icns` to `Resources/`

## Code Changes

### `app.py` — Server mode (no initial window)

- Make `initial_beans_dir` parameter optional (`None` = no window on start)
- When running as server: set `setQuitOnLastWindowClosed(False)` so the app stays alive in the dock with zero windows
- Add `run_server()` free function as the `.app` entry point — calls `StalkApp().run(initial_beans_dir=None)`

### `main.py` — Thin client CLI

Remove the `run_app` import/fallback. New flow:

1. Resolve the beans directory path (existing logic)
2. `try_send_to_running_instance(resolved)` → if success, exit 0
3. Server not running → find and launch `.app`:
   - Check paths in order: relative to package (`__file__`), `~/Applications/Beans Stalk.app`, `/Applications/Beans Stalk.app`
   - Launch via `subprocess.run(["open", app_path])`
4. Poll for socket readiness (up to 10s, 100ms intervals)
5. Send path over socket → exit 0
6. If timeout → exit with error

### `pyproject.toml`

Add entry point for the server (used by `.app` launcher):
```toml
stalk-server = "beans_stalk.app:run_server"
```

## Lifecycle

| Action | Behavior |
|---|---|
| Open `.app` from Finder/Dock | Starts headless server in dock, no windows, listens on socket |
| `stalk .` (server running) | Sends path over socket, window opens, CLI exits |
| `stalk .` (server not running) | Launches `.app`, waits for socket, sends path, CLI exits |
| Close all windows | App stays running in dock |
| Quit from dock menu | Shuts down IPC server, cleans up socket |

## Icon

Placeholder 1024x1024 PNG at `resources/icon.png`. Build script converts to `.icns`. Replace the PNG and re-run `scripts/build_app.sh` to update.
