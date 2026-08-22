export type AuthMode = "builtin" | "proxy" | "disabled";

export interface SetupStatus {
  needs_setup: boolean;
  auth_mode: AuthMode;
  /** Whether the diariser container is running, so the option is worth offering. */
  has_diarizer: boolean;
}

export interface User {
  id: string;
  username: string;
  is_admin: boolean;
}

export type JobStatus = "queued" | "running" | "cancelling" | "cancelled" | "done" | "failed";

export const TERMINAL_STATUSES: readonly JobStatus[] = ["done", "failed", "cancelled"];

export type JobSource = "upload" | "remote_url" | "ytdlp";

export interface Job {
  id: string;
  title: string;
  source_type: JobSource;
  /** The uploaded filename, or the link the job was created from. */
  source_ref: string;
  author: string | null;
  /** A calendar day (YYYY-MM-DD), not an instant: that is all the extractor knows. */
  published_on: string | null;
  has_thumbnail: boolean;
  /** What the recording still costs on disk; null once only the words are left. */
  audio_bytes: number | null;
  diarize: boolean;
  status: JobStatus;
  progress: number;
  language: string | null;
  duration_sec: number | null;
  error_code: string | null;
  error_params: Record<string, unknown>;
  created_at: string;
  finished_at: string | null;
}

export interface TranscriptSegment {
  idx: number;
  start: number;
  end: number;
  text: string;
  /** Whether `text` is a correction. The provider's own words are still there. */
  edited: boolean;
  /** The diariser's label. What it is called on screen lives in `speakers`. */
  speaker: string | null;
}

export interface Speaker {
  id: string;
  label: string;
  display_name: string | null;
}

export interface Transcript {
  job_id: string;
  language: string | null;
  text: string;
  segments: TranscriptSegment[];
  speakers: Speaker[];
}

export interface Preset {
  id: string;
  name: string;
  description: string | null;
  system_prompt: string;
  user_template: string;
  model_override: string | null;
  provider_id: string | null;
  temperature: number | null;
  output_format: string;
  is_builtin: boolean;
  /** Set on builtins. The UI translates this; `name` is the English fallback. */
  builtin_key: string | null;
}

export type PresetDraft = Omit<Preset, "id" | "is_builtin" | "builtin_key">;

export interface Summary {
  id: string;
  job_id: string;
  preset_id: string | null;
  preset_name: string;
  status: JobStatus;
  progress: number;
  content: string;
  partials_json: string | null;
  model_used: string | null;
  error_code: string | null;
  error_params: Record<string, unknown>;
  created_at: string;
  finished_at: string | null;
}

export type ExportFormat = "txt" | "md" | "srt" | "vtt" | "json";

export interface ExportOptions {
  timestamps?: boolean;
  speakers?: boolean;
  download?: boolean;
}

export interface Share {
  token: string;
  job_id: string;
  created_at: string;
  expires_at: string | null;
}

export interface SearchHit {
  job_id: string;
  job_title: string;
  idx: number;
  start: number;
  /** The matched words arrive wrapped in \x02 and \x03, never in markup. */
  excerpt: string;
}

export const MARK_START = "\u0002";
export const MARK_END = "\u0003";

export interface ApiTokenSummary {
  id: string;
  name: string;
  created_at: string;
  last_used_at: string | null;
}

/** Only ever returned by the call that created it. */
export interface CreatedApiToken extends ApiTokenSummary {
  token: string;
}

export interface SharedTranscript {
  job_id: string;
  title: string;
  author: string | null;
  published_on: string | null;
  language: string | null;
  duration_sec: number | null;
  has_audio: boolean;
  text: string;
  segments: TranscriptSegment[];
  /** Read-only: a reader sees the names, and cannot change them. */
  speakers: { label: string; display_name: string | null }[];
}

export type ProviderKind = "stt" | "llm";

export interface Provider {
  id: string;
  kind: ProviderKind;
  name: string;
  base_url: string;
  default_model: string | null;
  context_tokens: number | null;
  is_default: boolean;
  /** Masked, always. The key itself never comes back out of the server. */
  api_key: string | null;
}

export interface ProviderDraft {
  kind: ProviderKind;
  name: string;
  base_url: string;
  /** Omitted keeps the stored key, "" clears it, anything else replaces it. */
  api_key?: string;
  default_model: string | null;
  context_tokens: number | null;
  is_default: boolean;
}

