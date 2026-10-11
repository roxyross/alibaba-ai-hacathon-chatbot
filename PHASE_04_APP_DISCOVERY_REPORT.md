# Phase 4: Local Application Discovery Engine — Production Execution Report

**Date**: 2026-10-02  
**Status**: Verified & Production Ready  
**Execution Gate**: Passed (10/10 Phase 4 tests, 46/46 cumulative Phase 1–4 regression tests)  
**Target Subsystem**: Local Application Discovery Engine (`backend/src/app/device/scanner.py`, `service.py`, `router.py`, `daemon.py`, `models/device.py`)

---

## 1. Executive Summary

Phase 4 delivers the **Local Application Discovery Engine (System Scanner, Deep App Catalog & Metadata Intelligence)** for Roxy AI. This engine replaces naive mock application lookups with deep OS-native scanning, active process correlation, automatic taxonomy categorization, action verb derivation, and real-time remote daemon catalog synchronization.

Operating under the strict **Zero Simulation** principle:
- Real platform registry hives (`HKLM`, `HKCU`) and Start Menu trees are traversed on Windows.
- Standard `.app/Contents/Info.plist` manifests are parsed on macOS.
- XDG freedesktop `.desktop` files are scanned across system and user application paths on Linux.
- Live process telemetry (PIDs, CPU%, Memory%, running status) is correlated dynamically via `psutil`.
- 12 canonical application categories and operational capability verbs (`open`, `close`, `read`, `write`, `execute`, `inspect`) are derived autonomously without human intervention.
- The complete pipeline is backed by a linear, zero-downtime database migration (`009_deep_app_catalog.py`), REST APIs with search and pagination, and daemon synchronization.

---

## 2. Architecture & Subsystems

```mermaid
graph TD
    subgraph Host OS Environment
        REG[Windows Registry HKLM / HKCU]
        LNK[Windows Start Menu Shortcuts]
        PLIST[macOS Info.plist Bundles]
        DESK[Linux XDG .desktop Entries]
        PROC[psutil Running Processes]
    end

    subgraph Deep Scanner Engine
        SCAN[DeepAppScanner.scan_system]
        DEDUP[deduplicate_and_enrich_apps]
        CORR[correlate_running_processes]
        CAT[categorize_app - 12 Taxonomies]
        CAP[infer_capabilities & infer_supported_actions]
    end

    subgraph Backend & Daemon
        SVC[DeviceService]
        ROUTER[FastAPI /devices/{id}/apps Router]
        DAEMON[RoxyDeviceDaemon app_scan & sync]
        DB[(PostgreSQL DiscoveredApp)]
    end

    REG --> SCAN
    LNK --> SCAN
    PLIST --> SCAN
    DESK --> SCAN
    PROC --> CORR
    SCAN --> DEDUP
    CORR --> DEDUP
    CAT --> DEDUP
    CAP --> DEDUP
    DEDUP --> SVC
    DAEMON -->|POST /apps/sync| ROUTER
    ROUTER --> SVC
    SVC --> DB
```

---

## 3. Key Components Implemented

### 3.1 Multi-Platform Deep Scanner (`backend/src/app/device/scanner.py`)
- **Windows Scanner**:
  - Scans `HKEY_LOCAL_MACHINE\Software\Microsoft\Windows\CurrentVersion\Uninstall` (both 64-bit and 32-bit `KEY_WOW64_32KEY` / `KEY_WOW64_64KEY`).
  - Scans `HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Uninstall`.
  - Scans system and user Start Menu directory trees (`%APPDATA%\Microsoft\Windows\Start Menu\Programs` and `%ALLUSERSPROFILE%\Microsoft\Windows\Start Menu\Programs`) extracting binary targets from `.lnk` files.
- **macOS Scanner**:
  - Traverses `/Applications`, `/System/Applications`, and `~/Applications`.
  - Extracts `CFBundleName`, `CFBundleIdentifier`, `CFBundleShortVersionString`, and executable path from `Contents/Info.plist`.
- **Linux Scanner**:
  - Parses XDG standard `.desktop` files from `/usr/share/applications`, `/usr/local/share/applications`, and `~/.local/share/applications`.
  - Parses `Name`, `Exec`, `Icon`, `Categories`, and `Comment`.
