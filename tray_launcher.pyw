"""Tray Launcher — a Windows system-tray menu of quick-launch shortcuts to .bat files.

Config-driven (config.json next to this file). Each item launches a .bat (or any
command); console items open a visible cmd window, hidden items run with no window.
Anything launched is tracked and can be stopped from the "Running" submenu.

Run with:  pythonw tray_launcher.pyw   (no console of its own)
"""

import ctypes
import json
import os
import subprocess
import sys
import threading

from PIL import Image, ImageDraw
import pystray


# --- Left-click opens the menu (same panel as right-click) -----------------
# The Windows backend maps left-click to the default menu item and only shows
# the popup on right-click. Remap left-button-up to right-button-up so a normal
# click opens the full menu. Wrapped defensively: if pystray's internals change,
# it silently falls back to default behaviour.
def _patch_left_click_opens_menu():
    try:
        from pystray._win32 import Icon as _Win32Icon
        from pystray._util import win32 as _pswin32

        _orig_on_notify = _Win32Icon._on_notify

        def _on_notify(self, wparam, lparam):
            if lparam == _pswin32.WM_LBUTTONUP:
                lparam = _pswin32.WM_RBUTTONUP
            return _orig_on_notify(self, wparam, lparam)

        _Win32Icon._on_notify = _on_notify
    except Exception:
        pass


_patch_left_click_opens_menu()

# --- Windows process-creation flags ---------------------------------------
CREATE_NEW_CONSOLE = 0x00000010   # visible cmd window that closes when the bat ends
CREATE_NO_WINDOW = 0x08000000     # no window at all (background)

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
EXAMPLE_PATH = os.path.join(APP_DIR, "config.example.json")
AUTOSTART_PATH = os.path.join(APP_DIR, "autostart.json")
APP_NAME = "Tray Launcher"
STARTUP_LNK_NAME = "Tray Launcher.lnk"

# label -> {"proc": Popen | None, "pid": int}  for tracked launches
_running = {}
_running_lock = threading.Lock()


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------
def load_config():
    """Return the parsed config dict, creating config.json from the example on first run."""
    if not os.path.exists(CONFIG_PATH):
        if os.path.exists(EXAMPLE_PATH):
            with open(EXAMPLE_PATH, "r", encoding="utf-8") as f:
                data = f.read()
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                f.write(data)
        else:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump({"title": APP_NAME, "items": []}, f, indent=2)
        # open it so the user can start editing right away
        try:
            os.startfile(CONFIG_PATH)  # noqa: S606
        except Exception:
            pass
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        _notify(f"Could not read config.json:\n{exc}")
        return {"title": APP_NAME, "items": []}