/** How long things are kept. Null means forever, and that is the default. */
export interface Retention {
  audio_days: number | null;
  job_days: number | null;
}

export interface Storage {
  audio_bytes: number;
  other_bytes: number;
  recordings: number;
}

/** What the endpoint said when asked. A refusal is an answer, not an error. */
export interface ProviderProbe {
  reachable: boolean;
  status: number | null;
  latency_ms: number | null;
  models: string[];
  error_code: string | null;
}

/**
 * The API answers with a stable `code`; the UI is multilingual, so the message
 * the user reads comes from the translation bundle, never from the wire.
 */
export class ApiError extends Error {
  constructor(
    readonly code: string,
    readonly status: number,
    readonly params: Record<string, unknown> = {},
  ) {
    super(code);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    const isJson = typeof init?.body === "string";
    response = await fetch(path, {
      credentials: "same-origin",
      headers: isJson ? { "Content-Type": "application/json" } : undefined,
      ...init,
    });
  } catch {
    throw new ApiError("network", 0);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const body = await response.json().catch(() => null);

  if (!response.ok) {
    const error = body?.error;
    throw new ApiError(error?.code ?? "unknown", response.status, error?.params ?? {});
  }

  return body as T;
}

function exportQuery(format: ExportFormat, options: ExportOptions): string {
  const query = new URLSearchParams({ format });
  if (options.timestamps) query.set("timestamps", "true");
  if (options.speakers === false) query.set("speakers", "false");
  if (options.download) query.set("download", "true");
  return query.toString();
}

export const api = {
  setupStatus: () => request<SetupStatus>("/api/setup/status"),

  createFirstAdmin: (username: string, password: string) =>
    request<User>("/api/setup", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),

  login: (username: string, password: string) =>
    request<User>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),

  logout: () => request<void>("/api/auth/logout", { method: "POST" }),

  me: () => request<User>("/api/auth/me"),

  listJobs: () => request<Job[]>("/api/jobs"),

  readJob: (id: string) => request<Job>(`/api/jobs/${id}`),

  readTranscript: (id: string) => request<Transcript>(`/api/jobs/${id}/transcript`),

  uploadJob: (file: File, diarize = false) => {
    const body = new FormData();
    body.append("file", file);
    body.append("diarize", String(diarize));
    // No Content-Type header: the browser has to set the multipart boundary.
    return request<Job>("/api/jobs", { method: "POST", body });
  },

  /** Queue a link. The download happens in the worker, so this returns at once. */
  addUrlJob: (url: string, diarize = false) =>
    request<Job>("/api/jobs/url", { method: "POST", body: JSON.stringify({ url, diarize }) }),

  /** Blank text restores what the provider heard; the original is never lost. */
  correctSegment: (jobId: string, idx: number, text: string) =>
    request<TranscriptSegment>(`/api/jobs/${jobId}/segments/${idx}`, {
      method: "PATCH",
      body: JSON.stringify({ text }),
    }),

  renameSpeaker: (jobId: string, speakerId: string, displayName: string) =>
    request<Speaker>(`/api/jobs/${jobId}/speakers/${speakerId}`, {
      method: "PATCH",
      body: JSON.stringify({ display_name: displayName }),
    }),

  cancelJob: (id: string) => request<Job>(`/api/jobs/${id}/cancel`, { method: "POST" }),

  /** Everything: the words, the audio, the summaries and the share link. */
  deleteJob: (id: string) => request<void>(`/api/jobs/${id}`, { method: "DELETE" }),

  /** The recording only. The transcript stays, and its player goes quiet. */
  deleteJobAudio: (id: string) => request<void>(`/api/jobs/${id}/audio`, { method: "DELETE" }),

  deleteJobs: (ids: string[], audioOnly = false) =>
    request<{ deleted: number; skipped: number }>("/api/jobs/delete", {
      method: "POST",
      body: JSON.stringify({ ids, audio_only: audioOnly }),
    }),

  audioUrl: (id: string) => `/api/jobs/${id}/audio`,

  thumbnailUrl: (id: string) => `/api/jobs/${id}/thumbnail`,

  /** Live job list. One connection for every job, not one per job: browsers cap
   * concurrent requests per origin, and a queue of ten would starve. */
  watchJobs: (onJobs: (jobs: Job[]) => void): (() => void) => {
    const source = new EventSource("/api/jobs/events");
    source.onmessage = (event) => onJobs(JSON.parse(event.data) as Job[]);
    // The server closes the stream once everything is terminal; EventSource
    // would reconnect forever, so close it on the way out.
    source.onerror = () => source.close();
    return () => source.close();
  },