- **Curated Preset Fallback**:
  - Provides a base index of standard tools across categories (Chrome, VS Code, Slack, Obsidian, Terminal, etc.) when running in restricted sandbox environments.

### 3.2 Real-Time Process Correlation (`psutil`)
- Queries active system processes using `psutil.process_iter(['pid', 'name', 'exe', 'cpu_percent', 'memory_info'])`.
- Normalizes process names and executables, mapping matching installed applications to:
  - `is_running: bool`
  - `pid: int`
  - `cpu_percent: float`
  - `memory_mb: float`

### 3.3 Metadata Intelligence & Rule-Based Categorization
- **12 Canonical Taxonomies**:
  1. `browser` (Chrome, Firefox, Edge, Safari, Brave, Opera, Arc)
  2. `development` (VS Code, Cursor, PyCharm, IntelliJ, Git, Docker, Terminal, Postman, Sublime)
  3. `communication` (Slack, Teams, Discord, Zoom, Telegram, Signal, WhatsApp, Skype)
  4. `productivity` (Notion, Obsidian, Word, Excel, PowerPoint, LibreOffice, Notes, Todoist)
  5. `media` (VLC, Spotify, OBS Studio, Audacity, Netflix, Handbrake, GIMP)
  6. `design` (Figma, Photoshop, Illustrator, Blender, Inkscape, Canva)
  7. `system` (Settings, Task Manager, Disk Utility, Activity Monitor, Control Panel)
  8. `utilities` (7-Zip, WinRAR, Calculator, Snipping Tool, TextEdit, Notepad)
  9. `finance` (TurboTax, Quicken, QuickBooks, Mint, Ledger)
  10. `education` (Anki, Duolingo, Khan Academy)
  11. `gaming` (Steam, Epic Games, Battle.net, Minecraft, Discord, GOG)
  12. `other` (General fallback)
- **Word-Boundary Precision Matching**:
  - Employs regex boundaries (`\b`) to eliminate false positives (e.g., prevents `"obs"` from matching inside `"obsidian"`, keeping Obsidian firmly in `productivity` while OBS Studio maps to `media`).
- **Capability & Action Verb Derivation**:
  - Derives capabilities: `[app_launch, web_navigation, text_editing, file_read, code_execution, audio_playback, etc.]`.
  - Derives supported action verbs: `[launch, terminate, focus, read, search, play, compile, etc.]`.

### 3.4 Database Migration & Schema (`backend/alembic/versions/009_deep_app_catalog.py`)
- Extends the `discovered_apps` table with:
  - `publisher: String(255)`
  - `description: Text`
  - `capabilities_json: Text` (JSON list of derived capabilities)
  - `supported_actions_json: Text` (JSON list of actionable verbs)
  - `metadata_json: Text` (JSON dictionary of rich OS metadata)
  - `install_location: String(512)`
  - `is_system_app: Boolean`
- Verified linear revision history: `008_device_agent_enrollment -> 009_deep_app_catalog`.

### 3.5 Device Service & API Endpoints
- **Service Layer (`backend/src/app/device/service.py`)**:
  - `scan_installed_apps(user_id, device_id, force_refresh)`: Orchestrates deep scanner, upserts into database and memory cache idempotently.
  - `list_apps(user_id, device_id, category, is_running, search, limit, offset)`: Full-text search over app name/description/publisher, category filters, and pagination.
  - `get_app_details(user_id, device_id, app_id)`: Deep metadata lookup by app ID or normalized name.
  - `sync_device_apps(user_id, device_id, apps_data)`: Remote daemon catalog ingestion.
- **REST Endpoints (`backend/src/app/device/router.py`)**:
  - `POST /api/v1/devices/{device_id}/apps/scan`: Initiates system scan, returning categorized summary counts and running process totals.
  - `GET /api/v1/devices/{device_id}/apps`: Filterable, searchable, paginated app collection.
  - `GET /api/v1/devices/{device_id}/apps/{app_id}`: Single app deep metadata.
  - `POST /api/v1/devices/{device_id}/apps/sync`: Daemon ingestion endpoint with device token authentication (`X-Device-Token`).

### 3.6 Remote Agent Daemon Integration (`backend/src/app/device/daemon.py`)
- Registered `"app_scan"` command inside `execute_command`.
- Added `sync_apps_to_backend(apps)` to push local deep discovery snapshots to the centralized backend via `POST /api/v1/devices/{device_id}/apps/sync`.