# --------------------------------------------------------------------------
# Per-app autostart (which items launch together with the tray)
# --------------------------------------------------------------------------
def _load_autostart():
    """Set of labels marked to auto-launch with the tray. Missing/broken file -> empty set."""
    try:
        with open(AUTOSTART_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return set(data) if isinstance(data, list) else set()
    except Exception:
        return set()


def _save_autostart(labels):
    try:
        with open(AUTOSTART_PATH, "w", encoding="utf-8") as f:
            json.dump(sorted(labels), f, indent=2)
    except Exception as exc:
        _notify(f"Could not save autostart list:\n{exc}")


def is_autostart_item(label):
    return label in _load_autostart()


def toggle_autostart_item(label):
    labels = _load_autostart()
    labels.discard(label) if label in labels else labels.add(label)
    _save_autostart(labels)


# --------------------------------------------------------------------------
# Launching / stopping
# --------------------------------------------------------------------------
def _enable_dark_menus():
    """Let the native tray menu follow the OS light/dark theme (Win10 1903+/Win11).

    pystray shows a classic Win32 popup menu, which stays light by default. The
    undocumented uxtheme APIs SetPreferredAppMode(AllowDark) + FlushMenuThemes opt
    the app into dark mode; AllowDark makes menus track the system setting, so a
    dark OS gives a dark menu with no polling. Fully defensive: on any older build
    where the ordinals differ or the call fails, the menu just stays light.
    """
    try:
        uxtheme = ctypes.WinDLL("uxtheme.dll")
        set_preferred_app_mode = uxtheme[135]  # SetPreferredAppMode(PreferredAppMode)
        set_preferred_app_mode.restype = ctypes.c_int
        set_preferred_app_mode.argtypes = [ctypes.c_int]
        set_preferred_app_mode(1)  # AllowDark = follow the OS theme (2 = force dark)

        flush_menu_themes = uxtheme[136]  # FlushMenuThemes()
        flush_menu_themes.restype = None
        flush_menu_themes.argtypes = []
        flush_menu_themes()
    except Exception:
        pass


def _child_env():
    """Environment for launched processes, matching a normal double-click.

    Strips NoDefaultCurrentDirectoryInExePath: when that variable is present cmd
    excludes the current directory from command resolution, so a .bat that does a
    bare relative `call other.bat` (e.g. A1111's webui-user.bat → `call webui.bat`)
    fails to find its sibling and the console closes instantly. Explorer launches
    bats without this variable; removing it here reproduces that behaviour.
    """
    return {
        k: v
        for k, v in os.environ.items()
        if k.lower() != "nodefaultcurrentdirectoryinexepath"
    }


def _notify(message, title=APP_NAME):
    """Non-blocking-ish message box (runs in its own thread so the tray stays alive)."""
    def _show():
        ctypes.windll.user32.MessageBoxW(0, str(message), title, 0x40)  # MB_ICONINFORMATION
    threading.Thread(target=_show, daemon=True).start()


def _prune():
    """Drop finished processes from the running table."""
    with _running_lock:
        for key in list(_running.keys()):
            entry = _running[key]
            proc = entry.get("proc")
            if proc is not None and proc.poll() is not None:
                del _running[key]


def _track_key(label):
    """A unique menu key for a launch (allows the same label to run more than once)."""
    base = label
    n = 2
    with _running_lock:
        key = base
        while key in _running:
            key = f"{base} ({n})"
            n += 1
        _running[key] = {"proc": None, "pid": None}
    return key


def launch(item):
    """Launch a config item. Returns nothing; errors are surfaced via a message box."""
    path = item.get("path")
    if not path:
        _notify(f"Item '{item.get('label', '?')}' has no 'path'.")
        return

    path = os.path.expandvars(os.path.expanduser(path))
    if not os.path.isabs(path):
        path = os.path.join(APP_DIR, path)  # relative paths resolve next to this app
    if not os.path.exists(path):
        _notify(f"Path not found:\n{path}")
        return

    args = item.get("args") or []
    if isinstance(args, str):
        args = [args]
    cwd = item.get("cwd")
    if cwd:
        cwd = os.path.expandvars(os.path.expanduser(cwd))
    else:
        cwd = os.path.dirname(path) or None
    mode = (item.get("mode") or "console").lower()
    label = item.get("label") or os.path.basename(path)

    # Elevated launch: can't track the PID (a new elevated process is spawned by the shell)
    if item.get("admin"):
        try:
            params = " ".join(f'"{a}"' for a in args)
            ctypes.windll.shell32.ShellExecuteW(None, "runas", path, params, cwd, 1)
        except Exception as exc:
            _notify(f"Could not launch (admin) '{label}':\n{exc}")
        return

    flags = CREATE_NO_WINDOW if mode == "hidden" else CREATE_NEW_CONSOLE
    key = _track_key(label)
    try:
        proc = subprocess.Popen([path, *args], cwd=cwd, creationflags=flags, env=_child_env())
        with _running_lock:
            _running[key] = {"proc": proc, "pid": proc.pid}
    except Exception as exc:
        with _running_lock:
            _running.pop(key, None)
        _notify(f"Could not launch '{label}':\n{exc}")


def stop(key):
    """Kill a tracked process (and its whole child tree — bats spawn children)."""
    with _running_lock:
        entry = _running.get(key)
    if not entry:
        return
    pid = entry.get("pid")
    if pid:
        try:
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(pid)],
                creationflags=CREATE_NO_WINDOW,
                capture_output=True,
            )
        except Exception:
            pass
    with _running_lock:
        _running.pop(key, None)


