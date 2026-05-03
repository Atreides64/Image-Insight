import { useEffect, useMemo, useState } from "react";
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

function App() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadStats() {
      try {
        const response = await fetch(`${API_BASE_URL}/stats`);

        if (!response.ok) {
          throw new Error(`Stats request failed with ${response.status}`);
        }

        setStats(await response.json());
      } catch (caughtError) {
        setError(
          caughtError instanceof Error
            ? caughtError.message
            : "Unable to load stats",
        );
      } finally {
        setIsLoading(false);
      }
    }

    loadStats();
  }, []);

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
                    <Bar dataKey="count" fill="#6fd3b8" radius={[6, 6, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <p className="empty-chart">No scanned files yet.</p>
            )}
          </section>

          <section className="table-section">
            <div className="section-heading">
              <h2>File Types</h2>
              <span>{fileTypeRows.length} types</span>
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
                      <td>{extension}</td>
                      <td>{count.toLocaleString()}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={2}>No scanned files yet.</td>
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
