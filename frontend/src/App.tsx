import { useCallback, useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

type CountRow = {
  label: string;
  count: number;
};

type TimelineInsightRow = CountRow & {
  top_camera: string | null;
  top_lens: string | null;
};

type Stats = {
  total_photos: number;
  total_size_bytes: number;
  file_type_counts: Record<string, number>;
  top_cameras: CountRow[];
  top_lenses: CountRow[];
  top_focal_lengths: CountRow[];
  photos_by_year: CountRow[];
  photos_by_month: CountRow[];
  photo_timeline: TimelineInsightRow[];
  busiest_date: CountRow | null;
  newest_modified_at: string | null;
  oldest_modified_at: string | null;
};

type PhotoSearchResult = {
  id: number;
  filename: string;
  path: string;
  extension: string;
  camera_model: string | null;
  lens_model: string | null;
  focal_length: number | null;
  date_taken: string | null;
};

type PhotoSearchResponse = {
  total_count: number;
  limit: number;
  offset: number;
  results: PhotoSearchResult[];
};

type PhotoSearchFilters = {
  camera_model: string;
  lens_model: string;
  min_focal_length: string;
  max_focal_length: string;
  date_from: string;
  date_to: string;
};

type DashboardPreferences = {
  showTotalPhotosCard: boolean;
  showTotalSizeCard: boolean;
  showNewestDateCard: boolean;
  showOldestDateCard: boolean;
  showFavoriteCameraCard: boolean;
  showFavoriteLensCard: boolean;
  showFocalLengthCard: boolean;
  showBusiestDateCard: boolean;
  showScanHistorySection: boolean;
  showMetadataSearchSection: boolean;
  showCameraChart: boolean;
  showLensChart: boolean;
  showTimelineChart: boolean;
  showFileTypeChart: boolean;
  showFileTypeTable: boolean;
};

type SystemInfo = {
  app_version: string;
  database_path: string;
  photo_count: number;
  scan_session_count: number;
  exiftool_available: boolean;
};

type ScanStartResult = {
  scan_id: number;
  status: string;
  folder_path: string;
  force_metadata: boolean;
  exiftool_available: boolean;
  message?: string;
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
  elapsed_seconds: number;
  scan_speed_files_per_second: number;
  force_metadata: boolean;
  exiftool_available: boolean;
  last_error: string | null;
};

type ScanStatus = {
  scan_id: number;
  folder_path: string;
  status: string;
  files_seen: number;
  image_files_matched: number;
  new_files: number;
  updated_files: number;
  skipped_files: number;
  failed_files: number;
  elapsed_seconds: number;
  scan_speed_files_per_second: number;
  force_metadata: boolean;
  exiftool_available: boolean;
  last_error: string | null;
};

type ActiveTool = "scan" | "search" | null;

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
const TERMINAL_SCAN_STATUSES = ["completed", "failed", "interrupted", "cancelled"];
const PHOTO_SEARCH_LIMIT = 25;
const DASHBOARD_PREFERENCES_STORAGE_KEY = "image-insight-dashboard-preferences";
const COMPACT_DASHBOARD_STORAGE_KEY = "image-insight-compact-dashboard";
const DEFAULT_DASHBOARD_PREFERENCES: DashboardPreferences = {
  showTotalPhotosCard: true,
  showTotalSizeCard: true,
  showNewestDateCard: true,
  showOldestDateCard: true,
  showFavoriteCameraCard: true,
  showFavoriteLensCard: true,
  showFocalLengthCard: true,
  showBusiestDateCard: true,
  showScanHistorySection: true,
  showMetadataSearchSection: true,
  showCameraChart: true,
  showLensChart: true,
  showTimelineChart: true,
  showFileTypeChart: true,
  showFileTypeTable: true,
};

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

function formatCalendarDate(value: string | null): string {
  if (!value) {
    return "No data yet";
  }

  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
  }).format(new Date(`${value}T00:00:00`));
}

function formatOptional(value: string | number | null): string {
  if (value === null || value === "") {
    return "—";
  }

  return String(value);
}

function formatFocalLength(value: number | null): string {
  return value === null ? "—" : `${value}mm`;
}

function loadDashboardPreferences(): DashboardPreferences {
  try {
    const storedPreferences = window.localStorage.getItem(
      DASHBOARD_PREFERENCES_STORAGE_KEY,
    );

    if (!storedPreferences) {
      return DEFAULT_DASHBOARD_PREFERENCES;
    }

    const parsedPreferences = JSON.parse(storedPreferences) as
      Partial<DashboardPreferences> & {
        showSummaryCards?: boolean;
        showExifCards?: boolean;
        showCharts?: boolean;
      };

    return {
      showTotalPhotosCard:
        parsedPreferences.showTotalPhotosCard ??
        parsedPreferences.showSummaryCards ??
        DEFAULT_DASHBOARD_PREFERENCES.showTotalPhotosCard,
      showTotalSizeCard:
        parsedPreferences.showTotalSizeCard ??
        parsedPreferences.showSummaryCards ??
        DEFAULT_DASHBOARD_PREFERENCES.showTotalSizeCard,
      showNewestDateCard:
        parsedPreferences.showNewestDateCard ??
        parsedPreferences.showSummaryCards ??
        DEFAULT_DASHBOARD_PREFERENCES.showNewestDateCard,
      showOldestDateCard:
        parsedPreferences.showOldestDateCard ??
        parsedPreferences.showSummaryCards ??
        DEFAULT_DASHBOARD_PREFERENCES.showOldestDateCard,
      showFavoriteCameraCard:
        parsedPreferences.showFavoriteCameraCard ??
        parsedPreferences.showExifCards ??
        DEFAULT_DASHBOARD_PREFERENCES.showFavoriteCameraCard,
      showFavoriteLensCard:
        parsedPreferences.showFavoriteLensCard ??
        parsedPreferences.showExifCards ??
        DEFAULT_DASHBOARD_PREFERENCES.showFavoriteLensCard,
      showFocalLengthCard:
        parsedPreferences.showFocalLengthCard ??
        parsedPreferences.showExifCards ??
        DEFAULT_DASHBOARD_PREFERENCES.showFocalLengthCard,
      showBusiestDateCard:
        parsedPreferences.showBusiestDateCard ??
        parsedPreferences.showExifCards ??
        DEFAULT_DASHBOARD_PREFERENCES.showBusiestDateCard,
      showScanHistorySection:
        parsedPreferences.showScanHistorySection ??
        DEFAULT_DASHBOARD_PREFERENCES.showScanHistorySection,
      showMetadataSearchSection:
        parsedPreferences.showMetadataSearchSection ??
        DEFAULT_DASHBOARD_PREFERENCES.showMetadataSearchSection,
      showCameraChart:
        parsedPreferences.showCameraChart ??
        parsedPreferences.showCharts ??
        DEFAULT_DASHBOARD_PREFERENCES.showCameraChart,
      showLensChart:
        parsedPreferences.showLensChart ??
        parsedPreferences.showCharts ??
        DEFAULT_DASHBOARD_PREFERENCES.showLensChart,
      showTimelineChart:
        parsedPreferences.showTimelineChart ??
        parsedPreferences.showCharts ??
        DEFAULT_DASHBOARD_PREFERENCES.showTimelineChart,
      showFileTypeChart:
        parsedPreferences.showFileTypeChart ??
        parsedPreferences.showCharts ??
        DEFAULT_DASHBOARD_PREFERENCES.showFileTypeChart,
      showFileTypeTable:
        parsedPreferences.showFileTypeTable ??
        DEFAULT_DASHBOARD_PREFERENCES.showFileTypeTable,
    };
  } catch {
    return DEFAULT_DASHBOARD_PREFERENCES;
  }
}