def stop_all():
    with _running_lock:
        keys = list(_running.keys())
    for key in keys:
        stop(key)


def restart(icon):
    """Relaunch the tray from disk (picks up code/config changes) and quit this one."""
    DETACHED_PROCESS = 0x00000008
    script = os.path.join(APP_DIR, "tray_launcher.pyw")
    try:
        subprocess.Popen(
            [_pythonw(), script, "--no-autostart"],
            cwd=APP_DIR,
            creationflags=DETACHED_PROCESS,
            close_fds=True,
        )
    except Exception as exc:
        _notify(f"Could not restart:\n{exc}")
        return
    icon.stop()


# --------------------------------------------------------------------------
# Startup shortcut ("Start with Windows")
# --------------------------------------------------------------------------
def _startup_dir():
    return os.path.join(
        os.environ["APPDATA"],
        r"Microsoft\Windows\Start Menu\Programs\Startup",
    )


def _startup_lnk_path():
    return os.path.join(_startup_dir(), STARTUP_LNK_NAME)


def _pythonw():
    """Path to pythonw.exe for the interpreter running this script."""
    exe = sys.executable
    base = os.path.basename(exe).lower()
    if base == "python.exe":
        cand = os.path.join(os.path.dirname(exe), "pythonw.exe")
        if os.path.exists(cand):
            return cand
    return exe


def is_startup_enabled():
    return os.path.exists(_startup_lnk_path())


def toggle_startup():
    lnk = _startup_lnk_path()
    if os.path.exists(lnk):
        try:
            os.remove(lnk)
        except Exception as exc:
            _notify(f"Could not disable autostart:\n{exc}")
        return

    script = os.path.join(APP_DIR, "tray_launcher.pyw")
    target = _pythonw()
    ico = os.path.join(APP_DIR, "app.ico")
    icon_line = f"$s.IconLocation = '{ico}'; " if os.path.exists(ico) else ""
    ps = (
        "$ws = New-Object -ComObject WScript.Shell; "
        f"$s = $ws.CreateShortcut('{lnk}'); "
        f"$s.TargetPath = '{target}'; "
        f"$s.Arguments = '\"{script}\"'; "
        f"$s.WorkingDirectory = '{APP_DIR}'; "
        f"$s.WindowStyle = 7; "
        f"$s.Description = '{APP_NAME}'; "
        f"{icon_line}"
        "$s.Save()"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            creationflags=CREATE_NO_WINDOW,
            capture_output=True,
            check=True,
        )
    except Exception as exc:
        _notify(f"Could not enable autostart:\n{exc}")


# --------------------------------------------------------------------------
# Icon
# --------------------------------------------------------------------------
def make_icon():
    """Load the TRY Launcher emblem (tray_icon.png / app.ico), else draw a fallback."""
    for name in ("tray_icon.png", "app.ico", "logo.png"):
        path = os.path.join(APP_DIR, name)
        if os.path.exists(path):
            try:
                return Image.open(path).convert("RGBA")
            except Exception:
                pass
    # Fallback: a simple bolt tile drawn in code.
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([4, 4, size - 4, size - 4], radius=12, fill=(20, 20, 20, 255))
    d.rounded_rectangle([4, 4, size - 4, size - 4], radius=12, outline=(245, 158, 11, 255), width=4)
    bolt = [(38, 10), (20, 36), (30, 36), (24, 54), (46, 26), (34, 26)]
    d.polygon(bolt, fill=(255, 255, 255, 255))
    return img


