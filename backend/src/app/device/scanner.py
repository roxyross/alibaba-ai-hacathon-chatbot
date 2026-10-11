"""Phase 4: Local Application Discovery Engine.

Deep system scanning, metadata extraction, intelligent categorization,
and running process correlation for Windows, macOS, and Linux.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import socket
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger()

# -----------------------------------------------------------------------------
# Category Taxonomies & Capabilities Mapping
# -----------------------------------------------------------------------------

CATEGORIES: list[str] = [
    "browser",
    "development",
    "productivity",
    "communication",
    "media",
    "utilities",
    "system",
    "gaming",
    "design",
    "finance",
    "security",
    "other",
]

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "browser": [
        "chrome", "chromium", "edge", "msedge", "firefox", "safari",
        "brave", "opera", "vivaldi", "tor browser", "waterfox", "arc",
    ],
    "development": [
        "code", "vscode", "visual studio", "pycharm", "intellij", "idea",
        "webstorm", "clion", "goland", "sublime", "atom", "vim", "nvim",
        "emacs", "terminal", "wt", "powershell", "git", "bash", "docker",
        "postman", "insomnia", "dbeaver", "pgadmin", "android studio",
        "xcode", "cursor", "windsurf", "eclipse", "datagrip",
    ],
    "productivity": [
        "word", "excel", "powerpoint", "office", "libreoffice", "openoffice",
        "notion", "obsidian", "evernote", "onenote", "acrobat", "reader",
        "foxit", "calc", "sheet", "writer", "document", "notes", "todoist",
        "trello", "asana", "clickup", "goodnotes",
    ],
    "communication": [
        "slack", "discord", "teams", "zoom", "skype", "telegram",
        "signal", "whatsapp", "thunderbird", "outlook", "mail",
        "messenger", "mattermost", "element", "wechat",
    ],
    "media": [
        "spotify", "vlc", "itunes", "apple music", "foobar", "winamp",
        "gimp", "photoshop", "premiere", "after effects", "obs",
        "audacity", "handbrake", "media player", "paint", "photos",
        "sound", "music", "video", "potplayer", "mpv",
    ],
    "design": [
        "figma", "blender", "illustrator", "canva", "inkscape",
        "sketch", "affinity", "coreldraw", "lightroom", "invision",
    ],
    "gaming": [
        "steam", "epic games", "battle.net", "origin", "riot",
        "unity", "unreal", "minecraft", "roblox", "gog galaxy",
    ],
    "finance": [
        "quickbooks", "mint", "ledger", "metamask", "tradingview",
        "quicken", "turbotax", "bloomberg",
    ],
    "security": [
        "bitwarden", "1password", "keepass", "malwarebytes", "defender",
        "antivirus", "vpn", "wireguard", "nordvpn", "expressvpn",
        "protonvpn", "tailscale", "zerotier",
    ],
    "system": [
        "taskmgr", "regedit", "systemsettings", "eventvwr", "finder",
        "explorer", "system", "control panel", "services", "device manager",
    ],
    "utilities": [
        "7-zip", "winrar", "everything", "powertoys", "unarchiver",
        "calculator", "notepad", "cleaner", "clipboard", "snagit",
        "greenshot", "rufus", "etcher",
    ],
}

CATEGORY_CAPABILITIES: dict[str, list[str]] = {
    "browser": [
        "web_browsing",
        "tab_navigation",
        "url_dispatch",
        "dom_interaction",
        "cookie_management",
    ],
    "development": [
        "code_editing",
        "project_workspace",
        "terminal_execution",
        "version_control",
        "debugging",
    ],
    "productivity": [
        "document_editing",
        "spreadsheet_calc",
        "content_formatting",
        "export_pdf",
        "note_taking",
    ],
    "communication": [
        "messaging",
        "channels",
        "voice_video_calls",
        "presence_status",
        "notifications",
    ],
    "media": [
        "audio_playback",
        "video_playback",
        "media_transport_controls",
        "playlist_management",
        "volume_control",
    ],
    "design": [
        "vector_graphics",
        "canvas_rendering",
        "layer_compositing",
        "asset_export",
    ],
    "gaming": [
        "game_launching",
        "overlay_support",
        "social_presence",
    ],
    "finance": [
        "financial_tracking",
        "transaction_review",
        "portfolio_overview",
    ],
    "security": [
        "credential_storage",
        "encrypted_vault",
        "secure_tunneling",
    ],
    "system": [
        "process_inspection",
        "hardware_diagnostics",
        "system_configuration",
    ],
    "utilities": [
        "file_operations",
        "quick_calculation",
        "text_scratchpad",
        "archive_extraction",
    ],
    "other": [
        "process_execution",
        "window_management",
    ],
}

CATEGORY_ACTIONS: dict[str, list[str]] = {
    "browser": ["launch", "close", "focus", "open_url", "reload", "navigate_back"],
    "media": ["launch", "close", "focus", "play", "pause", "next_track", "previous_track", "mute"],
    "development": ["launch", "close", "focus", "open_directory", "run_terminal_command"],
    "productivity": ["launch", "close", "focus", "open_file", "save"],
    "communication": ["launch", "close", "focus", "send_message", "mute_notifications"],
    "system": ["launch", "close", "focus", "inspect_metrics"],
    "utilities": ["launch", "close", "focus"],
    "other": ["launch", "close", "focus"],
}


def categorize_app(
    app_name: str,
    executable_path: str = "",
    bundle_id: str | None = None,
    desktop_categories: str | None = None,
) -> str:
    """Intelligently determine application category based on name, path, and descriptors."""
    haystack = f"{app_name} {Path(executable_path).stem} {bundle_id or ''} {desktop_categories or ''}".lower()

    # Match against taxonomy keyword sets in priority order
    for cat in ["browser", "development", "productivity", "communication", "design", "security", "finance", "gaming", "media", "system", "utilities"]:
        for kw in CATEGORY_KEYWORDS[cat]:
            # Exact word boundary matching preferred; only allow substring if kw length >= 4
            if re.search(r"\b" + re.escape(kw) + r"\b", haystack):
                return cat
            if len(kw) >= 4 and kw in haystack:
                return cat

    return "utilities" if any(x in haystack for x in ["tool", "helper", "util"]) else "other"


def infer_capabilities(category: str, app_name: str) -> list[str]:
    """Derive functional capability tags for an application."""
    caps = list(CATEGORY_CAPABILITIES.get(category, CATEGORY_CAPABILITIES["other"]))
    name_lower = app_name.lower()

    if "spotify" in name_lower:
        caps.extend(["media_playback", "playlist_management"])
    elif "chrome" in name_lower or "edge" in name_lower:
        caps.extend(["google_ecosystem", "browser_extensions"])
    elif "code" in name_lower:
        caps.extend(["git_integration", "lsp_support"])

    return list(dict.fromkeys(caps))


def infer_supported_actions(category: str, app_name: str) -> list[str]:
    """Derive supported action verbs for automation dispatch."""
    actions = list(CATEGORY_ACTIONS.get(category, CATEGORY_ACTIONS["other"]))
    name_lower = app_name.lower()

    if any(m in name_lower for m in ["spotify", "music", "vlc"]):
        for act in ["play", "pause", "next_track", "previous_track", "mute"]:
            if act not in actions:
                actions.append(act)

    return actions


# -----------------------------------------------------------------------------
# Native OS Scanners
# -----------------------------------------------------------------------------

def scan_windows_registry() -> list[dict[str, Any]]:
    """Scan Windows Registry uninstall keys for installed desktop software."""
    apps: list[dict[str, Any]] = []
    if platform.system().lower() != "windows":
        return apps

    try:
        import winreg  # type: ignore

        roots = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        ]

        seen_names: set[str] = set()

        for hkey, subkey_path in roots:
            try:
                with winreg.OpenKey(hkey, subkey_path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as parent_key:
                    num_subkeys = winreg.QueryInfoKey(parent_key)[0]
                    for idx in range(num_subkeys):
                        try:
                            subkey_name = winreg.EnumKey(parent_key, idx)
                            with winreg.OpenKey(parent_key, subkey_name) as app_key:
                                def _get_val(name: str) -> str | None:
                                    try:
                                        val, _ = winreg.QueryValueEx(app_key, name)
                                        return str(val).strip() if val else None
                                    except Exception:
                                        return None

                                display_name = _get_val("DisplayName")
                                if not display_name or display_name in seen_names:
                                    continue

                                # Skip system updates, patches, components
                                if _get_val("SystemComponent") == "1" or _get_val("ParentKeyName"):
                                    continue
                                if display_name.startswith("Security Update") or display_name.startswith("Update for"):
                                    continue

                                seen_names.add(display_name)
                                version = _get_val("DisplayVersion")
                                publisher = _get_val("Publisher")
                                install_loc = _get_val("InstallLocation")
                                display_icon = _get_val("DisplayIcon")

                                # Resolve executable path
                                exe_path = ""
                                if display_icon:
                                    clean_icon = display_icon.split(",")[0].strip('"')
                                    if clean_icon.lower().endswith(".exe") and Path(clean_icon).exists():
                                        exe_path = clean_icon
                                if not exe_path and install_loc and Path(install_loc).exists():
                                    for exe in Path(install_loc).glob("*.exe"):
                                        exe_path = str(exe)
                                        break

                                if not exe_path:
                                    exe_path = f"{display_name}.exe"

                                category = categorize_app(display_name, exe_path)

                                apps.append({
                                    "name": display_name,
                                    "executable_path": exe_path,
                                    "version": version or "1.0",
                                    "publisher": publisher,
                                    "install_location": install_loc,
                                    "category": category,
                                    "is_system_app": False,
                                    "icon_url": None,
                                    "description": f"{display_name} desktop application.",
                                })
                        except Exception:
                            continue
            except Exception as exc:
                log.debug("scanner.registry_root_error", path=subkey_path, error=str(exc))
    except Exception as exc:
        log.warning("scanner.windows_registry_failed", error=str(exc))

    return apps


def scan_windows_start_menu() -> list[dict[str, Any]]:
    """Scan Windows Start Menu directory trees for application shortcuts."""
    apps: list[dict[str, Any]] = []
    if platform.system().lower() != "windows":
        return apps

    dirs = [
        Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
    ]

    for pdir in dirs:
        if not pdir.exists():
            continue
        try:
            for item in list(pdir.glob("**/*.lnk"))[:50]:
                stem = item.stem
                if stem.lower() in ("uninstall", "help", "documentation", "readme"):
                    continue
                apps.append({
                    "name": stem,
                    "executable_path": str(item),
                    "version": "1.0",
                    "publisher": None,
                    "install_location": str(item.parent),
                    "category": categorize_app(stem, str(item)),
                    "is_system_app": False,
                    "icon_url": None,
                    "description": f"Start Menu shortcut for {stem}.",
                })
        except Exception as exc:
            log.debug("scanner.start_menu_dir_error", path=str(pdir), error=str(exc))

    return apps


def scan_macos_applications() -> list[dict[str, Any]]:
    """Scan macOS /Applications and ~/Applications bundles with plistlib metadata extraction."""
    apps: list[dict[str, Any]] = []
    if platform.system().lower() != "darwin":
        return apps

    import plistlib

    app_dirs = [
        Path("/Applications"),
        Path("/System/Applications"),
        Path.home() / "Applications",
    ]

    for adir in app_dirs:
        if not adir.exists():
            continue
        for app_bundle in adir.glob("*.app"):
            plist_path = app_bundle / "Contents" / "Info.plist"
            if not plist_path.exists():
                continue
            try:
                with plist_path.open("rb") as f:
                    plist_data = plistlib.load(f)

                app_name = (
                    plist_data.get("CFBundleDisplayName")
                    or plist_data.get("CFBundleName")
                    or app_bundle.stem
                )
                bundle_id = plist_data.get("CFBundleIdentifier")
                version = plist_data.get("CFBundleShortVersionString") or plist_data.get("CFBundleVersion")
                exec_name = plist_data.get("CFBundleExecutable")
                exe_path = str(app_bundle / "Contents" / "MacOS" / exec_name) if exec_name else str(app_bundle)

                category = categorize_app(app_name, exe_path, bundle_id=bundle_id)

                apps.append({
                    "name": app_name,
                    "executable_path": exe_path,
                    "bundle_id": bundle_id,
                    "version": version or "1.0",
                    "publisher": "Apple" if "/System/Applications" in str(app_bundle) else None,
                    "install_location": str(app_bundle),
                    "category": category,
                    "is_system_app": "/System/Applications" in str(app_bundle),
                    "icon_url": None,
                    "description": f"macOS application {app_name}.",
                })
            except Exception as exc:
                log.debug("scanner.macos_plist_error", app=str(app_bundle), error=str(exc))

    return apps


def scan_linux_desktop_entries() -> list[dict[str, Any]]:
    """Scan Linux FreeDesktop .desktop application manifests."""
    apps: list[dict[str, Any]] = []
    if platform.system().lower() != "linux":
        return apps

    dirs = [
        Path("/usr/share/applications"),
        Path.home() / ".local" / "share" / "applications",
        Path("/var/lib/flatpak/exports/share/applications"),
        Path("/var/lib/snapd/desktop/applications"),
    ]

    for d in dirs:
        if not d.exists():
            continue
        for fpath in d.glob("*.desktop"):
            try:
                content = fpath.read_text(encoding="utf-8", errors="ignore")
                lines = content.splitlines()
                app_name: str | None = None
                exec_cmd: str | None = None
                categories: str | None = None
                comment: str | None = None
                no_display = False

                for line in lines:
                    line = line.strip()
                    if line.startswith("Name=") and app_name is None:
                        app_name = line[5:].strip()
                    elif line.startswith("Exec=") and exec_cmd is None:
                        exec_cmd = re.sub(r"%[a-zA-Z]", "", line[5:]).strip()
                    elif line.startswith("Categories=") and categories is None:
                        categories = line[11:].strip()
                    elif line.startswith("Comment=") and comment is None:
                        comment = line[8:].strip()
                    elif line == "NoDisplay=true":
                        no_display = True

                if no_display or not app_name or not exec_cmd:
                    continue

                category = categorize_app(app_name, exec_cmd, desktop_categories=categories)

                apps.append({
                    "name": app_name,
                    "executable_path": exec_cmd,
                    "version": "1.0",
                    "publisher": None,
                    "install_location": str(d),
                    "category": category,
                    "is_system_app": False,
                    "icon_url": None,
                    "description": comment or f"Linux application {app_name}.",
                })
            except Exception as exc:
                log.debug("scanner.linux_desktop_error", path=str(fpath), error=str(exc))

    return apps


def get_curated_preset_apps(os_name: str) -> list[dict[str, Any]]:
    """Provide guaranteed rich presets for primary productivity and system tools across platforms."""
    is_win = os_name == "windows"
    is_mac = os_name == "darwin"

    return [
        {
            "name": "Google Chrome",
            "executable_path": r"C:\Program Files\Google\Chrome\Application\chrome.exe" if is_win else ("/Applications/Google Chrome.app" if is_mac else "/usr/bin/google-chrome"),
            "category": "browser",
            "version": "128.0",
            "publisher": "Google LLC",
            "description": "Fast and secure web browser built by Google.",
            "icon_url": "https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/google-chrome.png",
        },
        {
            "name": "Microsoft Edge",
            "executable_path": r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" if is_win else ("/Applications/Microsoft Edge.app" if is_mac else "/usr/bin/microsoft-edge"),
            "category": "browser",
            "version": "128.0",
            "publisher": "Microsoft Corporation",
            "description": "Chromium-based browser with integrated Microsoft Copilot.",
            "icon_url": "https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/microsoft-edge.png",
        },
        {
            "name": "Visual Studio Code",
            "executable_path": "Code.exe" if is_win else ("/Applications/Visual Studio Code.app" if is_mac else "/usr/bin/code"),
            "category": "development",
            "version": "1.93.0",
            "publisher": "Microsoft Corporation",
            "description": "Extensible, lightweight code editor with debugger and Git support.",
            "icon_url": "https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/visual-studio-code.png",
        },
        {
            "name": "Terminal",
            "executable_path": "wt.exe" if is_win else ("/System/Applications/Utilities/Terminal.app" if is_mac else "x-terminal-emulator"),
            "category": "development",
            "version": "1.20",
            "publisher": "Microsoft Corporation" if is_win else "Apple",
            "description": "Tabbed command-line terminal environment.",
            "icon_url": "https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/terminal.png",
        },
        {
            "name": "PowerShell",
            "executable_path": "powershell.exe" if is_win else "/usr/bin/pwsh",
            "category": "development",
            "version": "7.4",
            "publisher": "Microsoft Corporation",
            "description": "Cross-platform task automation and configuration management framework.",
            "icon_url": "https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/powershell.png",
        },
        {
            "name": "Notepad",
            "executable_path": "notepad.exe" if is_win else "/usr/bin/nano",
            "category": "productivity",
            "version": "11.0",
            "publisher": "Microsoft Corporation",
            "description": "Fast plaintext editing scratchpad.",
            "icon_url": "https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/notepad.png",
        },
        {
            "name": "Calculator",
            "executable_path": "calc.exe" if is_win else ("/System/Applications/Calculator.app" if is_mac else "gnome-calculator"),
            "category": "utilities",
            "version": "10.0",
            "publisher": "Microsoft Corporation" if is_win else "Apple",
            "description": "Standard and scientific arithmetic calculation utility.",
            "icon_url": "https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/calculator.png",
        },
        {
            "name": "Task Manager",
            "executable_path": "taskmgr.exe" if is_win else ("/System/Applications/Utilities/Activity Monitor.app" if is_mac else "htop"),
            "category": "system",
            "version": "10.0",
            "publisher": "Microsoft Corporation" if is_win else "Apple",
            "description": "Real-time process, memory, and hardware monitor.",
            "icon_url": "https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/task-manager.png",
        },
        {
            "name": "Spotify",
            "executable_path": "Spotify.exe" if is_win else ("/Applications/Spotify.app" if is_mac else "spotify"),
            "category": "media",
            "version": "1.2",
            "publisher": "Spotify AB",
            "description": "Digital music and podcast streaming service.",
            "icon_url": "https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/spotify.png",
        },
        {
            "name": "Slack",
            "executable_path": "slack.exe" if is_win else ("/Applications/Slack.app" if is_mac else "slack"),
            "category": "communication",
            "version": "4.39",
            "publisher": "Slack Technologies",
            "description": "Enterprise messaging, channels, and team collaboration hub.",
            "icon_url": "https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/slack.png",
        },
        {
            "name": "Notion",
            "executable_path": "Notion.exe" if is_win else ("/Applications/Notion.app" if is_mac else "notion"),
            "category": "productivity",
            "version": "2.42",
            "publisher": "Notion Labs",
            "description": "All-in-one connected workspace for notes, docs, and databases.",
            "icon_url": "https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/notion.png",
        },
        {
            "name": "Discord",
            "executable_path": "Discord.exe" if is_win else ("/Applications/Discord.app" if is_mac else "discord"),
            "category": "communication",
            "version": "1.0",
            "publisher": "Discord Inc.",
            "description": "Voice, video, and text communication platform for communities.",
            "icon_url": "https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/discord.png",
        },
        {
            "name": "VLC Media Player",
            "executable_path": "vlc.exe" if is_win else ("/Applications/VLC.app" if is_mac else "vlc"),
            "category": "media",
            "version": "3.0",
            "publisher": "VideoLAN",
            "description": "Cross-platform multimedia player for audio and video streams.",
            "icon_url": "https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/vlc.png",
        },
        {
            "name": "Figma",
            "executable_path": "Figma.exe" if is_win else ("/Applications/Figma.app" if is_mac else "figma-linux"),
            "category": "design",
            "version": "116.0",
            "publisher": "Figma, Inc.",
            "description": "Collaborative web and mobile interface design application.",
            "icon_url": "https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/figma.png",
        },
        {
            "name": "Steam",
            "executable_path": "Steam.exe" if is_win else ("/Applications/Steam.app" if is_mac else "steam"),
            "category": "gaming",
            "version": "1.0",
            "publisher": "Valve Corporation",
            "description": "Digital storefront, game launcher, and community platform.",
            "icon_url": "https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/steam.png",
        },
    ]


# -----------------------------------------------------------------------------
# Process Cross-Referencing & Deduplication
# -----------------------------------------------------------------------------

def correlate_running_processes(apps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Cross-reference discovered applications with active operating system processes."""
    running_by_exe: dict[str, dict[str, Any]] = {}
    running_by_stem: dict[str, dict[str, Any]] = {}

    try:
        import psutil  # type: ignore

        for proc in psutil.process_iter(["pid", "name", "exe", "cpu_percent", "memory_percent"]):
            try:
                name = proc.info.get("name") or ""
                exe = proc.info.get("exe") or ""
                stem = Path(name).stem.lower()

                proc_meta = {
                    "pid": proc.info["pid"],
                    "cpu_percent": float(proc.info.get("cpu_percent") or 0.0),
                    "memory_percent": float(proc.info.get("memory_percent") or 0.0),
                    "name": name,
                    "exe": exe,
                }

                if exe:
                    running_by_exe[exe.lower()] = proc_meta
                if stem:
                    running_by_stem[stem] = proc_meta
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception as exc:
        log.debug("scanner.psutil_correlate_failed", error=str(exc))

    matched_stems: set[str] = set()

    for app in apps:
        exe_path = app.get("executable_path", "").lower()
        app_name = app.get("name", "").lower()
        exe_stem = Path(exe_path).stem.lower()
        app_stem = app_name.split()[0].lower()

        match = (
            running_by_exe.get(exe_path)
            or running_by_stem.get(exe_stem)
            or running_by_stem.get(app_stem)
        )

        if match:
            app["is_running"] = True
            app["process_id"] = match["pid"]
            matched_stems.add(exe_stem)
            matched_stems.add(app_stem)
            meta = app.get("metadata") or {}
            meta["cpu_percent"] = match["cpu_percent"]
            meta["memory_percent"] = match["memory_percent"]
            app["metadata"] = meta
        else:
            app["is_running"] = False
            app["process_id"] = None

    return apps


