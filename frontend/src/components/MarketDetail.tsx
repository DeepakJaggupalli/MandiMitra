import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type ForecastAvailable, type ForecastResponse, type PriceHistoryResponse } from '../api'
import { useApp, useAsync } from '../state'
import { fmtDate, fmtNum, rangeText, rupees } from '../i18n'
import { Async, ConfidenceChip, FmtDate, SourceLine, TrendChip } from './common'
import { PriceChart } from './PriceChart'
import { SpeakButton, spokenSummary } from './Speak'

const RANGES = [
  { days: 7, key: 'days7' },
  { days: 30, key: 'days30' },
  { days: 90, key: 'days90' },
  { days: 365, key: 'days365' },
] as const

/**
 * Price + 7-day outlook for one crop at one market.
 * Phone: today's price, next 7 days and Listen; everything else folded under "More details".
 * Desktop: the full view in two columns — chart with ranges, reasons and every market for the crop always visible.
 */
export function MarketDetail({ crop, market, desktop, onPickMarket }: {
  crop: string
  market: string
  desktop: boolean
  onPickMarket?: (market: string) => void
}) {
  const { t, lang, crop: cropInfo, market: marketInfo, bi } = useApp()
  const [days, setDays] = useState<number>(30)
  const [showLY, setShowLY] = useState(false)
  const span = desktop ? days : 7
  const hist = useAsync(() => api.history(crop, market, span), [crop, market, span])
  const fc = useAsync(() => api.forecast(crop, market), [crop, market])
  const latest = useAsync(() => (desktop ? api.latest(crop) : null), [crop, desktop])
  const f = fc.data && fc.data.available ? (fc.data as ForecastAvailable) : null
  const c = cropInfo(crop)
  const m = marketInfo(market)
  if (!c || !m) return null
  const key = `${crop}|${market}`

  const priceCard = (h: PriceHistoryResponse) => {
    const modal = h.latest?.modal ?? 0
    const old = !!h.latest?.date && h.latest.date !== h.data_as_of
    const say = spokenSummary(c.te, c.en, m.te, m.en, modal, f?.summary.direction ?? null, f?.summary.point_mean ?? null,
      old ? fmtDate(h.latest!.date, 'te', false) : null, old ? fmtDate(h.latest!.date, 'en', false) : null)
    return (
      <section className="card big-card">
        <div className="muted">{old ? t('priceOn', { date: fmtDate(h.latest!.date, lang) }) : t('todayPrice')}</div>
        <div className="price-big">
          {rupees(modal)} <span className="unit">{t('perQuintal')}</span>
        </div>
        {h.frozen_since && <div className="callout callout-warn">⚠ {t('frozenNote', { date: fmtDate(h.frozen_since, lang) })}</div>}
        {h.price_method === 'median' ? (
          <div className="muted small">
            {(h.main_varieties?.length ?? 0) > 1 ? t('mainVarieties', { n: h.main_varieties!.length }) : t('allVarietiesMedian')}
          </div>
        ) : h.variety ? (
          <div className="muted small">
            {t('varietyLabel')}: {h.variety}
            {h.grade && h.grade !== h.variety ? ` (${h.grade})` : ''}
          </div>
        ) : null}
        {desktop && (
          <div className="kv-row">
            <span>
              {t('min')} <strong>{rupees(h.latest?.min)}</strong>
            </span>
            <span>
              {t('max')} <strong>{rupees(h.latest?.max)}</strong>
            </span>
            {h.trend && <TrendChip trend={h.trend.label} change={h.trend.change_7d_pct} />}
          </div>
        )}
        <SourceLine date={h.latest?.date} source={h.source} />
        <SpeakButton id={`detail-${key}`} te={say.te} en={say.en} big />
        {(h.varieties_today?.length ?? 0) > 1 && (
          <div className="varieties">
            <div className="muted small">{t('byVariety')}</div>
            <ul>
              {h.varieties_today!.map((v, i) => (
                <li key={i}>
                  <span>
                    {v.variety}
                    {v.grade && v.grade !== v.variety ? <small> · {v.grade}</small> : null}
                  </span>
                  <strong>{rupees(v.modal)}</strong>
                  <small className="muted">
                    {rupees(v.min)}–{rupees(v.max)}
                  </small>
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>
    )
  }

  const forecastCard = (data: ForecastResponse | null) => (
    <section className="card big-card">
      <div className="muted">{t('next7')}</div>
      {!data ? null : !f ? (
        <p>{lang === 'te' && !data.available ? data.reason_te : t('noForecast')}</p>
      ) : (
        <>
          <div className={`dir-big dir-${f.summary.direction}`}>
            {f.summary.direction !== 'unclear' && (
              <span aria-hidden="true">{f.summary.direction === 'up' ? '▲' : f.summary.direction === 'down' ? '▼' : '▬'} </span>
            )}
            {f.summary.direction === 'up'
              ? t('bigUp')
              : f.summary.direction === 'down'
                ? t('bigDown')
                : f.summary.direction === 'unclear'
                  ? t('bigUnclear')
                  : t('bigFlat')}
          </div>
          {f.summary.direction === 'unclear' ? (
            <div className="kv-row">
              <span>
                {t('weekRange')} <strong>{rangeText(lang, f.summary.lo, f.summary.hi)}</strong>
              </span>
              <ConfidenceChip level={f.confidence} />
            </div>
          ) : (
            <>
              <div className="kv-row">
                <span>
                  {t('mostLikely')} <strong>{rupees(f.summary.point_mean)}</strong>
                </span>
                <ConfidenceChip level={f.confidence} />
              </div>
              <ul className="day-list">
                {f.points.map((p) => (
                  <li key={p.h}>
                    <span>
                      <FmtDate iso={p.date} withYear={false} />
                    </span>
                    <strong>{rupees(p.point)}</strong>
                  </li>
                ))}
              </ul>
            </>
          )}
          <div className="callout callout-good">{bi(f.advice)}</div>
        </>
      )}
    </section>
  )

  const reasons = f && f.reasons.length > 0 && (
    <>
      <h3>{t('why')}</h3>
      <ol className="reasons">
        {f.reasons.slice(0, 3).map((r) => (
          <li key={r.key}>
            {bi(r)}{' '}
            <span className={`effect effect-${r.effect}`}>
              ({r.effect === 'up' ? `▲ ${t('pushesUpShort')}` : `▼ ${t('pushesDownShort')}`})
            </span>
          </li>
        ))}
      </ol>
    </>
  )

  if (!desktop) {
    return (
      <Async state={hist} what={t('todayPrice')}>
        {(h) => (
          <>
            {priceCard(h)}
            {forecastCard(fc.data)}
            <details className="card more">
              <summary>{t('moreDetails')}</summary>
              <div className="kv-row">
                <span>
                  {t('min')} <strong>{rupees(h.latest?.min)}</strong>
                </span>
                <span>
                  {t('max')} <strong>{rupees(h.latest?.max)}</strong>
                </span>
                {h.latest?.arrivals_t != null && (
                  <span>
                    {t('arrivals')} <strong>{`${fmtNum(h.latest.arrivals_t, 1)} ${t('tonnes')}`}</strong>
                  </span>
                )}
              </div>
              {f && (
                <p>
                  {t('forecastBand')}: <strong>{rangeText(lang, f.summary.lo, f.summary.hi)}</strong>
                </p>
              )}
              {reasons}
              <h3>{t('last7')}</h3>
              <PriceChart history={h.history ?? []} lastYear={[]} forecast={f ? f.points : null} showLastYear={false} />
              <p>
                <Link to="/markets">{t('whereToSell')} →</Link>
              </p>
              <p className="guide-note">{t('guideNote')}</p>
            </details>
          </>
        )}
      </Async>
    )
  }

  // ---- desktop: full view, two columns
  return (
    <Async state={hist} what={t('todayPrice')}>
      {(h) => (
        <div className="desk-detail">
          <div className="desk-col">
            {priceCard(h)}
            {forecastCard(fc.data)}
          </div>
          <div className="desk-col">
            <section className="card">
              <div className="card-head">
                <h2>{t('chartTitle')}</h2>
                <div className="seg">
                  {RANGES.map((r) => (
                    <button key={r.days} className={days === r.days ? 'active' : ''} onClick={() => setDays(r.days)}>
                      {t(r.key)}
                    </button>
                  ))}
                </div>
              </div>
              <label className="check">
                <input type="checkbox" checked={showLY} onChange={(e) => setShowLY(e.target.checked)} /> {t('lastYear')}
              </label>
              <PriceChart history={h.history ?? []} lastYear={h.last_year ?? []} forecast={f ? f.points : null} showLastYear={showLY} />
              {f && (
                <p className="muted small">
                  {t('forecastBand')}: <strong>{rangeText(lang, f.summary.lo, f.summary.hi)}</strong>
                </p>
              )}
              <p className="guide-note">{t('guideNote')}</p>
            </section>
            {reasons && <section className="card">{reasons}</section>}
            <section className="card">
              <div className="card-head">
                <h2>{t('allMarkets')}</h2>
                <Link to="/markets">{t('whereToSell')} →</Link>
              </div>
              <Async state={latest}>
                {(l) => (
                  <div className="table-scroll">
                    <table className="table clickable">
                      <thead>
                        <tr>
                          <th>{t('market')}</th>
                          <th>{t('modal')}</th>
                          <th>{t('change7d')}</th>
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
                              onClick={() => onPickMarket?.(r.market)}
                              tabIndex={0}
                              onKeyDown={(e) => e.key === 'Enter' && onPickMarket?.(r.market)}
                            >
                              <td>{marketInfo(r.market)?.[lang] ?? r.market}</td>
                              <td>
                                <strong>{rupees(r.modal)}</strong>
                              </td>
                              <td>
                                <TrendChip trend={r.trend} change={r.change_7d_pct} />
                              </td>
                              <td>
                                <FmtDate iso={r.date} withYear={false} />
                                {r.stale && <span className="chip chip-warn">{t('oldPrice')}</span>}
                              </td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Async>
            </section>
          </div>
        </div>
      )}
    </Async>
  )
}