# --------------------------------------------------------------------------
# Menu
# --------------------------------------------------------------------------
def _iter_launchable(entries):
    """Yield launchable item dicts recursively (descends submenus; skips separators)."""
    for entry in entries or []:
        if not isinstance(entry, dict) or entry.get("separator"):
            continue
        if entry.get("submenu"):
            yield from _iter_launchable(entry["submenu"])
        else:
            yield entry


def _autostart(cfg):
    """Launch every item whose label is in autostart.json (once, at real startup)."""
    labels = _load_autostart()
    if not labels:
        return
    for entry in _iter_launchable(cfg.get("items", [])):
        if (entry.get("label") or "") in labels:
            launch(entry)


def _build_config_items(entries):
    """Turn config 'items' (list of dicts) into pystray menu items, recursively."""
    menu_items = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("separator"):
            menu_items.append(pystray.Menu.SEPARATOR)
            continue
        label = entry.get("label", "(unnamed)")
        submenu = entry.get("submenu")
        if submenu:
            menu_items.append(
                pystray.MenuItem(label, pystray.Menu(*_build_config_items(submenu)))
            )
        else:
            # bind the entry to the click handler
            menu_items.append(
                pystray.MenuItem(label, (lambda e: lambda icon, item: launch(e))(entry))
            )
    return menu_items


def _running_submenu():
    _prune()
    with _running_lock:
        keys = list(_running.keys())
    items = []
    for key in keys:
        items.append(
            pystray.MenuItem(key, (lambda k: lambda icon, item: stop(k))(key))
        )
    if items:
        items.append(pystray.Menu.SEPARATOR)
        items.append(pystray.MenuItem("Stop all", lambda icon, item: stop_all()))
    return items


def _startup_submenu(cfg):
    """The launcher's own autostart toggle + a checkbox per app for autostart."""
    items = [
        pystray.MenuItem(
            "TRY Launcher (this app)",
            lambda icon, item: toggle_startup(),
            checked=lambda item: is_startup_enabled(),
        ),
        pystray.Menu.SEPARATOR,
    ]
    for entry in _iter_launchable(cfg.get("items", [])):
        label = entry.get("label") or "(unnamed)"
        items.append(
            pystray.MenuItem(
                label,
                (lambda l: lambda icon, item: toggle_autostart_item(l))(label),
                checked=(lambda l: lambda item: is_autostart_item(l))(label),
            )
        )
    return items


def build_menu():
    def menu_factory():
        cfg = load_config()
        items = list(_build_config_items(cfg.get("items", [])))

        items.append(pystray.Menu.SEPARATOR)

        # Running submenu — only visible when something is live
        _prune()
        with _running_lock:
            has_running = bool(_running)
        items.append(
            pystray.MenuItem(
                "Running",
                pystray.Menu(*_running_submenu()),
                visible=has_running,
            )
        )
        items.append(pystray.Menu.SEPARATOR)

        items.append(
            pystray.MenuItem(
                "Start with Windows", pystray.Menu(*_startup_submenu(cfg))
            )
        )
        items.append(pystray.MenuItem("Reload config", lambda icon, item: icon.update_menu()))
        items.append(pystray.MenuItem("Restart", lambda icon, item: restart(icon)))
        items.append(
            pystray.MenuItem("Edit config", lambda icon, item: os.startfile(CONFIG_PATH))
        )
        items.append(
            pystray.MenuItem("Open app folder", lambda icon, item: os.startfile(APP_DIR))
        )
        items.append(pystray.MenuItem("Quit", lambda icon, item: icon.stop()))
        return items

    return pystray.Menu(menu_factory)


def main():
    _enable_dark_menus()
    cfg = load_config()
    if "--no-autostart" not in sys.argv:
        _autostart(cfg)
    title = cfg.get("title", APP_NAME)
    icon = pystray.Icon(APP_NAME, icon=make_icon(), title=title, menu=build_menu())
    icon.run()


if __name__ == "__main__":
    main()
