import { useState } from 'react'
import { api, type ForecastAvailable } from '../api'
import { useApp, useAsync } from '../state'
import { fmtNum, pct, rangeText, rupees } from '../i18n'
import { Async, Card, ConfidenceChip, CropMarketPicker, ErrorBox, FmtDate, Loading, SourceLine, TrendChip } from '../components/common'
import { PriceChart } from '../components/PriceChart'

const RANGES = [
  { days: 7, key: 'days7' },
  { days: 30, key: 'days30' },
  { days: 90, key: 'days90' },
  { days: 365, key: 'days365' },
] as const

export function PricesPage() {
  const { t, lang, selection, setSelection, cropName, marketName, bi } = useApp()
  const { crop, market } = selection
  const [days, setDays] = useState<number>(30)
  const [showLY, setShowLY] = useState(false)

  const hist = useAsync(() => api.history(crop, market, Math.max(days, 7)), [crop, market, days])
  const fc = useAsync(() => api.forecast(crop, market), [crop, market])
  const latest = useAsync(() => api.latest(crop), [crop])

  const f = fc.data && fc.data.available ? (fc.data as ForecastAvailable) : null

  return (
    <div className="page">
      <CropMarketPicker crop={crop} market={market} onChange={(c, m) => setSelection({ crop: c, market: m })} />

      <h1 className="page-title">
        {cropName(crop)}, {marketName(market)}
      </h1>

      {/* Price card */}
      <Card className="price-card">
        <Async state={hist} what={t('todayModal')}>
          {(h) => (
            <>
              <SourceLine date={h.latest?.date} source={h.source} />
              <div className="muted">{t('todayModal')}</div>
              <div className="price-big">
                {rupees(h.latest?.modal)} <span className="unit">{t('perQuintal')}</span>
              </div>
              <div className="kv-row">
                <span>
                  {t('min')} <strong>{rupees(h.latest?.min)}</strong>
                </span>
                <span>
                  {t('max')} <strong>{rupees(h.latest?.max)}</strong>
                </span>
                <span>
                  {t('arrivals')} <strong>{h.latest?.arrivals_t != null ? `${fmtNum(h.latest.arrivals_t, 1)} ${t('tonnes')}` : '—'}</strong>
                </span>
              </div>
              {h.trend && (
                <div className="kv-row">
                  <TrendChip trend={h.trend.label} change={h.trend.change_7d_pct} />
                  <span className="muted small">{t('vsLastWeek')}</span>
                  {h.trend.arrivals_change_7d_pct != null && (
                    <span className="muted small">
                      {t('arrivals')}: {pct(h.trend.arrivals_change_7d_pct)}
                    </span>
                  )}
                </div>
              )}
            </>
          )}
        </Async>
      </Card>

      {/* Forecast card */}
      <Card title={t('next7')} className="forecast-card">
        {fc.error && !fc.data ? (
          <ErrorBox error={fc.error} onRetry={fc.reload} />
        ) : !fc.data ? (
          <Loading />
        ) : !fc.data.available ? (
          <div className="callout">
            <strong>{t('noForecast')}</strong>
            <div>{lang === 'te' ? fc.data.reason_te || fc.data.reason_en : fc.data.reason_en}</div>
          </div>
        ) : (
          f && (
            <>
              <div className="range-big">{rangeText(lang, f.summary.lo, f.summary.hi)}</div>
              <div className="kv-row">
                <span>
                  {t('mostLikely')} <strong>{rupees(f.summary.point_mean)}</strong>
                </span>
                <ConfidenceChip level={f.confidence} />
                <span className="muted small">
                  {t('model')}: {f.model_label}
                </span>
              </div>
              {f.confidence_notes?.length > 0 && (
                <ul className="notes">
                  {f.confidence_notes.map((n, i) => (
                    <li key={i} className="muted small">
                      {bi(n)}
                    </li>
                  ))}
                </ul>
              )}
              {f.anomaly && (
                <div className="callout callout-warn">
                  ⚠ <strong>{t('warning')}:</strong> {bi(f.anomaly)} (<FmtDate iso={f.anomaly.date} />)
                </div>
              )}
              <h3>{t('why')}</h3>
              <ol className="reasons">
                {f.reasons.slice(0, 3).map((r) => (
                  <li key={r.key}>
                    <span>{bi(r)}</span>{' '}
                    <span className={`effect effect-${r.effect}`}>
                      {r.effect === 'up' ? '▲' : '▼'} {r.effect === 'up' ? t('pushesUp') : t('pushesDown')}
                    </span>
                  </li>
                ))}
              </ol>
              <div className="callout callout-good">
                <strong>{t('advice')}:</strong> {bi(f.advice)}{/decision is yours|నిర్ణయం/i.test(bi(f.advice)) ? '' : ` ${t('decisionYours')}`}
              </div>
              <table className="table compact">
                <thead>
                  <tr>
                    <th>{t('date')}</th>
                    <th>{t('mostLikely')}</th>
                    <th>{t('forecastBand')}</th>
                  </tr>
                </thead>
                <tbody>
                  {f.points.map((p) => (
                    <tr key={p.h}>
                      <td>
                        <FmtDate iso={p.date} withYear={false} />
                      </td>
                      <td>{rupees(p.point)}</td>
                      <td>
                        {rupees(p.lo)} – {rupees(p.hi)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )
        )}
      </Card>

      {/* Chart */}
      <Card
        title={t('chartTitle')}
        actions={
          <div className="seg">
            {RANGES.map((r) => (
              <button key={r.days} className={days === r.days ? 'active' : ''} onClick={() => setDays(r.days)}>
                {t(r.key)}
              </button>
            ))}
          </div>
        }
      >
        <label className="check">
          <input type="checkbox" checked={showLY} onChange={(e) => setShowLY(e.target.checked)} /> {t('lastYear')}
        </label>
        <Async state={hist}>
          {(h) => <PriceChart history={h.history ?? []} lastYear={h.last_year ?? []} forecast={f ? f.points : null} showLastYear={showLY} />}
        </Async>
        <p className="guide-note">{t('guideNote')}</p>
      </Card>

      {/* Same crop, all markets */}
      <Card title={t('allMarkets')}>
        <Async state={latest}>
          {(l) => (
            <>
              <p className="muted small">{t('tapToSwitch')}</p>
              <div className="table-scroll">
                <table className="table clickable">
                  <thead>
                    <tr>
                      <th>{t('market')}</th>
                      <th>{t('modal')}</th>
                      <th>{t('change7d')}</th>
                      <th>{t('arrivals')}</th>
                      <th>{t('date')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...l.rows]
                      .sort((a, b) => b.modal - a.modal)
                      .map((r) => (
                        <tr
                          key={r.market}
                          className={r.market === market ? 'row-active' : ''}
                          onClick={() => {
                            setSelection({ crop, market: r.market })
                            window.scrollTo({ top: 0, behavior: 'smooth' })
                          }}
                          tabIndex={0}
                          onKeyDown={(e) => e.key === 'Enter' && setSelection({ crop, market: r.market })}
                        >
                          <td>{marketName(r.market)}</td>
                          <td>
                            <strong>{rupees(r.modal)}</strong>
                          </td>
                          <td>
                            <TrendChip trend={r.trend} change={r.change_7d_pct} />
                          </td>
                          <td>{r.arrivals_t != null ? `${fmtNum(r.arrivals_t, 1)} t` : '—'}</td>
                          <td>
                            <FmtDate iso={r.date} withYear={false} />
                            {r.stale && <span className="chip chip-warn">{t('oldPrice')}</span>}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
              <SourceLine date={l.data_as_of} source={l.source} />
            </>
          )}
        </Async>
      </Card>
    </div>
  )
}
