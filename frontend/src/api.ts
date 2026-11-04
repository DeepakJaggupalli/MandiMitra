// Typed client for the MandiMitra API (see docs/API.md). One place for the base URL.

export const API_BASE = '/api'

export type Lang = 'te' | 'en'
export type Trend = 'rising' | 'falling' | 'steady'
export type Confidence = 'high' | 'medium' | 'low'
export type AnomalyType = 'arrival_flood' | 'price_spike' | 'price_crash'
export type Role = 'admin' | 'officer' | 'fpo'

export interface Source {
  code: 'AGMARKNET' | 'SIMULATED' | 'MIXED' | string
  label_en: string
  label_te: string
  is_simulated: boolean
}

export interface Crop {
  id: string
  en: string
  te: string
  shelf_life_days: number
  markets: string[]
}

export interface Market {
  id: string
  en: string
  te: string
  district: string
  lat: number
  lon: number
}

export interface Meta {
  app: string
  version: string
  generated_at: string
  data_as_of: string
  source: Source
  is_simulated: boolean
  llm_enabled: boolean
  crops: Crop[]
  markets: Market[]
}

export interface Health {
  status: string
  data_as_of: string
  db: string
}

export interface Place {
  id: string
  en: string
  district: string
  lat: number
  lon: number
}

export interface LatestRow {
  market: string
  date: string
  min: number
  max: number
  modal: number
  arrivals_t: number | null
  change_7d_pct: number | null
  trend: Trend
  stale: boolean
}

export interface LatestResponse {
  crop: string
  data_as_of: string
  source: Source
  rows: LatestRow[]
}

export interface PricePoint {
  date: string
  min: number
  max: number
  modal: number
  arrivals_t: number | null
}

export interface PriceTrend {
  label: Trend
  change_7d_pct: number | null
  change_30d_pct: number | null
  arrivals_change_7d_pct: number | null
  down_days_last5: number
  up_days_last5: number
}

export interface PriceHistoryResponse {
  crop: string
  market: string
  data_as_of: string
  source: Source
  latest: PricePoint
  trend: PriceTrend
  history: PricePoint[]
  last_year: { date: string; modal: number }[]
}

export interface Bilingual {
  en: string
  te: string
}

export interface ForecastPoint {
  date: string
  h: number
  point: number
  lo: number
  hi: number
}

export interface Reason extends Bilingual {
  key: string
  effect: 'up' | 'down'
  weight: number
}

export interface Anomaly extends Bilingual {
  type: AnomalyType
  date: string
}

export interface ForecastAvailable {
  available: true
  crop: string
  market: string
  as_of: string
  last_price: number
  model: string
  model_label: string
  confidence: Confidence
  confidence_notes: Bilingual[]
  points: ForecastPoint[]
  summary: { point_mean: number; lo: number; hi: number; direction: 'up' | 'down' | 'flat' }
  reasons: Reason[]
  advice: { action: 'sell_now' | 'wait' | 'either' } & Bilingual
  anomaly: Anomaly | null
  source: Source
  data_as_of: string
}

export interface ForecastUnavailable {
  available: false
  crop: string
  market: string
  reason_en: string
  reason_te: string
}

export type ForecastResponse = ForecastAvailable | ForecastUnavailable

export interface OverviewRow {
  crop: string
  market: string
  date: string
  modal: number
  change_7d_pct: number | null
  trend: Trend
  arrivals_t: number | null
  point_mean: number | null
  lo: number | null
  hi: number | null
  confidence: Confidence | null
  model: string | null
  anomaly_type: AnomalyType | null
}

export interface OverviewResponse {
  data_as_of: string
  source: Source
  rows: OverviewRow[]
}

export interface CompareRequest {
  crop: string
  quantity_qtl: number
  lat: number
  lon: number
  transport_rate_per_qtl_km?: number
  commission_pct?: number
  handling_per_qtl?: number
}

export interface Assumptions {
  transport_rate_per_qtl_km: number
  commission_pct: number
  handling_per_qtl: number
  road_factor: number
}

export interface CompareRow {
  rank: number
  market: string
  date: string
  modal: number
  distance_km: number
  transport: number
  commission: number
  handling: number
  net_per_qtl: number
  net_total: number
  badges: string[]
  flags: string[]
  forecast: { point_mean: number; lo: number; hi: number; confidence: Confidence } | null
}

export interface CompareResponse {
  crop: string
  quantity_qtl: number
  origin: { lat: number; lon: number }
  assumptions: Assumptions
  rows: CompareRow[]
  best_vs_nearest: { best: string; nearest: string; extra_per_qtl: number; extra_total: number } | null
  source: Source
  data_as_of: string
}