function loadCompactDashboardPreference(): boolean {
  try {
    const storedPreference = window.localStorage.getItem(
      COMPACT_DASHBOARD_STORAGE_KEY,
    );

    return storedPreference === null ? true : storedPreference === "true";
  } catch {
    return true;
  }
}

function topLabel(rows: CountRow[]): string {
  return rows[0]?.label ?? "No data yet";
}

function topCount(rows: CountRow[]): string | null {
  return rows[0] ? `${rows[0].count.toLocaleString()} photos` : null;
}

function TimelineTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload: TimelineInsightRow }>;
}) {
  if (!active || !payload?.length) {
    return null;
  }

  const row = payload[0].payload;

  return (
    <div className="chart-tooltip">
      <strong>{row.label}</strong>
      <span>{row.count.toLocaleString()} photos</span>
      {row.top_camera && <span>Top camera: {row.top_camera}</span>}
      {row.top_lens && <span>Top lens: {row.top_lens}</span>}
    </div>
  );
}

function formatScanStatus(status: string): string {
  switch (status) {
    case "completed":
      return "Completed";
    case "failed":
      return "Failed";
    case "interrupted":
      return "Interrupted";
    case "cancelled":
      return "Cancelled";
    case "running":
      return "Running";
    default:
      return status;
  }
}

function formatScanSpeed(value: number | null | undefined): string {
  if (!value || value <= 0) {
    return "0 files/sec";
  }

  return `${value.toLocaleString(undefined, {
    maximumFractionDigits: 1,
  })} files/sec`;
}

function formatScanSummary(status: ScanStatus): string {
  const summary = `${status.image_files_matched.toLocaleString()} matched, ${status.new_files.toLocaleString()} new, ${status.updated_files.toLocaleString()} updated, ${status.skipped_files.toLocaleString()} skipped, ${status.failed_files.toLocaleString()} failed at ${formatScanSpeed(status.scan_speed_files_per_second)}.`;

  switch (status.status) {
    case "completed":
      return `Scan complete for ${status.folder_path}. ${summary}`;
    case "cancelled":
      return `Scan cancelled for ${status.folder_path}. ${summary}`;
    case "failed":
      return `Scan failed for ${status.folder_path}. ${status.last_error ?? summary}`;
    case "interrupted":
      return `Scan interrupted for ${status.folder_path}. ${status.last_error ?? summary}`;
    default:
      return `Scan stopped for ${status.folder_path}. ${summary}`;
  }
}

