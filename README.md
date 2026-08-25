<div align="center">

<img src="logo.png" alt="TRAY Launcher" width="200" />

# TRAY Launcher

**A tiny, no-nonsense Windows tray menu for all your favorite `.bat` files.**

Pin every script you actually use — VPN tunnels, dev servers, text-to-speech, one-off tools —
to a single click in your system tray. Launch them visible or silent, and **stop any of them**
right from the menu.

<br />

![Python](https://img.shields.io/badge/Python-3.8%2B-3776AB?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows-0078D6?logo=windows&logoColor=white)
![Dependencies](https://img.shields.io/badge/deps-pystray%20%2B%20Pillow-F59E0B)
![License](https://img.shields.io/badge/License-MIT-F59E0B)
![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen)
![Stars](https://img.shields.io/github/stars/juanpe500/tray-launcher?style=social)

</div>

---

## Why

Your handy `.bat` files are scattered across a dozen folders. You `cd`, you double-click, you
lose the window, you can't remember which one starts the VPN. **TRY Launcher** turns that mess
into one always-there tray icon with a clean, editable menu — driven by a single JSON file.

- 🪶 **Minimal** — two dependencies (`pystray` + `Pillow`), one small script. No installer, no service, no admin required.
- ⚙️ **Config-driven** — your menu is a plain `config.json`. Add, rename, group, reorder in seconds.
- 🖥️ **Visible or silent** — each item runs in its own console window *or* fully hidden in the background.
- ⏹️ **Actually stoppable** — every launched task (console **and** hidden) shows up under **Running ▸** so you can kill it — process tree and all — without hunting in Task Manager.
- 🚀 **Start with Windows** — a one-click toggle in the menu. Off by default.
- 🎨 **Yours** — drop in your own `logo.png`, run one script, and the tray + shortcut icons rebrand instantly.

---

## Quick start

> **Requirements:** Windows 10/11 and Python 3.8+ ([python.org](https://www.python.org/downloads/)).

```powershell
# 1. Clone
git clone https://github.com/juanpe500/tray-launcher.git
cd tray-launcher

# 2. Create an isolated environment + install deps
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 3. Run it (no console window; icon appears in your tray)
.\.venv\Scripts\pythonw.exe tray_launcher.pyw
```

Or just **double-click `Tray Launcher.bat`** — it uses the local `.venv` automatically (falling
back to a system `pythonw`).

On first run, if you don't have a `config.json` yet, one is created for you from
`config.example.json` and opened in your editor. It ships with a working **Self-test** entry, so
you can try launch/stop immediately — then replace it with your own scripts.

---

## Configure your menu

Everything lives in **`config.json`** (create it by copying `config.example.json`, or let the
app create it on first run). Edit it, then click **Reload config** in the tray — no restart.

```jsonc
{
  "title": "TRAY Launcher",
  "items": [
    { "label": "Start VPN", "path": "C:\\bats\\vpn.bat", "mode": "hidden", "admin": true },
    { "label": "Dev server", "path": "C:\\proj\\run.bat", "mode": "console", "args": ["--port", "8080"] },
    { "separator": true },
    {
      "label": "Media",
      "submenu": [
        { "label": "Text-to-Speech daemon", "path": "C:\\tts\\run.bat", "mode": "console" },
        { "label": "Background sync",        "path": "C:\\sync\\sync.bat", "mode": "hidden" }
      ]
    }
  ]
}
```

### Item fields

| Field | Required | Description |
|---|:---:|---|
| `label` | ✅ | Text shown in the menu. |
| `path` | ✅ | Path to a `.bat` / `.cmd` / `.exe` / any command. Absolute, or **relative to the app folder**. `%ENV_VARS%` and `~` are expanded. |
| `mode` | — | `"console"` (visible window, **default**) or `"hidden"` (no window). Both are stoppable. |
| `args` | — | List of arguments, e.g. `["--port", "8080"]`. |
| `cwd` | — | Working directory. Defaults to the folder containing `path`. |
| `admin` | — | `true` launches elevated (UAC prompt). ⚠️ Elevated tasks can't be stopped from the menu. |
| `separator` | — | `{ "separator": true }` draws a divider line. |
| `submenu` | — | `{ "label": "Group", "submenu": [ ...items ] }` nests a group. |

---

## The menu

| Entry | What it does |
|---|---|
| *your items* | Launch the configured script. |
| **Running ▸** | Appears only when something is live. Lists each running task with **Stop**, plus **Stop all**. Stopping kills the whole process tree (`taskkill /T /F`). |
| **Start with Windows** | Checkbox. Adds/removes a shortcut in your Startup folder. Off by default. |
| **Reload config** | Re-reads `config.json` — pick up your edits without restarting. |
| **Edit config** | Opens `config.json` in your default editor. |
| **Open app folder** | Opens the install folder in Explorer. |
| **Quit** | Exits the tray app. Already-running tasks are **left alive** (so your VPN keeps running). |

---

## Make it your own

The tray and shortcut icons are generated from **`logo.png`**. To rebrand:

```powershell
# Replace logo.png with your square logo, then:
.\.venv\Scripts\python.exe make_icons.py
```

`make_icons.py` auto-crops the emblem, keeps it on its tile so light marks stay legible, rounds
the corners, and writes `tray_icon.png` (tray) and `app.ico` (shortcuts). Restart the app to see it.

---

## How it works

- **[`pystray`](https://github.com/moses-palmer/pystray)** draws the tray icon and a menu that's
  rebuilt every time you open it — that's how *Reload config* and the live *Running* list stay current.
- Tasks are launched with `subprocess.Popen` so the app holds each PID:
  - `console` → `CREATE_NEW_CONSOLE` (its own window),
  - `hidden` → `CREATE_NO_WINDOW` (no window).
- Stopping runs `taskkill /T /F /PID <pid>` to take down the `.bat` and every child it spawned.
- **Start with Windows** writes a `.lnk` into your Startup folder via `WScript.Shell` — no extra
  dependency, no registry edits.

Everything is in one readable file: **`tray_launcher.pyw`** (~250 lines).

---

## Project structure

```
tray-launcher/
├─ tray_launcher.pyw     # the app (run with pythonw)
├─ config.example.json   # documented sample menu
├─ config.json           # YOUR menu (git-ignored, created on first run)
├─ make_icons.py         # regenerate tray_icon.png + app.ico from logo.png
├─ logo.png              # brand logo (source for the icons)
├─ tray_icon.png         # tray emblem (generated)
├─ app.ico               # multi-size icon for shortcuts (generated)
├─ selftest.bat          # a harmless looping script for testing launch/stop
├─ Tray Launcher.bat     # one-click launcher (uses the local .venv)
└─ requirements.txt
```

> Your personal `config.json` is **git-ignored** — only `config.example.json` is tracked, so your
> real paths never leave your machine.

---

## FAQ

**Does it need admin rights?** No. Only items marked `"admin": true` prompt for elevation.

**Global hotkey daemon won't fire?** Some background tools need elevation for global hooks — set
`"admin": true` on that item (note: it then can't be stopped from the menu).

**Can `path` point at an `.exe` or a `.ps1`?** Any launchable path works. For PowerShell scripts,
point `path` at `powershell.exe` and pass the script via `args`.

**Where's the config stored?** Right next to the app, as `config.json`.

---

## Contributing

Issues and PRs are welcome. The code is intentionally small and dependency-light — please keep it
that way. Formatting/linting is [Ruff](https://github.com/astral-sh/ruff) (line length 100).

## License

[MIT](LICENSE) — do whatever you like.