  exportUrl: (jobId: string, format: ExportFormat, options: ExportOptions = {}) =>
    `/api/jobs/${jobId}/export?${exportQuery(format, options)}`,

  /** The same render the download gives, as a string, for the clipboard. */
  readExport: async (jobId: string, format: ExportFormat, options: ExportOptions = {}) => {
    const response = await fetch(api.exportUrl(jobId, format, options), {
      credentials: "same-origin",
    });
    if (!response.ok) throw new ApiError("unknown", response.status);
    return response.text();
  },

  search: (q: string) => request<SearchHit[]>(`/api/search?q=${encodeURIComponent(q)}`),

  createShare: (jobId: string, expiresInDays: number | null = null) =>
    request<Share>(`/api/jobs/${jobId}/share`, {
      method: "POST",
      body: JSON.stringify({ expires_in_days: expiresInDays }),
    }),

  readShare: (jobId: string) => request<Share>(`/api/jobs/${jobId}/share`),

  revokeShare: (jobId: string) => request<void>(`/api/jobs/${jobId}/share`, { method: "DELETE" }),

  readSharedTranscript: (token: string) =>
    request<SharedTranscript>(`/api/public/shares/${token}`),

  sharedAudioUrl: (token: string) => `/api/public/shares/${token}/audio`,

  sharedExportUrl: (token: string, format: ExportFormat, options: ExportOptions = {}) =>
    `/api/public/shares/${token}/export?${exportQuery(format, options)}`,

  listTokens: () => request<ApiTokenSummary[]>("/api/tokens"),

  createToken: (name: string) =>
    request<CreatedApiToken>("/api/tokens", { method: "POST", body: JSON.stringify({ name }) }),

  revokeToken: (id: string) => request<void>(`/api/tokens/${id}`, { method: "DELETE" }),

  readRetention: () => request<Retention>("/api/settings/retention"),

  writeRetention: (policy: Retention) =>
    request<Retention>("/api/settings/retention", {
      method: "PUT",
      body: JSON.stringify(policy),
    }),

  readStorage: () => request<Storage>("/api/settings/storage"),

  listProviders: () => request<Provider[]>("/api/providers"),

  createProvider: (draft: ProviderDraft) =>
    request<Provider>("/api/providers", { method: "POST", body: JSON.stringify(draft) }),

  updateProvider: (id: string, changes: Partial<ProviderDraft>) =>
    request<Provider>(`/api/providers/${id}`, {
      method: "PATCH",
      body: JSON.stringify(changes),
    }),

  deleteProvider: (id: string) => request<void>(`/api/providers/${id}`, { method: "DELETE" }),

  /** Ask an address whether anything lives there — a saved provider by id, or a
   *  draft that has not been committed to yet. */
  testProvider: (target: { provider_id?: string; base_url?: string; api_key?: string }) =>
    request<ProviderProbe>("/api/providers/test", {
      method: "POST",
      body: JSON.stringify(target),
    }),

  listPresets: () => request<Preset[]>("/api/presets"),

  createPreset: (draft: PresetDraft) =>
    request<Preset>("/api/presets", { method: "POST", body: JSON.stringify(draft) }),

  updatePreset: (id: string, draft: PresetDraft) =>
    request<Preset>(`/api/presets/${id}`, { method: "PUT", body: JSON.stringify(draft) }),

  deletePreset: (id: string) => request<void>(`/api/presets/${id}`, { method: "DELETE" }),

  listSummaries: (jobId: string) => request<Summary[]>(`/api/jobs/${jobId}/summaries`),

  createSummary: (jobId: string, presetId: string) =>
    request<Summary>(`/api/jobs/${jobId}/summaries`, {
      method: "POST",
      body: JSON.stringify({ preset_id: presetId }),
    }),

  deleteSummary: (id: string) => request<void>(`/api/summaries/${id}`, { method: "DELETE" }),

  /** Follow one summary as the worker writes it. */
  watchSummary: (id: string, onSummary: (summary: Summary) => void): (() => void) => {
    const source = new EventSource(`/api/summaries/${id}/events`);
    source.onmessage = (event) => onSummary(JSON.parse(event.data) as Summary);
    source.onerror = () => source.close();
    return () => source.close();
  },
};