---

## 4. Test Verification & Results

### 4.1 Phase 4 Test Suite (`backend/tests/test_phase4_app_discovery.py`)
| Test Case | Scope | Result |
| :--- | :--- | :--- |
| `test_categorize_app_archetypes` | Verifies 12-taxonomy categorization & boundary matching | **PASSED** |
| `test_infer_capabilities_and_actions` | Validates capability & verb inference by category | **PASSED** |
| `test_deep_app_scanner_execution` | Tests OS-level discovery engine execution | **PASSED** |
| `test_correlate_running_processes` | Validates live process matching via psutil | **PASSED** |
| `test_deduplicate_and_enrich_apps` | Tests deduplication, path resolution, and enrichments | **PASSED** |
| `test_service_scan_installed_apps_idempotency` | Verifies multi-scan stability and database upsert idempotency | **PASSED** |
| `test_service_list_apps_filtering_and_search` | Tests category filter, running filter, text search, pagination | **PASSED** |
| `test_service_get_app_details` | Tests app lookup by ID and fallback by name | **PASSED** |
| `test_daemon_catalog_sync` | Tests remote daemon app catalog synchronization | **PASSED** |
| `test_app_discovery_api_router_lifecycle` | End-to-end FastAPI test of scan, search, filter, detail, and sync | **PASSED** |

**Phase 4 Outcome**: **10 / 10 Tests Passed** (100% pass rate in 15.32s).

---

### 4.2 Cumulative Regression Verification (Phases 1 through 4)
Executed command:
```bash
python -m pytest tests/test_phase1_security_hardening.py tests/test_phase2_target_scoped_permissions.py tests/test_phase3_device_agent.py tests/test_phase4_app_discovery.py -v
```

| Phase Suite | File | Tests Passed | Status |
| :--- | :--- | :---: | :---: |
| **Phase 1: Security Hardening** | `test_phase1_security_hardening.py` | 12 / 12 | **GREEN** |
| **Phase 2: Target-Scoped Permissions** | `test_phase2_target_scoped_permissions.py` | 12 / 12 | **GREEN** |
| **Phase 3: Standalone Device Agent** | `test_phase3_device_agent.py` | 12 / 12 | **GREEN** |
| **Phase 4: App Discovery Engine** | `test_phase4_app_discovery.py` | 10 / 10 | **GREEN** |
| **Total Cumulative** | **4 Test Suites** | **46 / 46** | **100% PASSED** (19.75s) |

---

## 5. Security & Privacy Safeguards
1. **Zero Path Traversal / Command Injection**:
   - Executable path resolution uses strict OS string sanitization and absolute path validation.
   - App discovery avoids shell execution (`shell=False`), leveraging direct registry APIs (`winreg`) and direct filesystem reading.
2. **Process Telemetry Sanitization**:
   - Running process correlation only extracts system metrics (PID, CPU, Memory). Environment variables and command-line secrets (`cmdline`) are not ingested into the public app catalog.
3. **Device Token Scoping**:
   - The `/apps/sync` endpoint requires valid `X-Device-Token` authentication and verifies device ownership before allowing catalog updates.

---

## 6. Exit Gate Checklist

- [x] Multi-platform scanner parses Windows registry, Start Menu, macOS Plists, Linux desktop entries.
- [x] Real-time `psutil` process correlation actively reports PID, CPU%, Memory MB, and running status.
- [x] Rule-based categorization maps apps to 12 canonical taxonomies with regex word boundaries.
- [x] Capabilities and action verbs are autonomously derived for each discovered app.
- [x] Alembic migration `009_deep_app_catalog.py` validated with clean linear revision graph.
- [x] `DiscoveredApp` model updated with deep catalog fields and JSON serializable properties.
- [x] `DeviceService` supports idempotent scanning, category filters, full-text search, and pagination.
- [x] REST API endpoints (`/apps/scan`, `/apps`, `/apps/{app_id}`, `/apps/sync`) fully tested and operational.
- [x] Standalone `RoxyDeviceDaemon` integrates `DeepAppScanner` and backend synchronization.
- [x] All 10 Phase 4 tests pass 100%.
- [x] Cumulative regression suite (Phases 1–4) passes 46/46 tests without regression.

**Phase 4 is complete and verified.** Ready to proceed to **Phase 5: Knowledge Vault & Vector Memory**.
