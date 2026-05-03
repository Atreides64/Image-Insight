import { useCallback, useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

type Stats = {
  total_photos: number;
  total_size_bytes: number;
  file_type_counts: Record<string, number>;
  newest_modified_at: string | null;
  oldest_modified_at: string | null;
};

type ScanResult = {
  scan_id: number;
  status: string;
  total_files: number;
  new_files: number;
  updated_files: number;
  skipped_files: number;
  failed_files: number;
  elapsed_seconds: number;
  folder_path: string;
  last_error: string | null;
  files?: Array<Record<string, unknown>>;
};

type ScanSession = {
  scan_id: number;
  folder_path: string;
  status: string;
  started_at: string;
  completed_at: string | null;
  files_seen: number;
  image_files_matched: number;
  new_files: number;
  updated_files: number;
  skipped_files: number;
  failed_files: number;
  last_error: string | null;
};

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

function formatBytes(bytes: number): string {
  return new Intl.NumberFormat("en-US").format(bytes);
}

function formatGigabytes(bytes: number): string {
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
}

function formatDate(value: string | null): string {
  if (!value) {
    return "No data yet";
  }

  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function formatScanStatus(status: string): string {
  switch (status) {
    case "completed":
      return "Completed";
    case "failed":
      return "Failed";
    case "interrupted":
      return "Interrupted";
    case "running":
      return "Running";
    default:
      return status;
  }
}

function App() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [folderPath, setFolderPath] = useState("");
  const [isScanning, setIsScanning] = useState(false);
  const [scanMessage, setScanMessage] = useState<string | null>(null);
  const [scanError, setScanError] = useState<string | null>(null);
  const [lastScanSession, setLastScanSession] = useState<ScanSession | null>(null);

  const loadStats = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/stats`);

      if (!response.ok) {
        throw new Error(`Stats request failed with ${response.status}`);
      }

      setStats(await response.json());
      setError(null);
    } catch (caughtError) {
      setError(
        caughtError instanceof Error ? caughtError.message : "Unable to load stats",
      );
    } finally {
      setIsLoading(false);
    }
  }, []);

  const loadLatestScanSession = useCallback(async (targetFolderPath: string) => {
    const trimmedPath = targetFolderPath.trim();

    if (!trimmedPath) {
      setLastScanSession(null);
      return null;
    }

    try {
      const response = await fetch(
        `${API_BASE_URL}/scan-sessions?folder_path=${encodeURIComponent(trimmedPath)}`,
      );

      if (!response.ok) {
        throw new Error(`Scan sessions request failed with ${response.status}`);
      }

      const data = (await response.json()) as { scan_sessions: ScanSession[] };
      const latestSession = data.scan_sessions[0] ?? null;
      setLastScanSession(latestSession);
      return latestSession;
    } catch {
      setLastScanSession(null);
      return null;
    }
  }, []);

  useEffect(() => {
    loadStats();
  }, [loadStats]);

  useEffect(() => {
    void loadLatestScanSession(folderPath);
  }, [folderPath, loadLatestScanSession]);

  async function runScan({ resume }: { resume: boolean }) {
    const trimmedPath = folderPath.trim();

    if (!trimmedPath) {
      setScanError("Enter a folder path to scan.");
      setScanMessage(null);
      return;
    }

    setIsScanning(true);
    setScanError(null);
    setScanMessage(null);

    try {
      const response = await fetch(
        `${API_BASE_URL}/scan-folder?folder_path=${encodeURIComponent(trimmedPath)}&resume=${resume}`,
      );

      if (!response.ok) {
        let message = `Scan failed with ${response.status}`;

        try {
          const errorBody = await response.json();
          message = errorBody.detail ?? message;
        } catch {
          // Keep the status-based message if the backend response is not JSON.
        }

        throw new Error(message);
      }

      const result = (await response.json()) as ScanResult;
      const failedFilesMessage =
        result.failed_files > 0
          ? ` ${result.failed_files.toLocaleString()} could not be read this pass.`
          : "";
      const resumePrefix = resume ? "Resumed scan complete" : "Scan complete";

      setScanMessage(
        `${resumePrefix} for ${result.folder_path}. ${result.total_files.toLocaleString()} image files matched, ${result.new_files.toLocaleString()} new, ${result.updated_files.toLocaleString()} updated, ${result.skipped_files.toLocaleString()} skipped in ${result.elapsed_seconds.toFixed(2)}s.${failedFilesMessage}`,
      );
      await loadStats();
      await loadLatestScanSession(trimmedPath);
    } catch (caughtError) {
      await loadLatestScanSession(trimmedPath);
      setScanError(
        caughtError instanceof Error
          ? `The scan stopped before finishing. ${caughtError.message}`
          : "The scan stopped before finishing. You can review the last scan status and resume it when ready.",
      );
    } finally {
      setIsScanning(false);
    }
  }

  async function handleScanSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await runScan({ resume: false });
  }

  const fileTypeRows = useMemo(() => {
    if (!stats) {
      return [];
    }

    return Object.entries(stats.file_type_counts).sort(([left], [right]) =>
      left.localeCompare(right),
    );
  }, [stats]);

  const fileTypeChartData = useMemo(
    () =>
      fileTypeRows.map(([extension, count]) => ({
        extension,
        count,
      })),
    [fileTypeRows],
  );

  const canResumeLastScan =
    lastScanSession !== null &&
    ["failed", "interrupted", "running"].includes(lastScanSession.status);

  return (
    <main className="app-shell">
      <section className="page-header">
        <div>
          <p className="eyebrow">Image Insight</p>
          <h1>Photo Library Dashboard</h1>
        </div>
        <span className="status-pill">FastAPI / SQLite</span>
      </section>

      {isLoading && <p className="state-message">Loading dashboard...</p>}

      {error && (
        <div className="error-panel">
          <strong>Could not load stats.</strong>
          <span>{error}</span>
        </div>
      )}

      <section className="scan-section" aria-labelledby="scan-folder-heading">
        <div className="section-heading scan-heading">
          <div>
            <h2 id="scan-folder-heading">Scan Folder</h2>
            <span>Add local image files to the dashboard database</span>
          </div>
        </div>

        <form className="scan-form" onSubmit={handleScanSubmit}>
          <label htmlFor="folder-path">Local folder path</label>
          <div className="scan-controls">
            <input
              id="folder-path"
              type="text"
              value={folderPath}
              onChange={(event) => setFolderPath(event.target.value)}
              placeholder="/Users/you/Pictures"
              disabled={isScanning}
            />
            <button type="submit" disabled={isScanning}>
              {isScanning ? "Scanning..." : "Scan"}
            </button>
          </div>
        </form>

        {lastScanSession && (
          <div className="scan-history">
            <div className="scan-history-header">
              <strong>Previous Scan Status</strong>
              <span className={`scan-status ${lastScanSession.status}`}>
                {formatScanStatus(lastScanSession.status)}
              </span>
            </div>
            <p className="scan-history-meta">
              Started {formatDate(lastScanSession.started_at)}. Files seen:{" "}
              {lastScanSession.files_seen.toLocaleString()}, matched:{" "}
              {lastScanSession.image_files_matched.toLocaleString()}, new:{" "}
              {lastScanSession.new_files.toLocaleString()}, updated:{" "}
              {lastScanSession.updated_files.toLocaleString()}, skipped:{" "}
              {lastScanSession.skipped_files.toLocaleString()}, failed:{" "}
              {lastScanSession.failed_files.toLocaleString()}.
            </p>
            {lastScanSession.last_error && (
              <p className="scan-history-note">
                Last note: {lastScanSession.last_error}
              </p>
            )}
            {canResumeLastScan && (
              <button
                type="button"
                className="secondary-button"
                onClick={() => void runScan({ resume: true })}
                disabled={isScanning}
              >
                Resume Last Scan
              </button>
            )}
          </div>
        )}

        {isScanning && (
          <div className="scan-progress" role="status" aria-live="polite">
            <span className="spinner" aria-hidden="true" />
            <span>
              Scanning folder... this may take several minutes for large archives.
            </span>
          </div>
        )}

        {scanMessage && <p className="scan-feedback success">{scanMessage}</p>}
        {scanError && <p className="scan-feedback failure">{scanError}</p>}
      </section>

      {stats && (
        <>
          <section className="stats-grid" aria-label="Photo library stats">
            <article className="stat-card">
              <span>Total Photos</span>
              <strong>{stats.total_photos.toLocaleString()}</strong>
            </article>
            <article className="stat-card">
              <span>Total Size</span>
              <strong>{formatGigabytes(stats.total_size_bytes)}</strong>
              <small>{formatBytes(stats.total_size_bytes)} bytes</small>
            </article>
            <article className="stat-card">
              <span>Newest Date</span>
              <strong>{formatDate(stats.newest_modified_at)}</strong>
            </article>
            <article className="stat-card">
              <span>Oldest Date</span>
              <strong>{formatDate(stats.oldest_modified_at)}</strong>
            </article>
          </section>

          <section className="chart-section">
            <div className="section-heading">
              <h2>File Type Distribution</h2>
              <span>{fileTypeRows.length} types</span>
            </div>

            {fileTypeChartData.length > 0 ? (
              <div className="chart-frame">
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart data={fileTypeChartData}>
                    <CartesianGrid stroke="#273244" vertical={false} />
                    <XAxis
                      dataKey="extension"
                      stroke="#a7b3c6"
                      tickLine={false}
                      axisLine={false}
                    />
                    <YAxis
                      allowDecimals={false}
                      stroke="#a7b3c6"
                      tickLine={false}
                      axisLine={false}
                    />
                    <Tooltip
                      cursor={{ fill: "rgba(111, 211, 184, 0.08)" }}
                      contentStyle={{
                        background: "#121a26",
                        border: "1px solid #2f3d52",
                        borderRadius: "8px",
                        color: "#edf5ff",
                      }}
                    />
                    <Bar
                      dataKey="count"
                      fill="#6fd3b8"
                      radius={[6, 6, 0, 0]}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <p className="empty-chart">Run a scan to populate file type data.</p>
            )}
          </section>

          <section className="table-section">
            <div className="section-heading">
              <h2>File Type Counts</h2>
              <span>{stats.total_photos.toLocaleString()} indexed photos</span>
            </div>

            <table>
              <thead>
                <tr>
                  <th>Extension</th>
                  <th>Count</th>
                </tr>
              </thead>
              <tbody>
                {fileTypeRows.length > 0 ? (
                  fileTypeRows.map(([extension, count]) => (
                    <tr key={extension}>
                      <td>{extension.toUpperCase()}</td>
                      <td>{count.toLocaleString()}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={2}>No photo data yet.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </section>
        </>
      )}
    </main>
  );
}

export default App;