function App() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [systemInfo, setSystemInfo] = useState<SystemInfo | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dashboardPreferences, setDashboardPreferences] =
    useState<DashboardPreferences>(loadDashboardPreferences);
  const [isCompactDashboard, setIsCompactDashboard] = useState(
    loadCompactDashboardPreference,
  );
  const [folderPath, setFolderPath] = useState("");
  const [refreshMetadata, setRefreshMetadata] = useState(false);
  const [isScanning, setIsScanning] = useState(false);
  const [scanMessage, setScanMessage] = useState<string | null>(null);
  const [scanError, setScanError] = useState<string | null>(null);
  const [lastScanSession, setLastScanSession] = useState<ScanSession | null>(null);
  const [scanHistory, setScanHistory] = useState<ScanSession[]>([]);
  const [isScanHistoryExpanded, setIsScanHistoryExpanded] = useState(false);
  const [activeScanId, setActiveScanId] = useState<number | null>(null);
  const [activeScanStatus, setActiveScanStatus] = useState<ScanStatus | null>(null);
  const [photoSearchFilters, setPhotoSearchFilters] = useState<PhotoSearchFilters>({
    camera_model: "",
    lens_model: "",
    min_focal_length: "",
    max_focal_length: "",
    date_from: "",
    date_to: "",
  });
  const [photoSearch, setPhotoSearch] = useState<PhotoSearchResponse | null>(null);
  const [isSearchingPhotos, setIsSearchingPhotos] = useState(false);
  const [photoSearchError, setPhotoSearchError] = useState<string | null>(null);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [activeTool, setActiveTool] = useState<ActiveTool>(null);
  const [isScanHistoryOpen, setIsScanHistoryOpen] = useState(false);
  const [pendingRescanPath, setPendingRescanPath] = useState<string | null>(null);

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

  const loadSystemInfo = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/system-info`);

      if (!response.ok) {
        throw new Error(`System info request failed with ${response.status}`);
      }

      setSystemInfo((await response.json()) as SystemInfo);
    } catch {
      setSystemInfo(null);
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

  const loadScanHistory = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/scan-sessions?limit=10`);

      if (!response.ok) {
        throw new Error(`Scan history request failed with ${response.status}`);
      }

      const data = (await response.json()) as { scan_sessions: ScanSession[] };
      setScanHistory(data.scan_sessions);
    } catch {
      setScanHistory([]);
    }
  }, []);

  const runPhotoSearch = useCallback(async () => {
    const params = new URLSearchParams({
      limit: String(Math.min(PHOTO_SEARCH_LIMIT, 500)),
      offset: "0",
    });

    Object.entries(photoSearchFilters).forEach(([key, value]) => {
      const trimmedValue = value.trim();

      if (trimmedValue) {
        params.set(key, trimmedValue);
      }
    });

    setIsSearchingPhotos(true);
    setPhotoSearchError(null);

    try {
      const response = await fetch(`${API_BASE_URL}/photos/search?${params}`);

      if (!response.ok) {
        let message = `Photo search failed with ${response.status}`;

        try {
          const errorBody = await response.json();
          message = errorBody.detail ?? message;
        } catch {
          // Keep the status-based message if the backend response is not JSON.
        }

        throw new Error(message);
      }

      setPhotoSearch((await response.json()) as PhotoSearchResponse);
    } catch (caughtError) {
      setPhotoSearchError(
        caughtError instanceof Error ? caughtError.message : "Unable to search photos.",
      );
    } finally {
      setIsSearchingPhotos(false);
    }
  }, [photoSearchFilters]);

  useEffect(() => {
    loadStats();
    void loadSystemInfo();
    void loadScanHistory();
  }, [loadScanHistory, loadStats, loadSystemInfo]);

  useEffect(() => {
    window.localStorage.setItem(
      DASHBOARD_PREFERENCES_STORAGE_KEY,
      JSON.stringify(dashboardPreferences),
    );
  }, [dashboardPreferences]);

  useEffect(() => {
    window.localStorage.setItem(
      COMPACT_DASHBOARD_STORAGE_KEY,
      String(isCompactDashboard),
    );
  }, [isCompactDashboard]);

  useEffect(() => {
    void loadLatestScanSession(folderPath);
  }, [folderPath, loadLatestScanSession]);

  useEffect(() => {
    if (activeScanId === null) {
      return;
    }

    let isCancelled = false;

    async function loadScanStatus() {
      try {
        const response = await fetch(`${API_BASE_URL}/scan-status/${activeScanId}`);

        if (!response.ok) {
          throw new Error(`Scan status request failed with ${response.status}`);
        }

        const status = (await response.json()) as ScanStatus;

        if (isCancelled) {
          return;
        }

        setActiveScanStatus(status);

        if (TERMINAL_SCAN_STATUSES.includes(status.status)) {
          setIsScanning(false);
          setActiveScanId(null);
          await loadLatestScanSession(status.folder_path);
          await loadScanHistory();
          await loadSystemInfo();

          if (status.status === "completed") {
            setScanMessage(formatScanSummary(status));
            await loadStats();
          } else if (status.status === "cancelled") {
            setScanMessage(formatScanSummary(status));
          } else {
            setScanError(formatScanSummary(status));
          }
        }
      } catch (caughtError) {
        if (!isCancelled) {
          setScanError(
            caughtError instanceof Error
              ? caughtError.message
              : "Unable to load scan status.",
          );
        }
      }
    }

    void loadScanStatus();
    const intervalId = window.setInterval(() => void loadScanStatus(), 2000);

    return () => {
      isCancelled = true;
      window.clearInterval(intervalId);
    };
  }, [
    activeScanId,
    loadLatestScanSession,
    loadScanHistory,
    loadStats,
    loadSystemInfo,
  ]);

  async function runScan({
    resume,
    confirmRescan = false,
    forceMetadataOverride,
    targetFolderPath,
  }: {
    resume: boolean;
    confirmRescan?: boolean;
    forceMetadataOverride?: boolean;
    targetFolderPath?: string;
  }) {
    const trimmedPath = (targetFolderPath ?? folderPath).trim();
    const forceMetadata = forceMetadataOverride ?? refreshMetadata;

    if (!trimmedPath) {
      setScanError("Enter a folder path to scan.");
      setScanMessage(null);
      return;
    }

    if (!resume && !confirmRescan && isPreviouslyScannedPath(trimmedPath)) {
      setPendingRescanPath(trimmedPath);
      setScanError(null);
      setScanMessage(null);
      return;
    }

    setPendingRescanPath(null);
    setIsScanning(true);
    setScanError(null);
    setScanMessage(null);

    try {
      const response = await fetch(
        `${API_BASE_URL}/scan-folder?folder_path=${encodeURIComponent(trimmedPath)}&resume=${resume}&force_metadata=${forceMetadata}`,
        { method: "POST" },
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

      const result = (await response.json()) as ScanStartResult;

      setActiveScanId(result.scan_id);
      setActiveScanStatus(null);
      setScanMessage(
        resume
          ? `Resume started for ${result.folder_path}.`
          : forceMetadata
            ? `Metadata refresh started for ${result.folder_path}.`
          : `Scan started for ${result.folder_path}.`,
      );
      setFolderPath(result.folder_path);
      await loadLatestScanSession(trimmedPath);
      await loadScanHistory();
      await loadSystemInfo();
    } catch (caughtError) {
      await loadLatestScanSession(trimmedPath);
      await loadScanHistory();
      setIsScanning(false);
      setScanError(
        caughtError instanceof Error
          ? `Could not start scan. ${caughtError.message}`
          : "Could not start scan. You can review the last scan status and resume it when ready.",
      );
    }
  }

  async function cancelActiveScan() {
    if (activeScanId === null) {
      return;
    }

    try {
      const response = await fetch(
        `${API_BASE_URL}/scan-sessions/${activeScanId}/cancel`,
        { method: "POST" },
      );

      if (!response.ok) {
        throw new Error(`Cancel request failed with ${response.status}`);
      }

      setScanMessage("Cancelling scan...");
      setScanError(null);
    } catch (caughtError) {
      setScanError(
        caughtError instanceof Error
          ? caughtError.message
          : "Unable to cancel scan.",
      );
    }
  }

  async function handleScanSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await runScan({ resume: false });
  }

  async function handlePhotoSearchSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await runPhotoSearch();
  }

  function updatePhotoSearchFilter(
    key: keyof PhotoSearchFilters,
    value: string,
  ) {
    setPhotoSearchFilters((currentFilters) => ({
      ...currentFilters,
      [key]: value,
    }));
  }

  function updateDashboardPreference(key: keyof DashboardPreferences) {
    setDashboardPreferences((currentPreferences) => ({
      ...currentPreferences,
      [key]: !currentPreferences[key],
    }));
  }

  function toggleTool(tool: Exclude<ActiveTool, null>) {
    setActiveTool((currentTool) => (currentTool === tool ? null : tool));
  }

  function normalizePath(value: string): string {
    return value.trim().replace(/[/\\]+$/, "").toLocaleLowerCase();
  }

  function isPreviouslyScannedPath(value: string): boolean {
    const normalizedValue = normalizePath(value);

    if (
      lastScanSession &&
      normalizePath(lastScanSession.folder_path) === normalizedValue
    ) {
      return true;
    }

    return scanHistory.some(
      (scanSession) => normalizePath(scanSession.folder_path) === normalizedValue,
    );
  }

  function openShortcut(target: "scan" | "search" | "insights" | "settings") {
    if (target === "scan" || target === "search") {
      setActiveTool(target);
      setIsSettingsOpen(false);
      window.setTimeout(
        () =>
          document
            .getElementById(
              `${target === "scan" ? "scan-library" : "photo-search"}-panel`,
            )
            ?.scrollIntoView({ behavior: "smooth", block: "start" }),
        0,
      );
      return;
    }

    if (target === "settings") {
      setIsSettingsOpen(true);
      setActiveTool(null);
      window.setTimeout(
        () =>
          document
            .getElementById("dashboard-settings")
            ?.scrollIntoView({ behavior: "smooth", block: "start" }),
        0,
      );
      return;
    }

    setActiveTool(null);
    setIsSettingsOpen(false);
    window.setTimeout(
      () =>
        document
          .getElementById("insights-section")
          ?.scrollIntoView({ behavior: "smooth", block: "start" }),
      0,
    );
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
  const cameraChartData = stats?.top_cameras.slice(0, 8) ?? [];
  const lensChartData = stats?.top_lenses.slice(0, 8) ?? [];
  const timelineChartData = stats?.photo_timeline ?? [];
  const showAnyStatCard =
    dashboardPreferences.showTotalPhotosCard ||
    dashboardPreferences.showTotalSizeCard ||
    dashboardPreferences.showNewestDateCard ||
    dashboardPreferences.showOldestDateCard ||
    dashboardPreferences.showFavoriteCameraCard ||
    dashboardPreferences.showFavoriteLensCard ||
    dashboardPreferences.showFocalLengthCard ||
    dashboardPreferences.showBusiestDateCard;
  const showAnyInsightChart =
    dashboardPreferences.showCameraChart ||
    dashboardPreferences.showLensChart ||
    dashboardPreferences.showTimelineChart ||
    dashboardPreferences.showFileTypeChart;
  const visibleCardCount = [
    dashboardPreferences.showTotalPhotosCard,
    dashboardPreferences.showTotalSizeCard,
    dashboardPreferences.showNewestDateCard,
    dashboardPreferences.showOldestDateCard,
    dashboardPreferences.showFavoriteCameraCard,
    dashboardPreferences.showFavoriteLensCard,
    dashboardPreferences.showFocalLengthCard,
    dashboardPreferences.showBusiestDateCard,
  ].filter(Boolean).length;
  const visibleInsightCount = [
    dashboardPreferences.showCameraChart,
    dashboardPreferences.showLensChart,
    dashboardPreferences.showTimelineChart,
    dashboardPreferences.showFileTypeChart,
    dashboardPreferences.showScanHistorySection,
    dashboardPreferences.showMetadataSearchSection,
    dashboardPreferences.showFileTypeTable,
  ].filter(Boolean).length;
  const hasInsightData = stats !== null && stats.total_photos > 0;
  const hasNoPhotoData = stats !== null && stats.total_photos === 0;

  const canResumeLastScan =
    lastScanSession !== null &&
    ["failed", "interrupted"].includes(lastScanSession.status);

  const canResumeScan = (scanSession: ScanSession) =>
    ["failed", "interrupted"].includes(scanSession.status);
  const latestScanHistoryItem = scanHistory[0] ?? null;

  return (
    <main className={`app-shell${isCompactDashboard ? " compact-mode" : ""}`}>
      <section className="page-header">
        <div>
          <p className="eyebrow">v1.0 local metadata intelligence</p>
          <h1>IMAGE INSIGHT</h1>
          <p className="page-subtitle">
            Scan local photo folders, inspect metadata, and monitor your library.
          </p>
        </div>
        <button
          type="button"
          className="settings-button"
          onClick={() => setIsSettingsOpen((currentValue) => !currentValue)}
        >
          {isSettingsOpen ? "Close Settings" : "Settings"}
        </button>
      </section>

      <nav className="quick-tools" aria-label="Dashboard shortcuts">
        <button type="button" onClick={() => openShortcut("scan")}>
          Scan Library
        </button>
        <button type="button" onClick={() => openShortcut("search")}>
          Metadata Search
        </button>
        <button type="button" onClick={() => openShortcut("insights")}>
          Insights
        </button>
        <button type="button" onClick={() => openShortcut("settings")}>
          Settings
        </button>
      </nav>

      {isLoading && <p className="state-message">Loading dashboard...</p>}

      {error && (
        <div className="error-panel">
          <strong>Could not load stats.</strong>
          <span>{error}</span>
        </div>
      )}

      {isSettingsOpen && (
        <section
          id="dashboard-settings"
          className="settings-panel"
          aria-label="Dashboard settings"
        >
          {systemInfo && (
            <section className="system-info-panel" aria-labelledby="system-info-heading">
              <div className="section-heading">
                <h2 id="system-info-heading">System Info</h2>
                <span>v{systemInfo.app_version}</span>
              </div>
              <dl className="system-info-grid">
                <div>
                  <dt>Database</dt>
                  <dd>{systemInfo.database_path}</dd>
                </div>
                <div>
                  <dt>Photos</dt>
                  <dd>{systemInfo.photo_count.toLocaleString()}</dd>
                </div>
                <div>
                  <dt>Scan sessions</dt>
                  <dd>{systemInfo.scan_session_count.toLocaleString()}</dd>
                </div>
                <div>
                  <dt>ExifTool</dt>
                  <dd>
                    {systemInfo.exiftool_available ? "Detected" : "Not detected"}
                  </dd>
                </div>
              </dl>
            </section>
          )}

          <section className="customize-section" aria-labelledby="customize-heading">
            <div className="section-heading">
              <h2 id="customize-heading">Customize Dashboard</h2>
              <span>{visibleCardCount + visibleInsightCount} visible items</span>
            </div>
            <div className="customize-grid">
              <div className="customize-group">
                <strong>Cards</strong>
                <div className="customize-controls">
                  <label>
                    <input
                      type="checkbox"
                      checked={dashboardPreferences.showTotalPhotosCard}
                      onChange={() =>
                        updateDashboardPreference("showTotalPhotosCard")
                      }
                    />
                    Total photos
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      checked={dashboardPreferences.showTotalSizeCard}
                      onChange={() =>
                        updateDashboardPreference("showTotalSizeCard")
                      }
                    />
                    Total size
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      checked={dashboardPreferences.showNewestDateCard}
                      onChange={() =>
                        updateDashboardPreference("showNewestDateCard")
                      }
                    />
                    Newest date
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      checked={dashboardPreferences.showOldestDateCard}
                      onChange={() =>
                        updateDashboardPreference("showOldestDateCard")
                      }
                    />
                    Oldest date
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      checked={dashboardPreferences.showFavoriteCameraCard}
                      onChange={() =>
                        updateDashboardPreference("showFavoriteCameraCard")
                      }
                    />
                    Favorite camera
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      checked={dashboardPreferences.showFavoriteLensCard}
                      onChange={() =>
                        updateDashboardPreference("showFavoriteLensCard")
                      }
                    />
                    Favorite lens
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      checked={dashboardPreferences.showFocalLengthCard}
                      onChange={() =>
                        updateDashboardPreference("showFocalLengthCard")
                      }
                    />
                    Focal length
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      checked={dashboardPreferences.showBusiestDateCard}
                      onChange={() =>
                        updateDashboardPreference("showBusiestDateCard")
                      }
                    />
                    Busiest date
                  </label>
                </div>
              </div>
              <div className="customize-group">
                <strong>Sections</strong>
                <div className="customize-controls">
                  <label>
                    <input
                      type="checkbox"
                      checked={dashboardPreferences.showCameraChart}
                      onChange={() => updateDashboardPreference("showCameraChart")}
                    />
                    Camera chart
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      checked={dashboardPreferences.showLensChart}
                      onChange={() => updateDashboardPreference("showLensChart")}
                    />
                    Lens chart
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      checked={dashboardPreferences.showTimelineChart}
                      onChange={() =>
                        updateDashboardPreference("showTimelineChart")
                      }
                    />
                    Timeline insight
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      checked={dashboardPreferences.showFileTypeChart}
                      onChange={() =>
                        updateDashboardPreference("showFileTypeChart")
                      }
                    />
                    File type chart
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      checked={dashboardPreferences.showScanHistorySection}
                      onChange={() =>
                        updateDashboardPreference("showScanHistorySection")
                      }
                    />
                    Scan history
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      checked={dashboardPreferences.showMetadataSearchSection}
                      onChange={() =>
                        updateDashboardPreference("showMetadataSearchSection")
                      }
                    />
                    Metadata search
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      checked={dashboardPreferences.showFileTypeTable}
                      onChange={() =>
                        updateDashboardPreference("showFileTypeTable")
                      }
                    />
                    File type table
                  </label>
                </div>
              </div>
            </div>
          </section>
        </section>
      )}

      {hasInsightData && stats && (
        <section
          id="insights-section"
          className="dashboard-section insights-section"
          aria-labelledby="insights-heading"
        >
          <div className="dashboard-section-heading">
            <div>
              <h2 id="insights-heading">Insights</h2>
              <span>Stats and charts from indexed photos</span>
            </div>
          </div>

          {showAnyStatCard && (
            <section className="stats-grid" aria-label="Photo library stats">
              {dashboardPreferences.showTotalPhotosCard && (
                <article className="stat-card">
                  <span>Total Photos</span>
                  <strong>{stats.total_photos.toLocaleString()}</strong>
                </article>
              )}
              {dashboardPreferences.showTotalSizeCard && (
                <article className="stat-card">
                  <span>Total Size</span>
                  <strong>{formatGigabytes(stats.total_size_bytes)}</strong>
                  <small>{formatBytes(stats.total_size_bytes)} bytes</small>
                </article>
              )}
              {dashboardPreferences.showNewestDateCard && (
                <article className="stat-card">
                  <span>Newest Date</span>
                  <strong>{formatDate(stats.newest_modified_at)}</strong>
                </article>
              )}
              {dashboardPreferences.showOldestDateCard && (
                <article className="stat-card">
                  <span>Oldest Date</span>
                  <strong>{formatDate(stats.oldest_modified_at)}</strong>
                </article>
              )}
              {dashboardPreferences.showFavoriteCameraCard && (
                <article className="stat-card">
                  <span>Favorite Camera</span>
                  <strong>{topLabel(stats.top_cameras)}</strong>
                  {topCount(stats.top_cameras) && (
                    <small>{topCount(stats.top_cameras)}</small>
                  )}
                </article>
              )}
              {dashboardPreferences.showFavoriteLensCard && (
                <article className="stat-card">
                  <span>Favorite Lens</span>
                  <strong>{topLabel(stats.top_lenses)}</strong>
                  {topCount(stats.top_lenses) && (
                    <small>{topCount(stats.top_lenses)}</small>
                  )}
                </article>
              )}
              {dashboardPreferences.showFocalLengthCard && (
                <article className="stat-card">
                  <span>Most Used Focal Length</span>
                  <strong>{topLabel(stats.top_focal_lengths)}</strong>
                  {topCount(stats.top_focal_lengths) && (
                    <small>{topCount(stats.top_focal_lengths)}</small>
                  )}
                </article>
              )}
              {dashboardPreferences.showBusiestDateCard && (
                <article className="stat-card">
                  <span>Busiest Date</span>
                  <strong>
                    {formatCalendarDate(stats.busiest_date?.label ?? null)}
                  </strong>
                  {stats.busiest_date && (
                    <small>{stats.busiest_date.count.toLocaleString()} photos</small>
                  )}
                </article>
              )}
            </section>
          )}

          {showAnyInsightChart && (
            <>
              {(dashboardPreferences.showCameraChart ||
                dashboardPreferences.showLensChart) && (
              <div className="chart-grid">
                {dashboardPreferences.showCameraChart && (
                <section className="chart-section">
                  <div className="section-heading">
                    <h2>Camera Usage</h2>
                    <span>{cameraChartData.length} cameras</span>
                  </div>

                  {cameraChartData.length > 0 ? (
                    <div className="chart-frame">
                      <ResponsiveContainer width="100%" height={280}>
                        <BarChart data={cameraChartData}>
                          <CartesianGrid stroke="#273244" vertical={false} />
                          <XAxis dataKey="label" stroke="#a7b3c6" tickLine={false} axisLine={false} />
                          <YAxis allowDecimals={false} stroke="#a7b3c6" tickLine={false} axisLine={false} />
                          <Tooltip cursor={{ fill: "rgba(125, 211, 252, 0.1)" }} contentStyle={{ background: "#121a26", border: "1px solid #2f3d52", borderRadius: "8px", color: "#edf5ff" }} />
                          <Bar dataKey="count" fill="#7dd3fc" radius={[6, 6, 0, 0]} />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  ) : (
                    <p className="empty-chart">Run a scan with EXIF data to populate camera usage.</p>
                  )}
                </section>
                )}

                {dashboardPreferences.showLensChart && (
                <section className="chart-section">
                  <div className="section-heading">
                    <h2>Lens Usage</h2>
                    <span>{lensChartData.length} lenses</span>
                  </div>

                  {lensChartData.length > 0 ? (
                    <div className="chart-frame">
                      <ResponsiveContainer width="100%" height={280}>
                        <BarChart data={lensChartData}>
                          <CartesianGrid stroke="#273244" vertical={false} />
                          <XAxis dataKey="label" stroke="#a7b3c6" tickLine={false} axisLine={false} />
                          <YAxis allowDecimals={false} stroke="#a7b3c6" tickLine={false} axisLine={false} />
                          <Tooltip cursor={{ fill: "rgba(169, 135, 255, 0.1)" }} contentStyle={{ background: "#121a26", border: "1px solid #2f3d52", borderRadius: "8px", color: "#edf5ff" }} />
                          <Bar dataKey="count" fill="#8fb6ff" radius={[6, 6, 0, 0]} />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  ) : (
                    <p className="empty-chart">Run a scan with EXIF data to populate lens usage.</p>
                  )}
                </section>
                )}
              </div>
              )}

              {dashboardPreferences.showTimelineChart &&
                timelineChartData.length > 0 && (
              <section className="chart-section">
                <div className="section-heading">
                  <div>
                    <h2>Capture Timeline where available</h2>
                    <span>
                      Imported or exported archives may contain added/export dates
                      instead of true capture dates.
                    </span>
                  </div>
                  <span>{timelineChartData.length} months</span>
                </div>

                <div className="chart-frame">
                  <ResponsiveContainer width="100%" height={280}>
                    <LineChart data={timelineChartData}>
                      <CartesianGrid stroke="#273244" vertical={false} />
                      <XAxis dataKey="label" stroke="#a7b3c6" tickLine={false} axisLine={false} />
                      <YAxis allowDecimals={false} stroke="#a7b3c6" tickLine={false} axisLine={false} />
                      <Tooltip content={<TimelineTooltip />} />
                      <Line type="monotone" dataKey="count" stroke="#a987ff" strokeWidth={3} dot={{ r: 3 }} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </section>
              )}

              {dashboardPreferences.showFileTypeChart && (
              <section className="chart-section">
                <div className="section-heading">
                  <h2>File Type Distribution</h2>
                  <span>{fileTypeRows.length} types</span>
                </div>

                {fileTypeChartData.length > 0 ? (
                  <div className="chart-frame compact-chart">
                    <ResponsiveContainer width="100%" height={240}>
                      <BarChart data={fileTypeChartData}>
                        <CartesianGrid stroke="#273244" vertical={false} />
                        <XAxis dataKey="extension" stroke="#a7b3c6" tickLine={false} axisLine={false} />
                        <YAxis allowDecimals={false} stroke="#a7b3c6" tickLine={false} axisLine={false} />
                        <Tooltip cursor={{ fill: "rgba(125, 211, 252, 0.1)" }} contentStyle={{ background: "#121a26", border: "1px solid #2f3d52", borderRadius: "8px", color: "#edf5ff" }} />
                        <Bar dataKey="count" fill="#7dd3fc" radius={[6, 6, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                ) : (
                  <p className="empty-chart">Run a scan to populate file type data.</p>
                )}
              </section>
              )}
            </>
          )}

          {dashboardPreferences.showFileTypeTable && (
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
          )}
        </section>
      )}

      <section className="dashboard-section tools-section" aria-labelledby="tools-heading">
        <div className="dashboard-section-heading">
          <div>
            <h2 id="tools-heading">Tools</h2>
            <span>Open scan or search workspaces</span>
          </div>
        </div>

        {hasNoPhotoData && (
          <div className="onboarding-empty-state">
            <strong>Start by scanning a folder.</strong>
            <span>
              Image Insight needs an indexed photo folder before insights, search,
              and scan history become useful.
            </span>
          </div>
        )}

        <div className="tool-card-grid">
          <button
            type="button"
            className={`tool-card scan-card${activeTool === "scan" ? " active" : ""}${hasNoPhotoData ? " recommended" : ""}`}
            onClick={() => toggleTool("scan")}
            aria-controls="scan-library-panel"
            aria-expanded={activeTool === "scan"}
          >
            <span className="tool-card-icon" aria-hidden="true" />
            <span className="tool-card-copy">
              <strong>Scan Library</strong>
              <span>Run new scans, refresh metadata, and review scan history.</span>
            </span>
          </button>

          <button
            type="button"
            className={`tool-card search-card${activeTool === "search" ? " active" : ""}`}
            onClick={() => toggleTool("search")}
            aria-controls="photo-search-panel"
            aria-expanded={activeTool === "search"}
          >
            <span className="tool-card-icon" aria-hidden="true" />
            <span className="tool-card-copy">
              <strong>Metadata Search</strong>
              <span>Filter indexed photos by EXIF details.</span>
            </span>
          </button>
        </div>

        {!activeTool && (
          <p className="state-message">Choose a tool above to open its workspace.</p>
        )}
      </section>

      {activeTool === "scan" && (
      <section
        id="scan-library-panel"
        className="scan-section tool-detail"
        aria-labelledby="scan-library-heading"
      >
        <div className="section-heading scan-heading">
          <div>
            <h2 id="scan-library-heading">Scan Library</h2>
            <span>Start a scan or review recent scan activity</span>
          </div>
        </div>

        <div className="scan-subsection">
          <h3>New Scan</h3>
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
          <label className="scan-option">
            <input
              type="checkbox"
              checked={refreshMetadata}
              onChange={(event) => setRefreshMetadata(event.target.checked)}
              disabled={isScanning}
            />
            Refresh metadata
          </label>
        </form>
        </div>

        {pendingRescanPath && (
          <div className="rescan-warning" role="alert">
            <strong>This directory was previously scanned.</strong>
            <span>
              Choose how to continue for {pendingRescanPath}. A scan will not start
              until you pick one of these actions.
            </span>
            <div className="rescan-actions">
              <button
                type="button"
                onClick={() =>
                  void runScan({
                    resume: false,
                    confirmRescan: true,
                    forceMetadataOverride: true,
                    targetFolderPath: pendingRescanPath,
                  })
                }
                disabled={isScanning}
              >
                Refresh metadata
              </button>
              <button
                type="button"
                onClick={() =>
                  void runScan({
                    resume: false,
                    confirmRescan: true,
                    forceMetadataOverride: false,
                    targetFolderPath: pendingRescanPath,
                  })
                }
                disabled={isScanning}
              >
                Scan anyway
              </button>
              <button
                type="button"
                className="secondary-button"
                onClick={() => setPendingRescanPath(null)}
              >
                Cancel
              </button>
            </div>
          </div>
        )}

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
              {lastScanSession.failed_files.toLocaleString()}, speed:{" "}
              {formatScanSpeed(lastScanSession.scan_speed_files_per_second)}.
            </p>
            {(lastScanSession.force_metadata ||
              lastScanSession.exiftool_available) && (
              <p className="scan-history-note">
                {lastScanSession.exiftool_available
                  ? "ExifTool enabled."
                  : "ExifTool not detected."}{" "}
                {lastScanSession.force_metadata
                  ? "Metadata backfill was enabled."
                  : ""}
              </p>
            )}
            {lastScanSession.last_error && (
              <p className="scan-history-note">
                Last error: {lastScanSession.last_error}
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
              Scan running in the background. Progress updates every few seconds.
            </span>
            <span className="scan-progress-detail">
              {(activeScanStatus?.exiftool_available ??
                systemInfo?.exiftool_available)
                ? "ExifTool enabled"
                : "ExifTool not detected"}
            </span>
            {(activeScanStatus?.force_metadata ?? refreshMetadata) && (
              <span className="scan-progress-detail">Metadata backfill enabled</span>
            )}
            <button
              type="button"
              className="secondary-button"
              onClick={() => void cancelActiveScan()}
              disabled={activeScanId === null}
            >
              Cancel Scan
            </button>
          </div>
        )}

        {activeScanStatus && (
          <div className="scan-live-panel" aria-label="Live scan progress">
            <div>
              <span>Files Seen</span>
              <strong>{activeScanStatus.files_seen.toLocaleString()}</strong>
            </div>
            <div>
              <span>Matched</span>
              <strong>{activeScanStatus.image_files_matched.toLocaleString()}</strong>
            </div>
            <div>
              <span>New</span>
              <strong>{activeScanStatus.new_files.toLocaleString()}</strong>
            </div>
            <div>
              <span>Updated</span>
              <strong>{activeScanStatus.updated_files.toLocaleString()}</strong>
            </div>
            <div>
              <span>Skipped</span>
              <strong>{activeScanStatus.skipped_files.toLocaleString()}</strong>
            </div>
            <div>
              <span>Failed</span>
              <strong>{activeScanStatus.failed_files.toLocaleString()}</strong>
            </div>
            <div>
              <span>Speed</span>
              <strong>
                {formatScanSpeed(activeScanStatus.scan_speed_files_per_second)}
              </strong>
            </div>
          </div>
        )}

        {activeScanStatus?.last_error && (
          <p className="scan-feedback failure">{activeScanStatus.last_error}</p>
        )}

        {scanMessage && <p className="scan-feedback success">{scanMessage}</p>}
        {scanError && <p className="scan-feedback failure">{scanError}</p>}

        <div className="scan-history-toggle">
          <button
            type="button"
            className="small-action-button"
            onClick={() => setIsScanHistoryOpen((currentValue) => !currentValue)}
            aria-expanded={isScanHistoryOpen}
            aria-controls="scan-history-panel"
          >
            {isScanHistoryOpen ? "Hide Scan History" : "Show Scan History"}
          </button>
          <span>{scanHistory.length.toLocaleString()} recent scans</span>
        </div>

        {isScanHistoryOpen && (
      <section id="scan-history-panel" className="table-section embedded-history">
        <table>
          <thead>
            <tr>
              <th>Status</th>
              <th>Folder</th>
              <th>Matched</th>
              <th>Changes</th>
              <th>Duration</th>
              <th>Completed</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {scanHistory.length > 0 ? (
              scanHistory.map((scanSession) => (
                <tr key={scanSession.scan_id}>
                  <td>
                    <span className={`scan-status ${scanSession.status}`}>
                      {formatScanStatus(scanSession.status)}
                    </span>
                  </td>
                  <td>{scanSession.folder_path}</td>
                  <td>{scanSession.image_files_matched.toLocaleString()}</td>
                  <td>
                    {scanSession.new_files.toLocaleString()} new,{" "}
                    {scanSession.updated_files.toLocaleString()} updated,{" "}
                    {scanSession.failed_files.toLocaleString()} failed
                  </td>
                  <td>{scanSession.elapsed_seconds.toFixed(2)}s</td>
                  <td>{formatDate(scanSession.completed_at)}</td>
                  <td>
                    <div className="table-actions">
                      <button
                        type="button"
                        className="small-action-button"
                        onClick={() =>
                          void runScan({
                            resume: false,
                            confirmRescan: true,
                            targetFolderPath: scanSession.folder_path,
                          })
                        }
                        disabled={isScanning}
                      >
                        Rerun
                      </button>
                      {canResumeScan(scanSession) && (
                        <button
                          type="button"
                          className="small-action-button"
                          onClick={() =>
                            void runScan({
                              resume: true,
                              targetFolderPath: scanSession.folder_path,
                            })
                          }
                          disabled={isScanning}
                        >
                          Resume
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={7}>
                  No scan history yet. Start with a local photo folder above.
                </td>
              </tr>
            )}
          </tbody>
        </table>
        )}
      </section>
        )}
      </section>
      )}

      {activeTool === "search" && (
      <section
        id="photo-search-panel"
        className="search-section tool-detail"
        aria-labelledby="photo-search-heading"
      >
        <div className="section-heading scan-heading">
          <div>
            <h2 id="photo-search-heading">Metadata Search</h2>
            <span>Filter indexed photos by EXIF metadata</span>
          </div>
        </div>

        <form className="search-form" onSubmit={handlePhotoSearchSubmit}>
          <label>
            Camera
            <input
              type="text"
              value={photoSearchFilters.camera_model}
              onChange={(event) =>
                updatePhotoSearchFilter("camera_model", event.target.value)
              }
              placeholder="EOS R5"
            />
          </label>
          <label>
            Lens
            <input
              type="text"
              value={photoSearchFilters.lens_model}
              onChange={(event) =>
                updatePhotoSearchFilter("lens_model", event.target.value)
              }
              placeholder="RF50"
            />
          </label>
          <label>
            Min Focal
            <input
              type="number"
              min="0"
              step="0.1"
              value={photoSearchFilters.min_focal_length}
              onChange={(event) =>
                updatePhotoSearchFilter("min_focal_length", event.target.value)
              }
              placeholder="24"
            />
          </label>
          <label>
            Max Focal
            <input
              type="number"
              min="0"
              step="0.1"
              value={photoSearchFilters.max_focal_length}
              onChange={(event) =>
                updatePhotoSearchFilter("max_focal_length", event.target.value)
              }
              placeholder="85"
            />
          </label>
          <label>
            From
            <input
              type="date"
              value={photoSearchFilters.date_from}
              onChange={(event) =>
                updatePhotoSearchFilter("date_from", event.target.value)
              }
            />
          </label>
          <label>
            To
            <input
              type="date"
              value={photoSearchFilters.date_to}
              onChange={(event) =>
                updatePhotoSearchFilter("date_to", event.target.value)
              }
            />
          </label>
          <button type="submit" disabled={isSearchingPhotos}>
            {isSearchingPhotos ? "Searching..." : "Search"}
          </button>
        </form>

        {photoSearchError && (
          <p className="scan-feedback failure">{photoSearchError}</p>
        )}

        {photoSearch && (
          <div className="search-results">
            <div className="search-results-summary">
              <strong>{photoSearch.total_count.toLocaleString()} matches</strong>
              <span>Showing {photoSearch.results.length.toLocaleString()}</span>
            </div>
            <table>
              <thead>
                <tr>
                  <th>File</th>
                  <th>Camera</th>
                  <th>Lens</th>
                  <th>Focal</th>
                  <th>Date Taken</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {photoSearch.results.length > 0 ? (
                  photoSearch.results.map((photo) => (
                    <tr key={photo.id}>
                      <td>{photo.filename}</td>
                      <td>{formatOptional(photo.camera_model)}</td>
                      <td>{formatOptional(photo.lens_model)}</td>
                      <td>{formatFocalLength(photo.focal_length)}</td>
                      <td>{formatDate(photo.date_taken)}</td>
                      <td>
                        <button
                          type="button"
                          className="small-action-button"
                          onClick={() => void copyPhotoPath(photo)}
                        >
                          {copiedPhotoId === photo.id ? "Copied" : "Copy Path"}
                        </button>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={6}>
                      No matching photos. Try clearing a filter or widening the date
                      or focal length range.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </section>
      )}
    </main>
  );
}

export default App;
