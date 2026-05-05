# Image Insight Desktop Packaging Plan

This plan describes how to turn the current React + FastAPI + SQLite app into a Windows desktop app without changing scan behavior yet.

## Recommendation

Use **Tauri 2 with a bundled Python backend sidecar** as the first desktop packaging approach.

Image Insight is local-first, filesystem-heavy, and already has a complete React UI plus a FastAPI backend. Tauri fits that shape well because it can ship the Vite frontend in a small native WebView shell, run an embedded backend executable as a sidecar, and expose native folder selection without bringing in a full Chromium runtime. Electron is viable and easier for Node-centric teams, but it adds a larger runtime and does not provide much extra value for this app because the backend remains Python either way.

## Tauri vs Electron for Image Insight

| Area | Tauri | Electron |
| --- | --- | --- |
| Fit for current frontend | Strong. Vite/React can remain the frontend build output loaded by the WebView. | Strong. Vite/React can also be loaded into a BrowserWindow. |
| Backend integration | Good. Tauri supports external binaries, called sidecars, including PyInstaller-built Python API servers. | Good. Electron main can spawn packaged executables with Node child process APIs or similar process helpers. |
| Installer/runtime size | Usually smaller because it uses the system WebView2 runtime on Windows. | Usually larger because Chromium and Node are bundled. |
| Windows dependency | Requires WebView2 runtime. This is generally present on modern Windows, but installer strategy should account for it. | Bundles Chromium, so fewer WebView runtime concerns. |
| Native folder picker | Good. Tauri dialog plugin supports directory selection and returns filesystem paths on desktop platforms. | Good. Electron dialog supports `openDirectory`. |
| Security posture | Good default isolation model, explicit capabilities/plugins, smaller browser surface. | Good when configured carefully, but more footguns around preload, Node integration, and IPC. |
| Developer complexity | Adds Rust/Tauri config and sidecar target-triple naming. | Adds Electron main/preload code and packaging config; familiar if the team prefers JavaScript. |
| Python packaging complexity | Still required. Need PyInstaller/Nuitka backend executable. | Still required. Need PyInstaller/Nuitka backend executable. |
| Best reason to choose | Smaller native shell, clear sidecar model, good match for local utility app. | If future desktop work needs deep Node/Electron ecosystem packages or Chromium-specific behavior. |

Sources used:

- Tauri sidecars: <https://tauri.app/develop/sidecar/>
- Tauri dialog plugin: <https://v2.tauri.app/plugin/dialog/>
- Tauri path API: <https://v2.tauri.app/ja/reference/javascript/api/namespacepath/>
- Electron dialog API: <https://www.electronjs.org/docs/latest/api/dialog>
- Electron utility process API: <https://www.electronjs.org/docs/latest/api/utility-process>
- Electron app paths: <https://www.electronjs.org/docs/latest/api/app/>

## Target Architecture

The packaged app should have three pieces:

1. Tauri desktop shell
2. Built React frontend from `frontend/dist`
3. Bundled FastAPI backend executable running on localhost as a sidecar

The frontend should continue using HTTP requests, but in packaged mode it should target the sidecar on a loopback port selected by the shell/backend at startup.

Recommended runtime flow:

1. User opens Image Insight.
2. Tauri starts the backend sidecar before showing or immediately after creating the main window.
3. Backend binds to `127.0.0.1` on a free local port.
4. Tauri waits for `/health` to return `{"status":"ok"}`.
5. Tauri injects or exposes the API base URL to the frontend.
6. React dashboard loads normally.
7. On app close, Tauri requests graceful backend shutdown or kills the sidecar after a short timeout.

## Required Repo Changes

Add desktop packaging files:

- `src-tauri/`
- `src-tauri/tauri.conf.json`
- `src-tauri/Cargo.toml`
- `src-tauri/src/main.rs`
- `src-tauri/capabilities/default.json`
- `src-tauri/binaries/` for packaged backend executables

Add backend packaging files:

- `packaging/backend_server.py` or `app/desktop_server.py` as a thin executable entrypoint
- `packaging/pyinstaller-image-insight.spec`
- `scripts/package-backend.ps1`
- `scripts/package-desktop.ps1`

Add frontend desktop integration:

- A small API base URL resolver that supports:
  - dev web mode: `VITE_API_BASE_URL` or `http://127.0.0.1:8000`
  - desktop mode: value provided by Tauri
- A native folder picker adapter:
  - web/dev fallback: existing text input
  - desktop mode: Tauri dialog plugin

Add CI or local build steps later:

- Backend package smoke test
- Frontend `npm run build`
- Tauri build on Windows
- Installer artifact upload

## Backend Startup Strategy

Use a dedicated backend executable entrypoint instead of running `uvicorn app.main:app --reload`.

Proposed behavior:

- Package the backend with PyInstaller.
- Start it as a Tauri sidecar.
- Bind only to `127.0.0.1`.
- Use a dynamic free port, then communicate that port to Tauri through stdout JSON or a small port file in the app data directory.
- Disable reload mode.
- Keep the existing FastAPI app and endpoints unchanged.
- Preserve startup cleanup that marks stale `running` scan sessions as `interrupted`.

Recommended sidecar startup contract:

```text
image-insight-backend.exe --host 127.0.0.1 --port 0 --database-path <app-data>\image_insight.db
```