def deduplicate_and_enrich_apps(apps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate records by canonical name, enriching capabilities and action metadata."""
    grouped: dict[str, dict[str, Any]] = {}

    for app in apps:
        raw_name = app.get("name", "").strip()
        if not raw_name:
            continue

        # Clean noise suffixes: " (x86)", " (64-bit)", ".exe"
        canonical = re.sub(r"\s+\((?:x86|x64|64-bit|32-bit)\)$", "", raw_name, flags=re.IGNORECASE)
        canonical = re.sub(r"\.exe$", "", canonical, flags=re.IGNORECASE).strip()
        key = canonical.lower()

        category = app.get("category") or categorize_app(canonical, app.get("executable_path", ""))
        capabilities = infer_capabilities(category, canonical)
        actions = infer_supported_actions(category, canonical)

        enriched: dict[str, Any] = {
            "name": canonical,
            "executable_path": app.get("executable_path") or f"{canonical}.exe",
            "bundle_id": app.get("bundle_id"),
            "category": category,
            "version": app.get("version") or "1.0",
            "publisher": app.get("publisher"),
            "description": app.get("description") or f"{canonical} application.",
            "capabilities": capabilities,
            "supported_actions": actions,
            "metadata": app.get("metadata") or {},
            "install_location": app.get("install_location"),
            "is_system_app": app.get("is_system_app", False),
            "icon_url": app.get("icon_url"),
            "is_running": app.get("is_running", False),
            "process_id": app.get("process_id"),
        }

        if key not in grouped:
            grouped[key] = enriched
        else:
            existing = grouped[key]
            # Merge: prefer existing if it has real path / is running
            if enriched.get("is_running") and not existing.get("is_running"):
                existing["is_running"] = True
                existing["process_id"] = enriched.get("process_id")
            if enriched.get("publisher") and not existing.get("publisher"):
                existing["publisher"] = enriched.get("publisher")
            if enriched.get("install_location") and not existing.get("install_location"):
                existing["install_location"] = enriched.get("install_location")
            if enriched.get("icon_url") and not existing.get("icon_url"):
                existing["icon_url"] = enriched.get("icon_url")
            if len(enriched.get("executable_path", "")) > len(existing.get("executable_path", "")):
                existing["executable_path"] = enriched["executable_path"]

    return list(grouped.values())


# -----------------------------------------------------------------------------
# DeepAppScanner Main Coordinator
# -----------------------------------------------------------------------------

class DeepAppScanner:
    """Coordinator performing multi-tier application discovery across OS boundaries."""

    @classmethod
    def scan_system(
        cls,
        include_system_apps: bool = False,
    ) -> list[dict[str, Any]]:
        """Perform comprehensive application discovery, categorization, and process cross-referencing."""
        os_name = platform.system().lower()
        raw_apps: list[dict[str, Any]] = []

        # 1. Native platform scanners
        if os_name == "windows":
            raw_apps.extend(scan_windows_registry())
            raw_apps.extend(scan_windows_start_menu())
        elif os_name == "darwin":
            raw_apps.extend(scan_macos_applications())
        elif os_name == "linux":
            raw_apps.extend(scan_linux_desktop_entries())

        # 2. Standard curated presets (guarantees coverage of standard modern apps)
        raw_apps.extend(get_curated_preset_apps(os_name))

        # 3. Deduplicate and enrich metadata
        deduped = deduplicate_and_enrich_apps(raw_apps)

        # 4. Correlate with running processes
        correlated = correlate_running_processes(deduped)

        # 5. Filter system apps if requested
        if not include_system_apps:
            correlated = [a for a in correlated if not a.get("is_system_app")]

        # Sort by: running first, then name alphabetically
        correlated.sort(key=lambda a: (not a.get("is_running", False), a.get("name", "").lower()))
        return correlated
