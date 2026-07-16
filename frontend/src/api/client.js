import axios from "axios";

// ── Base client ────────────────────────────────────────────────────────────
const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "http://localhost:8000",
  timeout: 60_000,
  headers: { "Content-Type": "application/json" },
});

// ── Request interceptor ───────────────────────────────────────────────────
apiClient.interceptors.request.use(
  (config) => config,
  (error) => Promise.reject(error)
);

// ── Response interceptor — normalise errors ───────────────────────────────
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const message =
      error.response?.data?.detail ||
      error.response?.data?.error ||
      error.message ||
      "An unexpected error occurred";
    return Promise.reject(new Error(message));
  }
);

// ═══════════════════════════════════════════════════════════════════════════
// Reports API
// ═══════════════════════════════════════════════════════════════════════════
export const reportsApi = {
  /**
   * Create a new briefing run (topic-based).
   * @param {{ topic: string, competitor_name?: string, industry: string, region: string, max_sources?: number, max_steps?: number }} data
   */
  create: (data) =>
    apiClient.post("/api/v1/reports/", data).then((r) => r.data),

  /**
   * List reports with optional pagination and status filter.
   * @param {{ page?: number, page_size?: number, status?: string }} params
   */
  list: (params = {}) =>
    apiClient.get("/api/v1/reports/", { params }).then((r) => r.data),

  /** Get a single report by ID. */
  get: (reportId) =>
    apiClient.get(`/api/v1/reports/${reportId}`).then((r) => r.data),

  /** Lightweight status poll. */
  getStatus: (reportId) =>
    apiClient.get(`/api/v1/reports/${reportId}/status`).then((r) => r.data),

  /** Run metadata: budget usage, governance stats, peer review. */
  getMetadata: (reportId) =>
    apiClient.get(`/api/v1/reports/${reportId}/metadata`).then((r) => r.data),

  /** Delete a report. */
  delete: (reportId) =>
    apiClient.delete(`/api/v1/reports/${reportId}`).then((r) => r.data),

  /** URL for downloading the Markdown export (open in new tab or fetch). */
  markdownExportUrl: (reportId) =>
    `${apiClient.defaults.baseURL}/api/v1/reports/${reportId}/export/markdown`,

  /** URL for downloading the PDF export. */
  pdfExportUrl: (reportId) =>
    `${apiClient.defaults.baseURL}/api/v1/reports/${reportId}/export/pdf`,
};

// ═══════════════════════════════════════════════════════════════════════════
// Executions API
// ═══════════════════════════════════════════════════════════════════════════
export const executionsApi = {
  /** List all executions (paginated). */
  list: (params = {}) =>
    apiClient.get("/api/v1/executions/", { params }).then((r) => r.data),

  /** List all executions for a specific report. */
  listForReport: (reportId) =>
    apiClient
      .get(`/api/v1/executions/report/${reportId}`)
      .then((r) => r.data),

  /** Get a single execution by ID. */
  get: (executionId) =>
    apiClient.get(`/api/v1/executions/${executionId}`).then((r) => r.data),
};

// ═══════════════════════════════════════════════════════════════════════════
// Logs API
// ═══════════════════════════════════════════════════════════════════════════
export const logsApi = {
  /**
   * List audit logs (paginated, filterable).
   * @param {{ page?: number, page_size?: number, level?: string, agent_name?: string }} params
   */
  list: (params = {}) =>
    apiClient.get("/api/v1/logs/", { params }).then((r) => r.data),

  /** List all logs for a specific report. */
  listForReport: (reportId, params = {}) =>
    apiClient
      .get(`/api/v1/logs/report/${reportId}`, { params })
      .then((r) => r.data),

  /** Get a single log entry. */
  get: (logId) =>
    apiClient.get(`/api/v1/logs/${logId}`).then((r) => r.data),
};

// ═══════════════════════════════════════════════════════════════════════════
// Stream API (Server-Sent Events)
// ═══════════════════════════════════════════════════════════════════════════
export const streamApi = {
  /**
   * Open an SSE stream for a report's real-time agent status.
   *
   * @param {string} reportId
   * @param {{ onStatus, onDone, onError, onTimeout }} handlers
   * @returns {EventSource}  Call .close() to stop the stream.
   */
  openStatusStream: (reportId, { onStatus, onDone, onError, onTimeout } = {}) => {
    const base = import.meta.env.VITE_API_URL || "http://localhost:8000";
    const es = new EventSource(`${base}/api/v1/stream/${reportId}`);

    es.addEventListener("status", (e) => {
      try {
        onStatus?.(JSON.parse(e.data));
      } catch (err) {
        console.error("SSE parse error", err);
      }
    });

    es.addEventListener("done",    () => { onDone?.();    es.close(); });
    es.addEventListener("timeout", () => { onTimeout?.(); es.close(); });
    es.addEventListener("error",   (e) => {
      try {
        onError?.(JSON.parse(e.data));
      } catch {
        onError?.({ error: "Stream connection error" });
      }
      es.close();
    });

    es.onerror = () => {
      onError?.({ error: "EventSource connection dropped" });
      es.close();
    };

    return es;
  },
};

// ═══════════════════════════════════════════════════════════════════════════
// Health check
// ═══════════════════════════════════════════════════════════════════════════
export const healthApi = {
  check: () => apiClient.get("/health").then((r) => r.data),
};

export default apiClient;
