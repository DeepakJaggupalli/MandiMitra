import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { api, getToken, setToken, type Crop, type Lang, type Market, type Meta, type PriceAlert, type User } from './api'
import { translate, type DictKey } from './i18n'

// ---- safe storage ------------------------------------------------------------

export function loadJSON<T>(key: string, fallback: T, store: 'local' | 'session' = 'local'): T {
  try {
    const s = (store === 'local' ? localStorage : sessionStorage).getItem(key)
    return s ? (JSON.parse(s) as T) : fallback
  } catch {
    return fallback
  }
}

export function saveJSON(key: string, value: unknown, store: 'local' | 'session' = 'local') {
  try {
    ;(store === 'local' ? localStorage : sessionStorage).setItem(key, JSON.stringify(value))
  } catch {
    /* storage unavailable */
  }
}

// ---- app context -------------------------------------------------------------

interface AppState {
  lang: Lang
  setLang: (l: Lang) => void
  t: (key: DictKey, vars?: Record<string, string | number>) => string
  meta: Meta | null
  metaError: string | null
  reloadMeta: () => void
  user: User | null
  login: (username: string, password: string) => Promise<User>
  logout: () => void
  cropName: (id: string | null | undefined) => string
  marketName: (id: string | null | undefined) => string
  crop: (id: string) => Crop | undefined
  market: (id: string) => Market | undefined
  sourceLabel: (s: { label_en: string; label_te: string } | null | undefined) => string
  bi: (o: { en: string; te: string } | null | undefined) => string
  online: boolean
  selection: { crop: string; market: string }
  setSelection: (s: { crop: string; market: string }) => void
  alerts: PriceAlert[]
  setAlerts: (a: PriceAlert[]) => void
  addAlert: (a: Omit<PriceAlert, 'id'>) => void
}

const Ctx = createContext<AppState | null>(null)

export function AppProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(() => {
    const l = loadJSON<string>('mm_lang', 'te')
    return l === 'en' ? 'en' : 'te'
  })
  const [meta, setMeta] = useState<Meta | null>(null)
  const [metaError, setMetaError] = useState<string | null>(null)
  const [user, setUser] = useState<User | null>(() => loadJSON<User | null>('mm_user', null))
  const [online, setOnline] = useState<boolean>(typeof navigator === 'undefined' ? true : navigator.onLine)
  const [selection, setSelectionState] = useState(() => loadJSON('mm_sel', { crop: 'tomato', market: 'madanapalle' }))
  const [alerts, setAlertsState] = useState<PriceAlert[]>(() => loadJSON<PriceAlert[]>('mm_alerts', []))

  const setLang = useCallback((l: Lang) => {
    setLangState(l)
    saveJSON('mm_lang', l)
  }, [])

  useEffect(() => {
    document.documentElement.lang = lang
  }, [lang])

  const reloadMeta = useCallback(() => {
    setMetaError(null)
    api
      .meta()
      .then((m) => setMeta(m))
      .catch((e: Error) => setMetaError(e.message))
  }, [])

  useEffect(() => {
    reloadMeta()
  }, [reloadMeta])

  // keep selection valid against meta
  useEffect(() => {
    if (!meta || meta.crops.length === 0) return
    const c = meta.crops.find((x) => x.id === selection.crop) ?? meta.crops[0]
    const m = c.markets.includes(selection.market) ? selection.market : c.markets[0]
    if (c.id !== selection.crop || m !== selection.market) {
      setSelectionState({ crop: c.id, market: m })
      saveJSON('mm_sel', { crop: c.id, market: m })
    }
  }, [meta, selection.crop, selection.market])

  // verify a stored token is still valid
  const checked = useRef(false)
  useEffect(() => {
    if (checked.current) return
    checked.current = true
    if (!getToken()) {
      setUser(null)
      return
    }
    api
      .me()
      .then((u) => {
        setUser(u)
        saveJSON('mm_user', u)
      })
      .catch((e: { status?: number }) => {
        if (e.status === 401 || e.status === 403) {
          setToken(null)
          setUser(null)
          saveJSON('mm_user', null)
        }
      })
  }, [])

  useEffect(() => {
    const on = () => setOnline(true)
    const off = () => setOnline(false)
    window.addEventListener('online', on)
    window.addEventListener('offline', off)
    return () => {
      window.removeEventListener('online', on)
      window.removeEventListener('offline', off)
    }
  }, [])

  const login = useCallback(async (username: string, password: string) => {
    const r = await api.login(username, password)
    setToken(r.token)
    setUser(r.user)
    saveJSON('mm_user', r.user)
    return r.user
  }, [])

  const logout = useCallback(() => {
    setToken(null)
    setUser(null)
    saveJSON('mm_user', null)
  }, [])

  const setSelection = useCallback((s: { crop: string; market: string }) => {
    setSelectionState(s)
    saveJSON('mm_sel', s)
  }, [])

  const setAlerts = useCallback((a: PriceAlert[]) => {
    setAlertsState(a)
    saveJSON('mm_alerts', a)
  }, [])

  const addAlert = useCallback((a: Omit<PriceAlert, 'id'>) => {
    setAlertsState((prev) => {
      const next = [...prev, { ...a, id: `a${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}` }]
      saveJSON('mm_alerts', next)
      return next
    })
    if (typeof Notification !== 'undefined' && Notification.permission === 'default') {
      Notification.requestPermission().catch(() => undefined)
    }
  }, [])

  const value = useMemo<AppState>(() => {
    const t = (key: DictKey, vars?: Record<string, string | number>) => translate(lang, key, vars)
    const crop = (id: string) => meta?.crops.find((c) => c.id === id)
    const market = (id: string) => meta?.markets.find((m) => m.id === id)
    return {
      lang,
      setLang,
      t,
      meta,
      metaError,
      reloadMeta,
      user,
      login,
      logout,
      crop,
      market,
      cropName: (id) => {
        if (!id) return '—'
        const c = crop(id)
        return c ? c[lang] : id
      },
      marketName: (id) => {
        if (!id) return '—'
        const m = market(id)
        return m ? m[lang] : id
      },
      sourceLabel: (s) => (s ? (lang === 'te' ? s.label_te || s.label_en : s.label_en) : ''),
      bi: (o) => (o ? (lang === 'te' ? o.te || o.en : o.en) : ''),
      online,
      selection,
      setSelection,
      alerts,
      setAlerts,
      addAlert,
    }
  }, [lang, setLang, meta, metaError, reloadMeta, user, login, logout, online, selection, setSelection, alerts, setAlerts, addAlert])

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useApp(): AppState {
  const v = useContext(Ctx)
  if (!v) throw new Error('useApp must be used inside AppProvider')
  return v
}

// ---- data hook ----------------------------------------------------------------

export interface AsyncState<T> {
  data: T | null
  error: string | null
  loading: boolean
  reload: () => void
}

/** Runs `fn` whenever `deps` change; `fn` returning null skips the call. */
export function useAsync<T>(fn: () => Promise<T> | null, deps: unknown[]): AsyncState<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [tick, setTick] = useState(0)

  useEffect(() => {
    let alive = true
    const p = fn()
    if (!p) {
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    p.then((d) => {
      if (alive) {
        setData(d)
        setLoading(false)
      }
    }).catch((e: Error) => {
      if (alive) {
        setError(e.message || 'Error')
        setLoading(false)
      }
    })
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick])

  const reload = useCallback(() => setTick((x) => x + 1), [])
  return { data, error, loading, reload }
}
