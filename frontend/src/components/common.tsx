import type { ReactNode } from 'react'
import type { Confidence, Trend } from '../api'
import { useApp } from '../state'
import { fmtDate, pct } from '../i18n'

export function Loading({ label }: { label?: string }) {
  const { t } = useApp()
  return (
    <div className="status loading" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" /> {label ?? t('loading')}
    </div>
  )
}

export function ErrorBox({ error, onRetry, what }: { error: string; onRetry?: () => void; what?: string }) {
  const { t } = useApp()
  return (
    <div className="status error" role="alert">
      <div>
        <strong>{t('errorPrefix')}{what ? `: ${what}` : ''}</strong>
        <div className="muted small">{error}</div>
      </div>
      {onRetry && (
        <button className="btn btn-secondary" onClick={onRetry}>
          {t('retry')}
        </button>
      )}
    </div>
  )
}

/** Renders loading / error / children for an async state. */
export function Async<T>({
  state,
  what,
  children,
}: {
  state: { data: T | null; error: string | null; loading: boolean; reload: () => void }
  what?: string
  children: (data: T) => ReactNode
}) {
  if (state.error && !state.data) return <ErrorBox error={state.error} onRetry={state.reload} what={what} />
  if (!state.data) return <Loading />
  return (
    <>
      {state.error && <ErrorBox error={state.error} onRetry={state.reload} what={what} />}
      {children(state.data)}
    </>
  )
}

export function TrendChip({ trend, change }: { trend: Trend; change?: number | null }) {
  const { t } = useApp()
  const arrow = trend === 'rising' ? '▲' : trend === 'falling' ? '▼' : '▬'
  return (
    <span className={`chip trend-${trend}`}>
      <span aria-hidden="true">{arrow}</span> {t(trend)}
      {change !== undefined && change !== null ? ` ${pct(change)}` : ''}
    </span>
  )
}

export function ConfidenceChip({ level, short = false }: { level: Confidence | null | undefined; short?: boolean }) {
  const { t } = useApp()
  if (!level) return <span className="muted">—</span>
  return <span className={`chip conf-${level}`}>{short ? t(`confShort_${level}`) : t(`conf_${level}`)}</span>
}

export function PassChip({ passed }: { passed: boolean | null | undefined }) {
  const { t } = useApp()
  if (passed === null || passed === undefined) return <span className="chip chip-pending">⏳ {t('pending')}</span>
  return <span className={`chip ${passed ? 'chip-pass' : 'chip-fail'}`}>{passed ? `✓ ${t('pass')}` : `✗ ${t('fail')}`}</span>
}

export function Card({ title, children, actions, className }: { title?: ReactNode; children: ReactNode; actions?: ReactNode; className?: string }) {
  return (
    <section className={`card ${className ?? ''}`}>
      {(title || actions) && (
        <div className="card-head">
          {title && <h2>{title}</h2>}
          {actions && <div className="card-actions">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  )
}

export function SourceLine({ date, source }: { date: string | null | undefined; source: { label_en: string; label_te: string } | null | undefined }) {
  const { t, sourceLabel } = useApp()
  return (
    <p className="source-line">
      {t('updated')}: <FmtDate iso={date} /> · {t('source')}: {sourceLabel(source)}
    </p>
  )
}

export function FmtDate({ iso, withYear = true }: { iso: string | null | undefined; withYear?: boolean }) {
  const { lang } = useApp()
  return <>{fmtDate(iso, lang, withYear)}</>
}

export function CropMarketPicker({
  crop,
  market,
  onChange,
  showMarket = true,
}: {
  crop: string
  market?: string
  onChange: (crop: string, market: string) => void
  showMarket?: boolean
}) {
  const { meta, t, lang } = useApp()
  if (!meta) return null
  const c = meta.crops.find((x) => x.id === crop) ?? meta.crops[0]
  const markets = c ? meta.markets.filter((m) => c.markets.includes(m.id)) : []
  return (
    <div className="picker">
      <label className="field">
        <span>{t('crop')}</span>
        <select
          value={c?.id ?? ''}
          onChange={(e) => {
            const nc = meta.crops.find((x) => x.id === e.target.value)
            if (!nc) return
            const nm = market && nc.markets.includes(market) ? market : nc.markets[0]
            onChange(nc.id, nm)
          }}
        >
          {meta.crops.map((x) => (
            <option key={x.id} value={x.id}>
              {x[lang]}
            </option>
          ))}
        </select>
      </label>
      {showMarket && (
        <label className="field">
          <span>{t('market')}</span>
          <select value={market ?? ''} onChange={(e) => onChange(c.id, e.target.value)}>
            {markets.map((m) => (
              <option key={m.id} value={m.id}>
                {m[lang]}
              </option>
            ))}
          </select>
        </label>
      )}
    </div>
  )
}