export interface AskResponse {
  answer: string
  lang: Lang
  intent: string
  crop: string | null
  market: string | null
  data_date: string | null
  source_label: string | null
  used_llm: boolean
  guard: 'passed' | 'fallback' | 'n/a'
  suggestions: string[]
}

export interface EvalRow {
  question: string
  lang: string
  expected: { intent?: string; crop?: string | null; market?: string | null }
  got: { intent?: string; crop?: string | null; market?: string | null }
  correct: boolean
  answer?: string
  unverified_numbers?: (string | number)[]
}

export interface EvalResponse {
  total: number
  correct: number
  accuracy: number
  target: number
  passed: boolean
  made_up_numbers: number
  rows: EvalRow[]
}

export interface PriceAlert {
  id: string
  crop: string
  market: string
  target: number
  direction: 'above' | 'below'
}

export interface AlertCheckResult {
  id: string
  triggered: boolean
  current: number | null
  date: string | null
}

export interface FeedWarning extends Bilingual {
  id: string
  crop: string
  market: string
  type: AnomalyType
  date: string
  reviewed_at: string | null
}

export interface Bulletin {
  id: number
  week_start: string
  status?: 'draft' | 'approved' | 'held' | string
  title_en: string
  title_te: string
  body_en: string
  body_te: string
  created_at?: string
  created_by?: string | null
  reviewed_by?: string | null
  reviewed_at: string | null
}

export interface FeedResponse {
  warnings: FeedWarning[]
  bulletins: Bulletin[]
}

export interface ModelMape {
  [model: string]: number
}

export interface Criterion {
  key: string
  name_en: string
  name_te: string
  target: string
  value: string
  /** null = pending (e.g. field test not done yet) */
  passed: boolean | null
}

export interface AccuracyResponse {
  generated_at: string
  test_window: { start: string; end: string; days: number }
  calibration_window: { start: string; end: string; days: number }
  model_labels: Record<string, string>
  overall: {
    mape: ModelMape
    best_baseline: string
    improvement_pct: number
    coverage: number
    direction_accuracy: number
    direction_n?: number
  }
  selection_counts?: Record<string, number>
  criteria: Criterion[]
  by_horizon: { h: number; mape: ModelMape }[]
  series: {
    crop: string
    market: string
    n_test: number
    mape: ModelMape
    selected: string
    production_model?: string
    coverage: number
    direction_accuracy: number
    improvement_pct: number
  }[]
}

export interface User {
  username: string
  role: Role
  name: string
}

export interface LoginResponse {
  token: string
  user: User
}

export interface Warning extends Bilingual {
  id: string
  crop: string
  market: string
  type: AnomalyType
  date: string
  magnitude: number | null
  status: 'pending' | 'approved' | 'rejected' | string
  reviewed_by: string | null
  reviewed_at: string | null
  note: string | null
}

export interface QualityReport {
  generated_at: string
  source: Source | string
  rows_raw: number
  rows_clean: number
  duplicates_removed: number
  name_fixes: number
  unit_fixes: number
  unmatched_rows?: number
  checks: { name: string; passed: boolean; detail: string }[]
  series: {
    crop: string
    market: string
    first_date: string
    last_date: string
    days_reported: number
    missing_days: number
    missing_pct: number
    flagged: number
    stale: boolean
  }[]
  flagged: {
    id: string
    crop: string
    market: string
    date: string
    rule: string
    detail: string
    min: number | null
    max: number | null
    modal: number | null
    review: null | { decision: string; by: string; at: string }
  }[]
}

export interface AuditRow {
  id: number
  ts: string
  agent: string
  action: string
  detail: unknown
  actor: string | null
}

export interface PipelineRow {
  ts: string
  agent: string
  action: string
  detail: unknown
  level: 'info' | 'warning' | 'error' | string
}

export interface PipelineResponse {
  generated_at: string
  data_as_of: string
  source: Source
  rows: PipelineRow[]
  history: { date: string; status: string; source: string; data_as_of: string }[]
}

export interface AskContext {
  lat?: number
  lon?: number
  quantity_qtl?: number
}

export interface FeedbackRow {
  id?: number
  ts?: string
  created_at?: string
  question: string
  answer: string
  helpful: boolean
  correction: string | null
}

// ---------------------------------------------------------------------------

