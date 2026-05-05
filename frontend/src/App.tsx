import { useCallback, useEffect, useMemo, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import {
  Bar,
  BarChart,
  Cell,
  CartesianGrid,
  Pie,
  PieChart,
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

type SizeRow = {
  label: string;
  size_bytes: number;
};

type AverageFileSizeByCameraRow = {
  label: string;
  average_file_size_bytes: number;
  count: number;
};

type TimelineInsightRow = CountRow & {
  top_camera: string | null;
  top_lens: string | null;
};

type UsageTimelineRow = {
  label: string;
  [series: string]: string | number;
};

type Stats = {
  total_photos: number;
  total_size_bytes: number;
  average_file_size_bytes: number;
  file_type_counts: Record<string, number>;
  storage_by_file_type: SizeRow[];
  average_file_size_by_file_type: AverageFileSizeByCameraRow[];
  raw_vs_jpeg_counts: Record<"raw" | "jpeg" | "other", number>;
  phone_vs_camera_counts: Record<"phone" | "camera" | "unknown", number>;
  top_cameras: CountRow[];
  top_lenses: CountRow[];
  top_focal_lengths: CountRow[];
  most_common_iso: CountRow | null;
  most_common_aperture: CountRow | null;
  most_common_shutter_speed: CountRow | null;
  average_file_size_by_camera: AverageFileSizeByCameraRow[];
  top_capture_dates: CountRow[];
  iso_distribution: CountRow[];
  aperture_distribution: CountRow[];
  shutter_speed_buckets: CountRow[];
  focal_length_usage_over_time: UsageTimelineRow[];
  photos_with_capture_date: number;
  photos_missing_capture_date: number;
  photos_by_year: CountRow[];
  photos_by_month: CountRow[];
  photo_timeline: TimelineInsightRow[];
  camera_usage_timeline: UsageTimelineRow[];
  lens_usage_timeline: UsageTimelineRow[];
  busiest_date: CountRow | null;
  newest_modified_at: string | null;
  oldest_modified_at: string | null;
};

type PhotoSearchResult = {
  id: number;
  filename: string;
  path: string;
  extension: string;
  size_bytes: number;
  camera_model: string | null;
  lens_model: string | null;
  focal_length: number | null;
  iso: number | null;
  aperture: number | null;
  shutter_speed: string | null;
  date_taken: string | null;
  device_type: string;
};

type PhotoSearchResponse = {
  total_count: number;
  limit: number;
  offset: number;
  sort_by: string;
  sort_order: string;
  results: PhotoSearchResult[];
};

type PhotoSearchFilters = {
  camera_model: string;
  lens_model: string;
  min_focal_length: string;
  max_focal_length: string;
  extension: string;
  iso: string;
  aperture: string;
  shutter_speed: string;
  date_from: string;
  date_to: string;
  device_type: string;
  sort_by: string;
  sort_order: string;
};

type PhotoSearchOptions = {
  camera_models?: string[];
  lens_models?: string[];
  cameras: string[];
  lenses: string[];
  extensions: string[];
  iso_values: number[];
  aperture_values: number[];
  shutter_speed_values: string[];
  device_types: string[];
};

type AnalyticsResponse = {
  x_axis: string;
  metric: string;
  group_by: string | null;
  limit: number;
  offset: number;
  total_count: number;
  series: string[];
  rows: UsageTimelineRow[];
};

type AnalyticsFilters = {
  x_axis: string;
  metric: string;
  group_by: string;
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
  showAverageFileSizeCard: boolean;
  showTopStorageTypeCard: boolean;
  showRawJpegCard: boolean;
  showDeviceTypeCard: boolean;
  showMostCommonIsoCard: boolean;
  showMostCommonApertureCard: boolean;
  showMostCommonShutterCard: boolean;
  showAverageCameraSizeCard: boolean;
  showScanHistorySection: boolean;
  showMetadataSearchSection: boolean;
  showCameraChart: boolean;
  showLensChart: boolean;
  showTimelineChart: boolean;
  showFileTypeChart: boolean;
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

type ActiveTool = "scan" | "search" | "analytics" | null;

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
const TERMINAL_SCAN_STATUSES = ["completed", "failed", "interrupted", "cancelled"];
const PHOTO_SEARCH_LIMIT = 25;
const DASHBOARD_PREFERENCES_STORAGE_KEY = "image-insight-dashboard-preferences";
const COMPACT_DASHBOARD_STORAGE_KEY = "image-insight-compact-dashboard";
const SEARCH_COLUMNS_STORAGE_KEY = "image-insight-search-columns";
const CHART_SERIES_COLORS = [
  "#7dd3fc",
  "#a987ff",
  "#fbbf24",
  "#4ade80",
  "#f472b6",
  "#fb7185",
  "#38bdf8",
  "#c084fc",
  "#f97316",
  "#2dd4bf",
  "#e879f9",
  "#a3e635",
];
const SEARCH_SORT_FIELDS = [
  "date_taken",
  "camera_model",
  "lens_model",
  "focal_length",
  "iso",
  "aperture",
  "shutter_speed",
  "size_bytes",
  "extension",
  "device_type",
];
const DEFAULT_SEARCH_COLUMNS = [
  "filename",
  "extension",
  "size_bytes",
  "camera_model",
  "lens_model",
  "focal_length",
  "iso",
  "aperture",
  "shutter_speed",
  "date_taken",
  "device_type",
];
const SEARCH_COLUMN_LABELS: Record<string, string> = {
  filename: "File",
  extension: "Type",
  size_bytes: "Size",
  camera_model: "Camera",
  lens_model: "Lens",
  focal_length: "Focal",
  iso: "ISO",
  aperture: "Aperture",
  shutter_speed: "Shutter",
  date_taken: "Date Taken",
  device_type: "Device",
};
const ANALYTICS_DIMENSIONS = [
  "capture_month",
  "capture_date",
  "camera_model",
  "lens_model",
  "extension",
  "device_type",
  "iso",
  "aperture",
  "shutter_speed_bucket",
  "focal_length_bucket",
];
const ANALYTICS_GROUP_BY = ["camera_model", "lens_model", "extension", "device_type"];
const ANALYTICS_METRICS = ["photo_count", "avg_file_size", "total_file_size"];
const ANALYTICS_TIME_DIMENSIONS = new Set(["capture_month", "capture_date"]);
const DEFAULT_DASHBOARD_PREFERENCES: DashboardPreferences = {
  showTotalPhotosCard: true,
  showTotalSizeCard: true,
  showNewestDateCard: true,
  showOldestDateCard: true,
  showFavoriteCameraCard: true,
  showFavoriteLensCard: true,
  showFocalLengthCard: true,
  showBusiestDateCard: true,
  showAverageFileSizeCard: true,
  showTopStorageTypeCard: true,
  showRawJpegCard: true,
  showDeviceTypeCard: true,
  showMostCommonIsoCard: true,
  showMostCommonApertureCard: true,
  showMostCommonShutterCard: true,
  showAverageCameraSizeCard: true,
  showScanHistorySection: true,
  showMetadataSearchSection: true,
  showCameraChart: true,
  showLensChart: true,
  showTimelineChart: true,
  showFileTypeChart: true,
};

function formatBytes(bytes: number): string {
  return new Intl.NumberFormat("en-US").format(bytes);
}

function formatGigabytes(bytes: number): string {
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
}

function formatMegabytes(bytes: number): string {
  return `${(bytes / 1024 ** 2).toFixed(2)} MB`;
}

function formatDate(value: string | null): string {
  if (!value) {
    return "No data yet";
  }

  const timestampHasTimezone = /(?:z|[+-]\d{2}:?\d{2})$/i.test(value);
  const date = new Date(timestampHasTimezone ? value : `${value}Z`);

  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
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

function formatSearchCell(photo: PhotoSearchResult, column: string): string {
  if (column === "filename") {
    return photo.filename;
  }
  if (column === "extension") {
    return photo.extension.toUpperCase();
  }
  if (column === "size_bytes") {
    return formatMegabytes(photo.size_bytes);
  }
  if (column === "camera_model") {
    return formatOptional(photo.camera_model);
  }
  if (column === "lens_model") {
    return formatOptional(photo.lens_model);
  }
  if (column === "focal_length") {
    return formatFocalLength(photo.focal_length);
  }
  if (column === "iso") {
    return formatOptional(photo.iso);
  }
  if (column === "aperture") {
    return photo.aperture === null ? "—" : `f/${photo.aperture}`;
  }
  if (column === "shutter_speed") {
    return formatOptional(photo.shutter_speed);
  }
  if (column === "date_taken") {
    return formatDate(photo.date_taken);
  }
  if (column === "device_type") {
    return photo.device_type;
  }

  return "";
}

type ChartTooltipPayload = {
  name?: string | number;
  value?: string | number;
  color?: string;
  stroke?: string;
};

function SeriesTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: ChartTooltipPayload[];
  label?: string | number;
}) {
  if (!active || !payload?.length) {
    return null;
  }

  return (
    <div className="series-tooltip">
      <strong>{label}</strong>
      {payload
        .filter((item) => item.value !== undefined && item.value !== null)
        .map((item) => (
          <span key={String(item.name)}>
            <i
              aria-hidden="true"
              style={{ background: item.color ?? item.stroke ?? "#7dd3fc" }}
            />
            {item.name}: {item.value}
          </span>
        ))}
    </div>
  );
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
      showAverageFileSizeCard:
        parsedPreferences.showAverageFileSizeCard ??
        DEFAULT_DASHBOARD_PREFERENCES.showAverageFileSizeCard,
      showTopStorageTypeCard:
        parsedPreferences.showTopStorageTypeCard ??
        DEFAULT_DASHBOARD_PREFERENCES.showTopStorageTypeCard,
      showRawJpegCard:
        parsedPreferences.showRawJpegCard ??
        DEFAULT_DASHBOARD_PREFERENCES.showRawJpegCard,
      showDeviceTypeCard:
        parsedPreferences.showDeviceTypeCard ??
        DEFAULT_DASHBOARD_PREFERENCES.showDeviceTypeCard,
      showMostCommonIsoCard:
        parsedPreferences.showMostCommonIsoCard ??
        DEFAULT_DASHBOARD_PREFERENCES.showMostCommonIsoCard,
      showMostCommonApertureCard:
        parsedPreferences.showMostCommonApertureCard ??
        DEFAULT_DASHBOARD_PREFERENCES.showMostCommonApertureCard,
      showMostCommonShutterCard:
        parsedPreferences.showMostCommonShutterCard ??
        DEFAULT_DASHBOARD_PREFERENCES.showMostCommonShutterCard,
      showAverageCameraSizeCard:
        parsedPreferences.showAverageCameraSizeCard ??
        DEFAULT_DASHBOARD_PREFERENCES.showAverageCameraSizeCard,
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

function usageTimelineKeys(rows: UsageTimelineRow[]): string[] {
  return Array.from(
    new Set(
      rows.flatMap((row) => Object.keys(row).filter((key) => key !== "label")),
    ),
  );
}

function formatOptionLabel(value: string): string {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function loadSearchColumns(): string[] {
  try {
    const storedColumns = window.localStorage.getItem(SEARCH_COLUMNS_STORAGE_KEY);
    if (!storedColumns) {
      return DEFAULT_SEARCH_COLUMNS;
    }

    const parsedColumns = JSON.parse(storedColumns);
    if (!Array.isArray(parsedColumns)) {
      return DEFAULT_SEARCH_COLUMNS;
    }

    return parsedColumns.filter((column) => column in SEARCH_COLUMN_LABELS);
  } catch {
    return DEFAULT_SEARCH_COLUMNS;
  }
}

function topStorageLabel(rows: SizeRow[]): string {
  const row = rows[0];

  if (!row) {
    return "No data yet";
  }

  return `${row.label.toUpperCase()} ${formatGigabytes(row.size_bytes)}`;
}

function topAverageCameraSize(rows: AverageFileSizeByCameraRow[]): string {
  const row = rows[0];

  if (!row) {
    return "No data yet";
  }

  return row.label;
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
  switch (status.status) {
    case "completed":
      return `Scan complete for ${status.folder_path}.`;
    case "cancelled":
      return `Scan cancelled for ${status.folder_path}.`;
    case "failed":
      return `Scan failed for ${status.folder_path}. ${
        status.last_error ?? "Review Scan History for details."
      }`;
    case "interrupted":
      return `Scan interrupted for ${status.folder_path}. ${
        status.last_error ?? "Review Scan History for details."
      }`;
    default:
      return `Scan stopped for ${status.folder_path}.`;
  }
}

function InfoTip({ label, children }: { label: string; children: ReactNode }) {
  return (
    <span className="info-tip">
      <button type="button" aria-label={label}>
        i
      </button>
      <span role="tooltip">{children}</span>
    </span>
  );
}

function ScanLibraryInfoTip() {
  return (
    <InfoTip label="Scan Library terminology">
      <ul>
        <li>Files seen: files inspected.</li>
        <li>Matched: supported image files.</li>
        <li>New: newly indexed images.</li>
        <li>Updated: changed image metadata.</li>
        <li>Skipped: unchanged matched images.</li>
        <li>Failed: files that could not be processed.</li>
        <li>Speed: current files/sec rate.</li>
        <li>Refresh metadata: re-read EXIF for indexed files.</li>
        <li>Network drives may scan slower.</li>
        <li>ZIP/archive files are not scanned inside yet.</li>
      </ul>
    </InfoTip>
  );
}

function ScanLibraryIcon() {
  return (
    <svg viewBox="0 0 40 40" aria-hidden="true" focusable="false">
      <path
        d="M12 7h12l6 6v20H12z"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinejoin="round"
      />
      <path
        d="M24 7v7h6"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinejoin="round"
      />
      <path
        d="M8 23h24"
        fill="none"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
      />
      <path
        d="M14 28h12"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        opacity="0.65"
      />
    </svg>
  );
}

function SearchIcon() {
  return (
    <svg viewBox="0 0 40 40" aria-hidden="true" focusable="false">
      <circle
        cx="18"
        cy="18"
        r="9"
        fill="none"
        stroke="currentColor"
        strokeWidth="3"
      />
      <path
        d="M25 25l7 7"
        fill="none"
        stroke="currentColor"
        strokeWidth="3.4"
        strokeLinecap="round"
      />
    </svg>
  );
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
  const [activeScanId, setActiveScanId] = useState<number | null>(null);
  const [activeScanStatus, setActiveScanStatus] = useState<ScanStatus | null>(null);
  const [photoSearchFilters, setPhotoSearchFilters] = useState<PhotoSearchFilters>({
    camera_model: "",
    lens_model: "",
    min_focal_length: "",
    max_focal_length: "",
    extension: "",
    iso: "",
    aperture: "",
    shutter_speed: "",
    date_from: "",
    date_to: "",
    device_type: "",
    sort_by: "date_taken",
    sort_order: "desc",
  });
  const [photoSearch, setPhotoSearch] = useState<PhotoSearchResponse | null>(null);
  const [photoSearchOptions, setPhotoSearchOptions] =
    useState<PhotoSearchOptions | null>(null);
  const [isSearchingPhotos, setIsSearchingPhotos] = useState(false);
  const [photoSearchError, setPhotoSearchError] = useState<string | null>(null);
  const [isSearchResultsOpen, setIsSearchResultsOpen] = useState(true);
  const [visibleSearchColumns, setVisibleSearchColumns] =
    useState<string[]>(loadSearchColumns);
  const [analyticsFilters, setAnalyticsFilters] = useState<AnalyticsFilters>({
    x_axis: "capture_month",
    metric: "photo_count",
    group_by: "",
    date_from: "",
    date_to: "",
  });
  const [analyticsResult, setAnalyticsResult] = useState<AnalyticsResponse | null>(null);
  const [isLoadingAnalytics, setIsLoadingAnalytics] = useState(false);
  const [analyticsError, setAnalyticsError] = useState<string | null>(null);
  const [copiedPhotoId, setCopiedPhotoId] = useState<number | null>(null);
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

  const loadPhotoSearchOptions = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/photos/search-options`);

      if (!response.ok) {
        throw new Error(`Search options request failed with ${response.status}`);
      }

      setPhotoSearchOptions((await response.json()) as PhotoSearchOptions);
    } catch {
      setPhotoSearchOptions(null);
    }
  }, []);

  const runPhotoSearch = useCallback(async (offset = 0, append = false) => {
    const params = new URLSearchParams({
      limit: String(Math.min(PHOTO_SEARCH_LIMIT, 500)),
      offset: String(offset),
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

      const nextSearch = (await response.json()) as PhotoSearchResponse;
      setPhotoSearch((currentSearch) =>
        append && currentSearch
          ? {
              ...nextSearch,
              results: [...currentSearch.results, ...nextSearch.results],
            }
          : nextSearch,
      );
      setIsSearchResultsOpen(true);
    } catch (caughtError) {
      setPhotoSearchError(
        caughtError instanceof Error ? caughtError.message : "Unable to search photos.",
      );
    } finally {
      setIsSearchingPhotos(false);
    }
  }, [photoSearchFilters]);

  const runAnalytics = useCallback(async (offset = 0) => {
    const params = new URLSearchParams({
      x_axis: analyticsFilters.x_axis,
      metric: analyticsFilters.metric,
      limit: analyticsFilters.x_axis === "capture_date" ? "250" : "50",
      offset: String(offset),
    });

    if (analyticsFilters.group_by) {
      params.set("group_by", analyticsFilters.group_by);
    }
    if (analyticsFilters.date_from) {
      params.set("date_from", analyticsFilters.date_from);
    }
    if (analyticsFilters.date_to) {
      params.set("date_to", analyticsFilters.date_to);
    }

    setIsLoadingAnalytics(true);
    setAnalyticsError(null);

    try {
      const response = await fetch(`${API_BASE_URL}/analytics?${params}`);

      if (!response.ok) {
        let message = `Analytics request failed with ${response.status}`;

        try {
          const errorBody = await response.json();
          message = errorBody.detail ?? message;
        } catch {
          // Keep the status-based message if the backend response is not JSON.
        }

        throw new Error(message);
      }

      setAnalyticsResult((await response.json()) as AnalyticsResponse);
    } catch (caughtError) {
      setAnalyticsError(
        caughtError instanceof Error
          ? caughtError.message
          : "Unable to build analytics chart.",
      );
    } finally {
      setIsLoadingAnalytics(false);
    }
  }, [analyticsFilters]);

  useEffect(() => {
    loadStats();
    void loadSystemInfo();
    void loadScanHistory();
    void loadPhotoSearchOptions();
  }, [loadPhotoSearchOptions, loadScanHistory, loadStats, loadSystemInfo]);

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
    window.localStorage.setItem(
      SEARCH_COLUMNS_STORAGE_KEY,
      JSON.stringify(visibleSearchColumns),
    );
  }, [visibleSearchColumns]);

  useEffect(() => {
    void loadLatestScanSession(folderPath);
  }, [folderPath, loadLatestScanSession]);

  useEffect(() => {
    if (photoSearch) {
      void runPhotoSearch(0, false);
    }
  }, [photoSearchFilters.sort_by, photoSearchFilters.sort_order]);

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
    await runPhotoSearch(0, false);
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

  function updateAnalyticsFilter(key: keyof AnalyticsFilters, value: string) {
    setAnalyticsFilters((currentFilters) => ({
      ...currentFilters,
      [key]: value,
      ...(key === "x_axis" && value === currentFilters.group_by
        ? { group_by: "" }
        : {}),
    }));
  }

  function toggleSearchColumn(column: string) {
    setVisibleSearchColumns((currentColumns) =>
      currentColumns.includes(column)
        ? currentColumns.filter((currentColumn) => currentColumn !== column)
        : [...currentColumns, column],
    );
  }

  async function copyPhotoPath(photo: PhotoSearchResult) {
    try {
      await window.navigator.clipboard.writeText(photo.path);
      setCopiedPhotoId(photo.id);
      window.setTimeout(() => {
        setCopiedPhotoId((currentPhotoId) =>
          currentPhotoId === photo.id ? null : currentPhotoId,
        );
      }, 1800);
    } catch {
      setPhotoSearchError("Unable to copy the photo path from this browser.");
    }
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

  const fileTypeRows = useMemo(() => {
    if (!stats) {
      return [];
    }

    return Object.entries(stats.file_type_counts).sort(([left], [right]) =>
      left.localeCompare(right),
    );
  }, [stats]);

  const fileTypeDistributionData = useMemo(
    () =>
      fileTypeRows.map(([extension, count]) => ({
        extension: extension.toUpperCase(),
        count,
      })),
    [fileTypeRows],
  );
  const cameraChartData = stats?.top_cameras.slice(0, 8) ?? [];
  const lensChartData = stats?.top_lenses.slice(0, 8) ?? [];
  const timelineChartData = stats?.photo_timeline ?? [];
  const cameraUsageTimelineData = stats?.camera_usage_timeline ?? [];
  const lensUsageTimelineData = stats?.lens_usage_timeline ?? [];
  const cameraUsageTimelineKeys = useMemo(
    () => usageTimelineKeys(cameraUsageTimelineData),
    [cameraUsageTimelineData],
  );
  const lensUsageTimelineKeys = useMemo(
    () => usageTimelineKeys(lensUsageTimelineData),
    [lensUsageTimelineData],
  );
  const showAnyStatCard =
    dashboardPreferences.showTotalPhotosCard ||
    dashboardPreferences.showTotalSizeCard ||
    dashboardPreferences.showNewestDateCard ||
    dashboardPreferences.showOldestDateCard ||
    dashboardPreferences.showFavoriteCameraCard ||
    dashboardPreferences.showFavoriteLensCard ||
    dashboardPreferences.showFocalLengthCard ||
    dashboardPreferences.showBusiestDateCard ||
    dashboardPreferences.showAverageFileSizeCard ||
    dashboardPreferences.showTopStorageTypeCard ||
    dashboardPreferences.showRawJpegCard ||
    dashboardPreferences.showDeviceTypeCard ||
    dashboardPreferences.showMostCommonIsoCard ||
    dashboardPreferences.showMostCommonApertureCard ||
    dashboardPreferences.showMostCommonShutterCard ||
    dashboardPreferences.showAverageCameraSizeCard;
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
    dashboardPreferences.showAverageFileSizeCard,
    dashboardPreferences.showTopStorageTypeCard,
    dashboardPreferences.showRawJpegCard,
    dashboardPreferences.showDeviceTypeCard,
    dashboardPreferences.showMostCommonIsoCard,
    dashboardPreferences.showMostCommonApertureCard,
    dashboardPreferences.showMostCommonShutterCard,
    dashboardPreferences.showAverageCameraSizeCard,
  ].filter(Boolean).length;
  const visibleInsightCount = [
    dashboardPreferences.showCameraChart,
    dashboardPreferences.showLensChart,
    dashboardPreferences.showTimelineChart,
    dashboardPreferences.showFileTypeChart,
    dashboardPreferences.showScanHistorySection,
    dashboardPreferences.showMetadataSearchSection,
  ].filter(Boolean).length;
  const hasInsightData = stats !== null && stats.total_photos > 0;
  const hasNoPhotoData = stats !== null && stats.total_photos === 0;

  const canResumeLastScan =
    lastScanSession !== null &&
    ["failed", "interrupted"].includes(lastScanSession.status);

  const canResumeScan = (scanSession: ScanSession) =>
    ["failed", "interrupted"].includes(scanSession.status);
  const latestScanHistoryItem = scanHistory[0] ?? null;
  const activeScanMetrics = activeScanStatus
    ? [
        {
          label: "Files seen",
          value: activeScanStatus.files_seen.toLocaleString(),
        },
        {
          label: "Matched",
          value: activeScanStatus.image_files_matched.toLocaleString(),
        },
        {
          label: "New",
          value: activeScanStatus.new_files.toLocaleString(),
        },
        {
          label: "Updated",
          value: activeScanStatus.updated_files.toLocaleString(),
        },
        {
          label: "Skipped",
          value: activeScanStatus.skipped_files.toLocaleString(),
        },
        {
          label: "Failed",
          value: activeScanStatus.failed_files.toLocaleString(),
        },
        {
          label: "Speed",
          value: formatScanSpeed(activeScanStatus.scan_speed_files_per_second),
        },
      ]
    : [];

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
                  {(
                    [
                      ["showAverageFileSizeCard", "Average file"],
                      ["showTopStorageTypeCard", "Top storage type"],
                      ["showRawJpegCard", "RAW / JPEG"],
                      ["showDeviceTypeCard", "Phone / camera"],
                      ["showMostCommonIsoCard", "ISO"],
                      ["showMostCommonApertureCard", "Aperture"],
                      ["showMostCommonShutterCard", "Shutter"],
                      ["showAverageCameraSizeCard", "Camera average size"],
                    ] as Array<[keyof DashboardPreferences, string]>
                  ).map(([key, label]) => (
                    <label key={key}>
                      <input
                        type="checkbox"
                        checked={dashboardPreferences[key]}
                        onChange={() => updateDashboardPreference(key)}
                      />
                      {label}
                    </label>
                  ))}
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
              {dashboardPreferences.showAverageFileSizeCard && (
              <article className="stat-card insight-default-card file-insight-card">
                <span>Average File</span>
                <strong>{formatMegabytes(stats.average_file_size_bytes)}</strong>
              </article>
              )}
              {dashboardPreferences.showTopStorageTypeCard && (
              <article className="stat-card insight-default-card file-insight-card">
                <span>Top Storage Type</span>
                <strong>{topStorageLabel(stats.storage_by_file_type)}</strong>
              </article>
              )}
              {dashboardPreferences.showRawJpegCard && (
              <article className="stat-card insight-default-card file-insight-card">
                <span>RAW / JPEG</span>
                <strong>
                  {stats.raw_vs_jpeg_counts.raw.toLocaleString()} /{" "}
                  {stats.raw_vs_jpeg_counts.jpeg.toLocaleString()}
                </strong>
                <small>{stats.raw_vs_jpeg_counts.other.toLocaleString()} other</small>
              </article>
              )}
              {dashboardPreferences.showDeviceTypeCard && (
              <article className="stat-card insight-default-card camera-insight-card">
                <span>Phone / Camera</span>
                <strong>
                  {stats.phone_vs_camera_counts.phone.toLocaleString()} /{" "}
                  {stats.phone_vs_camera_counts.camera.toLocaleString()}
                </strong>
                <small>
                  {stats.phone_vs_camera_counts.unknown.toLocaleString()} unknown
                </small>
              </article>
              )}
              {dashboardPreferences.showMostCommonIsoCard && (
              <article className="stat-card insight-default-card exposure-insight-card">
                <span>Most Common ISO</span>
                <strong>{stats.most_common_iso?.label ?? "No data yet"}</strong>
                {stats.most_common_iso && (
                  <small>{stats.most_common_iso.count.toLocaleString()} photos</small>
                )}
              </article>
              )}
              {dashboardPreferences.showMostCommonApertureCard && (
              <article className="stat-card insight-default-card exposure-insight-card">
                <span>Most Common Aperture</span>
                <strong>{stats.most_common_aperture?.label ?? "No data yet"}</strong>
                {stats.most_common_aperture && (
                  <small>
                    {stats.most_common_aperture.count.toLocaleString()} photos
                  </small>
                )}
              </article>
              )}
              {dashboardPreferences.showMostCommonShutterCard && (
              <article className="stat-card insight-default-card exposure-insight-card">
                <span>Most Common Shutter</span>
                <strong>
                  {stats.most_common_shutter_speed?.label ?? "No data yet"}
                </strong>
                {stats.most_common_shutter_speed && (
                  <small>
                    {stats.most_common_shutter_speed.count.toLocaleString()} photos
                  </small>
                )}
              </article>
              )}
              {dashboardPreferences.showAverageCameraSizeCard && (
              <article className="stat-card insight-default-card camera-insight-card">
                <span>Largest Average Camera</span>
                <strong>{topAverageCameraSize(stats.average_file_size_by_camera)}</strong>
                {stats.average_file_size_by_camera[0] && (
                  <small>
                    {formatMegabytes(
                      stats.average_file_size_by_camera[0].average_file_size_bytes,
                    )}{" "}
                    average
                  </small>
                )}
              </article>
              )}
            </section>
          )}

          {showAnyInsightChart && (
            <div className="insight-module-grid">
              {dashboardPreferences.showCameraChart && (
                <section className="chart-section camera-module">
                  <div className="section-heading">
                    <h2>
                      {cameraUsageTimelineData.length > 0
                        ? "Camera Usage Over Time"
                        : "Camera Usage"}
                    </h2>
                    <span>
                      {cameraUsageTimelineData.length > 0
                        ? `${cameraUsageTimelineKeys.length} cameras`
                        : `${cameraChartData.length} cameras`}
                    </span>
                  </div>

                  {cameraUsageTimelineData.length > 0 &&
                  cameraUsageTimelineKeys.length > 0 ? (
                    <div className="chart-frame">
                      <ResponsiveContainer width="100%" height={280}>
                        <LineChart
                          data={cameraUsageTimelineData}
                          margin={{ top: 12, right: 14, bottom: 28, left: 0 }}
                        >
                          <CartesianGrid stroke="#273244" vertical={false} />
                          <XAxis
                            dataKey="label"
                            stroke="#c6d3e6"
                            tickLine={false}
                            axisLine={false}
                            height={42}
                            tick={{ fontSize: 11 }}
                          />
                          <YAxis allowDecimals={false} stroke="#a7b3c6" tickLine={false} axisLine={false} />
                          <Tooltip content={<SeriesTooltip />} />
                          {cameraUsageTimelineKeys.map((key, index) => (
                            <Line
                              key={key}
                              type="monotone"
                              dataKey={key}
                              stroke={
                                CHART_SERIES_COLORS[
                                  index % CHART_SERIES_COLORS.length
                                ]
                              }
                              strokeWidth={2.5}
                              dot={{ r: 2 }}
                              activeDot={{ r: 5 }}
                            />
                          ))}
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  ) : cameraChartData.length > 0 ? (
                    <div className="chart-frame">
                      <ResponsiveContainer width="100%" height={280}>
                        <BarChart
                          data={cameraChartData}
                          margin={{ top: 8, right: 8, bottom: 36, left: 0 }}
                        >
                          <CartesianGrid stroke="#273244" vertical={false} />
                          <XAxis
                            dataKey="label"
                            stroke="#c6d3e6"
                            tickLine={false}
                            axisLine={false}
                            height={14}
                            tick={false}
                          />
                          <YAxis allowDecimals={false} stroke="#a7b3c6" tickLine={false} axisLine={false} />
                          <Tooltip cursor={{ fill: "rgba(125, 211, 252, 0.16)" }} contentStyle={{ background: "#121a26", border: "1px solid #2f3d52", borderRadius: "8px", color: "#edf5ff" }} />
                          <Bar dataKey="count" fill="#4ade80" radius={[6, 6, 0, 0]} activeBar={{ fill: "#bfffea" }} />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  ) : (
                    <p className="empty-chart">Run a scan with EXIF data to populate camera usage.</p>
                  )}
                </section>
              )}

              {dashboardPreferences.showLensChart && (
                <section className="chart-section lens-module">
                  <div className="section-heading">
                    <h2>
                      {lensUsageTimelineData.length > 0
                        ? "Lens Usage Over Time"
                        : "Lens Usage"}
                    </h2>
                    <span>
                      {lensUsageTimelineData.length > 0
                        ? `${lensUsageTimelineKeys.length} lenses`
                        : `${lensChartData.length} lenses`}
                    </span>
                  </div>

                  {lensUsageTimelineData.length > 0 &&
                  lensUsageTimelineKeys.length > 0 ? (
                    <div className="chart-frame">
                      <ResponsiveContainer width="100%" height={280}>
                        <LineChart
                          data={lensUsageTimelineData}
                          margin={{ top: 12, right: 14, bottom: 28, left: 0 }}
                        >
                          <CartesianGrid stroke="#273244" vertical={false} />
                          <XAxis
                            dataKey="label"
                            stroke="#c6d3e6"
                            tickLine={false}
                            axisLine={false}
                            height={42}
                            tick={{ fontSize: 11 }}
                          />
                          <YAxis allowDecimals={false} stroke="#a7b3c6" tickLine={false} axisLine={false} />
                          <Tooltip content={<SeriesTooltip />} />
                          {lensUsageTimelineKeys.map((key, index) => (
                            <Line
                              key={key}
                              type="monotone"
                              dataKey={key}
                              stroke={
                                CHART_SERIES_COLORS[
                                  index % CHART_SERIES_COLORS.length
                                ]
                              }
                              strokeWidth={2.5}
                              dot={{ r: 2 }}
                              activeDot={{ r: 5 }}
                            />
                          ))}
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  ) : lensChartData.length > 0 ? (
                    <div className="chart-frame">
                      <ResponsiveContainer width="100%" height={280}>
                        <BarChart
                          data={lensChartData}
                          margin={{ top: 8, right: 8, bottom: 36, left: 0 }}
                        >
                          <CartesianGrid stroke="#273244" vertical={false} />
                          <XAxis
                            dataKey="label"
                            stroke="#c6d3e6"
                            tickLine={false}
                            axisLine={false}
                            height={14}
                            tick={false}
                          />
                          <YAxis allowDecimals={false} stroke="#a7b3c6" tickLine={false} axisLine={false} />
                          <Tooltip cursor={{ fill: "rgba(169, 135, 255, 0.16)" }} contentStyle={{ background: "#121a26", border: "1px solid #2f3d52", borderRadius: "8px", color: "#edf5ff" }} />
                          <Bar dataKey="count" fill="#a987ff" radius={[6, 6, 0, 0]} activeBar={{ fill: "#d7c7ff" }} />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  ) : (
                    <p className="empty-chart">Run a scan with EXIF data to populate lens usage.</p>
                  )}
                </section>
              )}

              {dashboardPreferences.showTimelineChart &&
                timelineChartData.length > 0 && (
              <section className="chart-section timeline-module">
                <div className="section-heading">
                  <div>
                    <h2>Capture Timeline</h2>
                    <span>
                      Only files with capture dates and capture metadata are included.
                    </span>
                  </div>
                  <span>{timelineChartData.length} months</span>
                </div>

                <div className="chart-frame">
                  <ResponsiveContainer width="100%" height={280}>
                    <LineChart
                      data={timelineChartData}
                      margin={{ top: 12, right: 14, bottom: 28, left: 0 }}
                    >
                      <CartesianGrid stroke="#273244" vertical={false} />
                      <XAxis
                        dataKey="label"
                        stroke="#c6d3e6"
                        tickLine={false}
                        axisLine={false}
                        height={42}
                        tick={{ fontSize: 11 }}
                      />
                      <YAxis allowDecimals={false} stroke="#a7b3c6" tickLine={false} axisLine={false} />
                      <Tooltip content={<TimelineTooltip />} />
                      <Line type="monotone" dataKey="count" stroke="#f472b6" strokeWidth={3} dot={{ r: 3 }} activeDot={{ r: 6, fill: "#fdf2f8" }} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </section>
              )}

              {dashboardPreferences.showTimelineChart &&
                stats.top_capture_dates.length > 0 && (
              <section className="chart-section compact-module timeline-module">
                <div className="section-heading">
                  <h2>Top 5 Capture Dates</h2>
                  <span>{stats.top_capture_dates.length} dates</span>
                </div>
                <div className="chart-frame compact-chart">
                      <ResponsiveContainer width="100%" height={160}>
                        <BarChart
                          data={stats.top_capture_dates}
                          margin={{ top: 4, right: 6, bottom: 14, left: 0 }}
                    >
                      <CartesianGrid stroke="#273244" vertical={false} />
                      <XAxis
                        dataKey="label"
                        stroke="#c6d3e6"
                        tickLine={false}
                        axisLine={false}
                          height={28}
                        tick={{ fontSize: 11 }}
                      />
                      <YAxis allowDecimals={false} stroke="#a7b3c6" tickLine={false} axisLine={false} />
                      <Tooltip cursor={{ fill: "rgba(74, 222, 128, 0.14)" }} contentStyle={{ background: "#121a26", border: "1px solid #2f3d52", borderRadius: "8px", color: "#edf5ff" }} />
                      <Bar dataKey="count" fill="#4ade80" radius={[6, 6, 0, 0]} activeBar={{ fill: "#bbf7d0" }} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </section>
              )}

              {dashboardPreferences.showFileTypeChart && (
              <section className="chart-section compact-module file-type-module">
                <div className="section-heading">
                  <h2>File Type Distribution</h2>
                  <span>{fileTypeDistributionData.length} types</span>
                </div>

                {fileTypeDistributionData.length > 0 ? (
                  <div className="chart-frame compact-chart donut-chart">
                    <ResponsiveContainer width="100%" height={190}>
                      <PieChart>
                        <Pie
                          data={fileTypeDistributionData}
                          dataKey="count"
                          nameKey="extension"
                          innerRadius={42}
                          outerRadius={72}
                          paddingAngle={2}
                        >
                          {fileTypeDistributionData.map((row, index) => (
                            <Cell
                              key={row.extension}
                              fill={
                                CHART_SERIES_COLORS[
                                  index % CHART_SERIES_COLORS.length
                                ]
                              }
                            />
                          ))}
                        </Pie>
                        <Tooltip content={<SeriesTooltip />} />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                ) : (
                  <p className="empty-chart">Run a scan to populate file type data.</p>
                )}
              </section>
              )}
            </div>
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
            <span className="tool-card-icon scan-icon" aria-hidden="true">
              <ScanLibraryIcon />
            </span>
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
            <span className="tool-card-icon search-icon" aria-hidden="true">
              <SearchIcon />
            </span>
            <span className="tool-card-copy">
              <strong>Metadata Search</strong>
              <span>Filter indexed photos by EXIF details.</span>
            </span>
          </button>

          <button
            type="button"
            className={`tool-card analytics-card${activeTool === "analytics" ? " active" : ""}`}
            onClick={() => toggleTool("analytics")}
            aria-controls="analytics-explorer-panel"
            aria-expanded={activeTool === "analytics"}
          >
            <span className="tool-card-icon analytics-icon" aria-hidden="true">
              <SearchIcon />
            </span>
            <span className="tool-card-copy">
              <strong>Analytics Explorer</strong>
              <span>Build compact custom charts from scanned metadata.</span>
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
            <span>Index a local photo folder and review recent scan activity</span>
          </div>
        </div>

        <div className="scan-subsection">
          <div className="scan-subsection-heading">
            <h3>New Scan</h3>
            <ScanLibraryInfoTip />
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
              <button
                type={isScanning ? "button" : "submit"}
                className={
                  isScanning ? "scan-primary-button cancel" : "scan-primary-button"
                }
                onClick={isScanning ? () => void cancelActiveScan() : undefined}
                disabled={isScanning && activeScanId === null}
              >
                {isScanning ? "Cancel Scan" : "Start Scan"}
              </button>
            </div>
            {isScanning && (
              <div
                className="active-scan-near-input"
                role="status"
                aria-live="polite"
              >
                <span className="spinner" aria-hidden="true" />
                <div>
                  <strong>Running scan</strong>
                  <span>{activeScanStatus?.folder_path ?? folderPath}</span>
                  <small>
                    Started{" "}
                    {formatDate(
                      activeScanStatus?.started_at ??
                        lastScanSession?.started_at ??
                        null,
                    )}
                  </small>
                </div>
              </div>
            )}
            <label className="scan-option">
              <input
                type="checkbox"
                checked={refreshMetadata}
                onChange={(event) => setRefreshMetadata(event.target.checked)}
                disabled={isScanning}
              />
              <span>
                Refresh metadata
                <small>Re-read EXIF details for files already indexed.</small>
              </span>
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

        {isScanning && (
          <div className="scan-progress" aria-live="polite">
            <span className="spinner" aria-hidden="true" />
            <span>
              Scanning with live counters. Total file count is not known up front.
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
          </div>
        )}

        {activeScanStatus && (
          <div className="scan-live-panel" aria-label="Live scan progress">
            {activeScanMetrics.map((metric) => (
              <div key={metric.label}>
                <span>{metric.label}</span>
                <strong>{metric.value}</strong>
              </div>
            ))}
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
          <span>
            {scanHistory.length.toLocaleString()} recent scans
            {latestScanHistoryItem && (
              <>
                . Latest: {formatScanStatus(latestScanHistoryItem.status)}{" "}
                {formatDate(latestScanHistoryItem.started_at)}
              </>
            )}
          </span>
        </div>

{isScanHistoryOpen && (
  <section id="scan-history-panel" className="table-section embedded-history">
    {canResumeLastScan && (
      <div className="history-resume-banner">
        <span>Last scan can be resumed from Scan History.</span>
        <button
          type="button"
          className="secondary-button"
          onClick={() => void runScan({ resume: true })}
          disabled={isScanning}
        >
          Resume Last Scan
        </button>
      </div>
    )}
    <table>
      <thead>
        <tr>
          <th>Status</th>
          <th>Folder</th>
          <th>Matched</th>
          <th>Changes</th>
          <th>Started</th>
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
                {scanSession.skipped_files.toLocaleString()} skipped,{" "}
                {scanSession.failed_files.toLocaleString()} failed
              </td>
              <td>{formatDate(scanSession.started_at)}</td>
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
            <td colSpan={8}>
              No scan history yet. Start with a local photo folder above.
            </td>
          </tr>
        )}
      </tbody>
    </table>
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
              list="camera-options"
              value={photoSearchFilters.camera_model}
              onChange={(event) =>
                updatePhotoSearchFilter("camera_model", event.target.value)
              }
              placeholder="EOS R5"
            />
            <datalist id="camera-options">
              {(photoSearchOptions?.camera_models ?? photoSearchOptions?.cameras ?? []).map((camera) => (
                <option key={camera} value={camera} />
              ))}
            </datalist>
          </label>
          <label>
            Lens
            <input
              type="text"
              list="lens-options"
              value={photoSearchFilters.lens_model}
              onChange={(event) =>
                updatePhotoSearchFilter("lens_model", event.target.value)
              }
              placeholder="RF50"
            />
            <datalist id="lens-options">
              {(photoSearchOptions?.lens_models ?? photoSearchOptions?.lenses ?? []).map((lens) => (
                <option key={lens} value={lens} />
              ))}
            </datalist>
          </label>
          <label>
            Type
            <select
              value={photoSearchFilters.extension}
              onChange={(event) =>
                updatePhotoSearchFilter("extension", event.target.value)
              }
            >
              <option value="">Any</option>
              {photoSearchOptions?.extensions.map((extension) => (
                <option key={extension} value={extension}>
                  {extension.toUpperCase()}
                </option>
              ))}
            </select>
          </label>
          <label>
            Device
            <select
              value={photoSearchFilters.device_type}
              onChange={(event) =>
                updatePhotoSearchFilter("device_type", event.target.value)
              }
            >
              <option value="">Any</option>
              {photoSearchOptions?.device_types.map((deviceType) => (
                <option key={deviceType} value={deviceType}>
                  {deviceType}
                </option>
              ))}
            </select>
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
            ISO
            <select
              value={photoSearchFilters.iso}
              onChange={(event) =>
                updatePhotoSearchFilter("iso", event.target.value)
              }
            >
              <option value="">Any</option>
              {photoSearchOptions?.iso_values.map((isoValue) => (
                <option key={isoValue} value={isoValue}>
                  {isoValue}
                </option>
              ))}
            </select>
          </label>
          <label>
            Aperture
            <select
              value={photoSearchFilters.aperture}
              onChange={(event) =>
                updatePhotoSearchFilter("aperture", event.target.value)
              }
            >
              <option value="">Any</option>
              {photoSearchOptions?.aperture_values.map((apertureValue) => (
                <option key={apertureValue} value={apertureValue}>
                  f/{apertureValue}
                </option>
              ))}
            </select>
          </label>
          <label>
            Shutter
            <select
              value={photoSearchFilters.shutter_speed}
              onChange={(event) =>
                updatePhotoSearchFilter("shutter_speed", event.target.value)
              }
            >
              <option value="">Any</option>
              {photoSearchOptions?.shutter_speed_values.map((shutterSpeed) => (
                <option key={shutterSpeed} value={shutterSpeed}>
                  {shutterSpeed}
                </option>
              ))}
            </select>
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
          <label>
            Sort
            <select
              value={photoSearchFilters.sort_by}
              onChange={(event) =>
                updatePhotoSearchFilter("sort_by", event.target.value)
              }
            >
              {SEARCH_SORT_FIELDS.map((field) => (
                <option key={field} value={field}>
                  {formatOptionLabel(field)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Order
            <select
              value={photoSearchFilters.sort_order}
              onChange={(event) =>
                updatePhotoSearchFilter("sort_order", event.target.value)
              }
            >
              <option value="desc">Descending</option>
              <option value="asc">Ascending</option>
            </select>
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
              <button
                type="button"
                className="small-action-button"
                onClick={() => setIsSearchResultsOpen((currentValue) => !currentValue)}
                aria-expanded={isSearchResultsOpen}
              >
                {isSearchResultsOpen ? "Hide Results" : "Show Results"}
              </button>
              <strong>{photoSearch.total_count.toLocaleString()} matches</strong>
              <span>
                Showing {photoSearch.results.length.toLocaleString()} sorted by{" "}
                {formatOptionLabel(photoSearch.sort_by)} {photoSearch.sort_order}
              </span>
            </div>
            {isSearchResultsOpen && (
              <>
                <div className="column-picker" aria-label="Search result columns">
                  {DEFAULT_SEARCH_COLUMNS.map((column) => (
                    <label key={column}>
                      <input
                        type="checkbox"
                        checked={visibleSearchColumns.includes(column)}
                        onChange={() => toggleSearchColumn(column)}
                      />
                      {SEARCH_COLUMN_LABELS[column]}
                    </label>
                  ))}
                </div>
                <table>
                  <thead>
                    <tr>
                      {visibleSearchColumns.map((column) => (
                        <th key={column}>{SEARCH_COLUMN_LABELS[column]}</th>
                      ))}
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {photoSearch.results.length > 0 ? (
                      photoSearch.results.map((photo) => (
                        <tr key={photo.id}>
                          {visibleSearchColumns.map((column) => (
                            <td key={column}>{formatSearchCell(photo, column)}</td>
                          ))}
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
                        <td colSpan={visibleSearchColumns.length + 1}>
                          No matching photos. Try clearing a filter or widening the
                          date or focal length range.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
                {photoSearch.results.length < photoSearch.total_count && (
                  <div className="load-more-row">
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() =>
                        void runPhotoSearch(photoSearch.results.length, true)
                      }
                      disabled={isSearchingPhotos}
                    >
                      {isSearchingPhotos ? "Loading..." : "Load More"}
                    </button>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </section>
      )}

      {activeTool === "analytics" && (
      <section
        id="analytics-explorer-panel"
        className="search-section tool-detail analytics-section"
        aria-labelledby="analytics-explorer-heading"
      >
        <div className="section-heading scan-heading">
          <div>
            <h2 id="analytics-explorer-heading">Analytics Explorer</h2>
            <span>Build compact charts from indexed metadata</span>
          </div>
        </div>

        <div className="preset-row">
          {[
            ["capture_month", "photo_count", "camera_model", "Camera usage over time"],
            ["capture_month", "photo_count", "lens_model", "Lens usage over time"],
            ["extension", "avg_file_size", "", "Average file size by type"],
            ["camera_model", "total_file_size", "", "Total storage by camera"],
            ["capture_date", "photo_count", "", "Top capture dates"],
            ["iso", "photo_count", "", "ISO distribution"],
            ["aperture", "photo_count", "", "Aperture distribution"],
          ].map(([xAxis, metric, groupBy, label]) => (
            <button
              type="button"
              className="small-action-button"
              key={label}
              onClick={() =>
                setAnalyticsFilters({
                  x_axis: xAxis,
                  metric,
                  group_by: groupBy,
                  date_from: "",
                  date_to: "",
                })
              }
            >
              {label}
            </button>
          ))}
        </div>

        <form
          className="search-form analytics-form"
          onSubmit={(event) => {
            event.preventDefault();
            void runAnalytics();
          }}
        >
          <label>
            Compare by
            <select
              value={analyticsFilters.x_axis}
              onChange={(event) =>
                updateAnalyticsFilter("x_axis", event.target.value)
              }
            >
              {ANALYTICS_DIMENSIONS.map((dimension) => (
                <option key={dimension} value={dimension}>
                  {formatOptionLabel(dimension)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Measure
            <select
              value={analyticsFilters.metric}
              onChange={(event) =>
                updateAnalyticsFilter("metric", event.target.value)
              }
            >
              {ANALYTICS_METRICS.map((metric) => (
                <option key={metric} value={metric}>
                  {formatOptionLabel(metric)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Group by
            <select
              value={analyticsFilters.group_by}
              onChange={(event) =>
                updateAnalyticsFilter("group_by", event.target.value)
              }
            >
              <option value="">None</option>
              {ANALYTICS_GROUP_BY.filter(
                (groupBy) => groupBy !== analyticsFilters.x_axis,
              ).map((groupBy) => (
                <option key={groupBy} value={groupBy}>
                  {formatOptionLabel(groupBy)}
                </option>
              ))}
            </select>
          </label>
          <label>
            From
            <input
              type="date"
              value={analyticsFilters.date_from}
              onChange={(event) =>
                updateAnalyticsFilter("date_from", event.target.value)
              }
            />
          </label>
          <label>
            To
            <input
              type="date"
              value={analyticsFilters.date_to}
              onChange={(event) =>
                updateAnalyticsFilter("date_to", event.target.value)
              }
            />
          </label>
          <button type="submit" disabled={isLoadingAnalytics}>
            {isLoadingAnalytics ? "Building..." : "Build Chart"}
          </button>
        </form>

        {analyticsError && (
          <p className="scan-feedback failure">{analyticsError}</p>
        )}

        {analyticsResult && (
          <section className="chart-section analytics-chart">
            <div className="section-heading">
              <h2>
                {formatOptionLabel(analyticsResult.metric)} by{" "}
                {formatOptionLabel(analyticsResult.x_axis)}
              </h2>
              <span>{analyticsResult.rows.length} points</span>
            </div>
            <div
              className={`chart-frame${
                analyticsResult.x_axis === "capture_date" ? " chart-scroll" : ""
              }`}
            >
              <div
                className="chart-scroll-inner"
                style={{
                  minWidth:
                    analyticsResult.x_axis === "capture_date"
                      ? `${Math.max(760, analyticsResult.rows.length * 44)}px`
                      : "100%",
                }}
              >
              <ResponsiveContainer width="100%" height={300}>
                {analyticsResult.group_by ||
                analyticsResult.x_axis.startsWith("capture_") ? (
                  <LineChart
                    data={analyticsResult.rows}
                    margin={{ top: 12, right: 14, bottom: 28, left: 0 }}
                  >
                    <CartesianGrid stroke="#273244" vertical={false} />
                    <XAxis
                      dataKey="label"
                      stroke="#c6d3e6"
                      tickLine={false}
                      axisLine={false}
                      height={42}
                      tick={{ fontSize: 11 }}
                    />
                    <YAxis allowDecimals={false} stroke="#a7b3c6" tickLine={false} axisLine={false} />
                    <Tooltip content={<SeriesTooltip />} />
                    {(analyticsResult.group_by
                      ? analyticsResult.series
                      : ["value"]
                    ).map((key, index) => (
                      <Line
                        key={key}
                        type="monotone"
                        dataKey={key}
                        stroke={
                          CHART_SERIES_COLORS[index % CHART_SERIES_COLORS.length]
                        }
                        strokeWidth={2.5}
                        dot={{ r: 2 }}
                        activeDot={{ r: 5 }}
                      />
                    ))}
                  </LineChart>
                ) : (
                  <BarChart
                    data={analyticsResult.rows}
                    margin={{ top: 8, right: 8, bottom: 36, left: 0 }}
                  >
                    <CartesianGrid stroke="#273244" vertical={false} />
                    <XAxis
                      dataKey="label"
                      stroke="#c6d3e6"
                      tickLine={false}
                      axisLine={false}
                      height={38}
                      tick={{ fontSize: 11 }}
                    />
                    <YAxis allowDecimals={false} stroke="#a7b3c6" tickLine={false} axisLine={false} />
                    <Tooltip cursor={{ fill: "rgba(125, 211, 252, 0.16)" }} content={<SeriesTooltip />} />
                    <Bar dataKey="value" fill="#7dd3fc" radius={[6, 6, 0, 0]} activeBar={{ fill: "#bfffea" }} />
                  </BarChart>
                )}
              </ResponsiveContainer>
              </div>
            </div>
            <div className="analytics-result-list">
              <table>
                <thead>
                  <tr>
                    <th>{formatOptionLabel(analyticsResult.x_axis)}</th>
                    {(analyticsResult.group_by
                      ? analyticsResult.series
                      : ["value"]
                    ).map((key) => (
                      <th key={key}>{formatOptionLabel(key)}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {analyticsResult.rows.map((row) => (
                    <tr key={String(row.label)}>
                      <td>{row.label}</td>
                      {(analyticsResult.group_by
                        ? analyticsResult.series
                        : ["value"]
                      ).map((key) => (
                        <td key={key}>{row[key] ?? "—"}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </section>
      )}
    </main>
  );
}

export default App;