The backend should print one machine-readable line when ready:

```json
{"event":"ready","host":"127.0.0.1","port":49231}
```

Tauri should watch sidecar stdout, then pass `http://127.0.0.1:49231` to the frontend.

## Backend Shutdown Strategy

Prefer graceful shutdown first:

1. Tauri sends `POST /shutdown` to the backend, protected so it only accepts loopback calls and only exists in desktop mode.
2. Backend stops accepting new work.
3. If a scan is running, either:
   - request cancellation and persist `cancelled`, or
   - mark the session `interrupted` if the process is closing immediately.
4. Backend exits.
5. Tauri waits a short timeout, then kills the sidecar if still running.

Alternative if avoiding a `/shutdown` endpoint initially:

- Let Tauri kill the sidecar on window/app exit.
- Rely on existing startup cleanup to mark stale `running` scan sessions as `interrupted` next launch.

Recommendation: implement graceful shutdown for polish, but keep startup cleanup as the safety net.

## Database Location Strategy

Do not keep using the repo-root `image_insight.db` in packaged builds.

For Windows desktop builds, store the SQLite database under an app-owned user data directory:

```text
%LOCALAPPDATA%\Image Insight\image_insight.db
```

Rationale:

- The install directory may be read-only.
- The repo root does not exist for normal users.
- The database can grow, so local app data is a better fit than roaming profile storage.
- Electron docs note `userData` is for app configuration and warn that large files may be backed up in some environments; this is another reason to prefer local app data for the SQLite library index.

Required backend change later:

- Add an `IMAGE_INSIGHT_DATABASE_PATH` or `--database-path` option.
- Keep `IMAGE_INSIGHT_DATABASE_URL` for tests.
- Resolve packaged default from the desktop shell and pass it to the backend.
- Ensure parent directories are created before SQLAlchemy initializes.

Suggested path behavior:

- Development default: repo-root `image_insight.db`, unchanged.
- Tests: `IMAGE_INSIGHT_DATABASE_URL`, unchanged.
- Desktop: explicit `--database-path` from Tauri app local data directory.

## Native Folder Picker Strategy

Use Tauri's dialog plugin in desktop mode.

Frontend behavior:

- Add a `Choose Folder` button next to the scan path input.
- In Tauri desktop mode, call the dialog plugin with directory selection.
- Put the selected folder path into the existing folder path state.
- Keep manual path entry available for power users and debugging.
- In browser dev mode, hide the native button or leave it disabled with the text input unchanged.

The scan API can remain unchanged because it already accepts a folder path string.

## Implementation Roadmap

### Phase 1: Backend Executable Spike

- Add a desktop backend entrypoint.
- Add CLI args for host, port, and database path.
- Package with PyInstaller.
- Confirm the executable can:
  - start FastAPI,
  - create/open SQLite in a temp app data folder,
  - return `/health`,
  - scan a small test folder,
  - exit cleanly.

Exit criteria:

- A local `.exe` backend runs without an activated virtualenv.
- Existing pytest suite still passes.

### Phase 2: Tauri Shell Spike

- Add `src-tauri`.
- Configure Vite frontend dist as the app frontend.
- Add sidecar config for the backend executable.
- Start backend sidecar on app startup.
- Read backend ready event from stdout.
- Pass API base URL to React.

Exit criteria:

- `npm run tauri dev` opens the dashboard and loads `/stats`.
- App closes without leaving a backend process running.

### Phase 3: Desktop Database Path

- Add backend database path CLI/env support.
- Tauri resolves app local data directory and passes `image_insight.db`.
- `/system-info` reports the desktop database path.

Exit criteria:

- Packaged/dev desktop app stores DB under app data.
- Browser/dev backend still uses repo-root DB by default.
- Tests still override database cleanly.

### Phase 4: Native Folder Picker

- Add Tauri dialog plugin.
- Add `Choose Folder` button in Scan Library.
- Keep manual path input.
- Add a frontend abstraction so browser mode does not depend on Tauri globals.

Exit criteria:

- Windows folder picker returns a path that can be scanned.
- Manual entry still works.

### Phase 5: Packaging Polish

- Add app icon and product metadata.
- Add Windows installer target.
- Add smoke test checklist.
- Decide whether to bundle ExifTool or keep it optional.
- Confirm update strategy: manual installer download first, auto-update later.

Exit criteria:

- A Windows installer installs and launches Image Insight.
- First run can choose a folder, scan, close, reopen, and keep the indexed database.

## Open Decisions

- PyInstaller vs Nuitka for backend executable.
- Whether to bundle ExifTool in the app or keep current PATH detection.
- Whether to add a desktop-only `/shutdown` endpoint now or rely on sidecar kill plus startup cleanup at first.
- Whether desktop should allow multiple folder selections in one picker pass or keep one folder per scan.
- Whether production desktop should keep localhost HTTP or move selected commands to Tauri IPC over time.

## Initial Recommendation Summary

Start with **Tauri 2 + PyInstaller backend sidecar + SQLite in `%LOCALAPPDATA%\Image Insight` + Tauri native folder picker**.

This path preserves the current architecture, minimizes UI rewrite risk, keeps the app local-first, avoids Electron's larger runtime, and gives Image Insight a practical Windows desktop path without changing scan architecture.