const TOKEN_KEY = 'mm_token'

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* storage unavailable */
  }
}

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function request<T>(method: string, path: string, body?: unknown, auth = false): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  const token = getToken()
  if (token && (auth || method !== 'GET' || path.startsWith('/auth') || path.startsWith('/admin'))) {
    headers.Authorization = `Bearer ${token}`
  }
  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  } catch {
    throw new ApiError('Network error — check your internet connection.', 0)
  }
  const text = await res.text()
  let data: unknown = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = text
    }
  }
  if (!res.ok) {
    let msg = `Request failed (${res.status})`
    if (data && typeof data === 'object' && 'detail' in data) {
      const d = (data as { detail: unknown }).detail
      if (typeof d === 'string') msg = d
      else if (Array.isArray(d)) msg = d.map((x) => (x && typeof x === 'object' && 'msg' in x ? String((x as { msg: unknown }).msg) : String(x))).join('; ')
    }
    throw new ApiError(msg, res.status)
  }
  return data as T
}

const enc = encodeURIComponent

export const api = {
  health: () => request<Health>('GET', '/health'),
  meta: () => request<Meta>('GET', '/meta'),
  places: () => request<{ rows: Place[] }>('GET', '/places'),
  latest: (crop: string) => request<LatestResponse>('GET', `/prices/latest?crop=${enc(crop)}`),
  history: (crop: string, market: string, days: number) =>
    request<PriceHistoryResponse>('GET', `/prices/${enc(crop)}/${enc(market)}?days=${days}`),
  forecast: (crop: string, market: string) => request<ForecastResponse>('GET', `/forecast/${enc(crop)}/${enc(market)}`),
  overview: () => request<OverviewResponse>('GET', '/forecast/overview'),
  compare: (body: CompareRequest) => request<CompareResponse>('POST', '/markets/compare', body),
  ask: (question: string, lang: Lang | 'auto', ctx?: AskContext) =>
    request<AskResponse>('POST', '/assistant/ask', { question, lang, ...(ctx ?? {}) }),
  feedback: (body: { question: string; answer: string; helpful: boolean; correction: string | null }) =>
    request<{ ok: boolean }>('POST', '/assistant/feedback', body),
  evalReport: () => request<EvalResponse>('GET', '/assistant/eval'),
  checkAlerts: (alerts: PriceAlert[]) => request<{ results: AlertCheckResult[] }>('POST', '/alerts/check', { alerts }),
  feed: () => request<FeedResponse>('GET', '/alerts/feed'),
  accuracy: () => request<AccuracyResponse>('GET', '/accuracy'),

  login: (username: string, password: string) => request<LoginResponse>('POST', '/auth/login', { username, password }),
  me: () => request<User>('GET', '/auth/me', undefined, true),

  warnings: (status: string) => request<{ rows: Warning[] }>('GET', `/warnings?status=${enc(status)}`, undefined, true),
  reviewWarning: (id: string, decision: 'approve' | 'reject', note?: string) =>
    request<Warning>('POST', `/warnings/${enc(id)}/review`, { decision, note }, true),
  bulletins: (status: string) => request<{ rows: Bulletin[] }>('GET', `/bulletins?status=${enc(status)}`, undefined, true),
  draftBulletin: (week_start?: string) => request<Bulletin>('POST', '/bulletins/draft', week_start ? { week_start } : {}, true),
  updateBulletin: (id: number, body: Pick<Bulletin, 'title_en' | 'title_te' | 'body_en' | 'body_te'>) =>
    request<Bulletin>('PUT', `/bulletins/${id}`, body, true),
  reviewBulletin: (id: number, decision: 'approve' | 'hold') =>
    request<Bulletin>('POST', `/bulletins/${id}/review`, { decision }, true),
  feedbackList: () => request<{ rows: FeedbackRow[] }>('GET', '/assistant/feedback', undefined, true),

  quality: () => request<QualityReport>('GET', '/admin/quality', undefined, true),
  reviewQuality: (id: string, decision: 'accept' | 'exclude') =>
    request<unknown>('POST', `/admin/quality/${enc(id)}/review`, { decision }, true),
  audit: (limit = 100) => request<{ rows: AuditRow[] }>('GET', `/admin/audit?limit=${limit}`, undefined, true),
  pipeline: () => request<PipelineResponse>('GET', '/admin/pipeline', undefined, true),
}

/** Some list endpoints may return a bare array or `{rows: [...]}` — normalise. */
export function rowsOf<T>(data: unknown): T[] {
  if (Array.isArray(data)) return data as T[]
  if (data && typeof data === 'object' && Array.isArray((data as { rows?: unknown }).rows)) return (data as { rows: T[] }).rows
  return []
}
