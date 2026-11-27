import { useEffect } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, type ForecastAvailable } from '../api'
import { useApp, useAsync } from '../state'
import { fmtNum, rangeText, rupees } from '../i18n'
import { Async, ConfidenceChip, FmtDate, SourceLine } from '../components/common'
import { PriceChart } from '../components/PriceChart'
import { SpeakButton, spokenSummary } from '../components/Speak'
import { favKey, useFavs } from '../favs'
import { CROP_ICON } from './Home'

export function PriceDetailPage() {
  const { crop = '', market = '' } = useParams()
  const { t, lang, crop: cropInfo, market: marketInfo, cropName, marketName, bi, setSelection } = useApp()
  const { isFav, toggle } = useFavs()
  const valid = !!cropInfo(crop)?.markets.includes(market)

  useEffect(() => {
    if (valid) setSelection({ crop, market })
  }, [valid, crop, market, setSelection])

  const hist = useAsync(() => (valid ? api.history(crop, market, 7) : null), [crop, market, valid])
  const fc = useAsync(() => (valid ? api.forecast(crop, market) : null), [crop, market, valid])

  if (!valid) {
    return (
      <div className="page">
        <Link to="/" className="back-link">← {t('backAll')}</Link>
        <p>404</p>
      </div>
    )
  }

  const f = fc.data && fc.data.available ? (fc.data as ForecastAvailable) : null
  const key = favKey(crop, market)
  const fav = isFav(key)
  const c = cropInfo(crop)!
  const m = marketInfo(market)!

  return (
    <div className="page">
      <div className="detail-head">
        <Link to="/" className="back-link">← {t('backAll')}</Link>
        <button type="button" className={`btn btn-secondary ${fav ? 'fav-on' : ''}`} onClick={() => toggle(key)} aria-pressed={fav}>
          {fav ? '★' : '☆'} {fav ? t('removeFav') : t('addFav')}
        </button>
      </div>
      <h1 className="page-title">
        <span aria-hidden="true">{CROP_ICON[crop] ?? '🌾'}</span> {cropName(crop)}, {marketName(market)}
      </h1>

      <Async state={hist} what={t('todayPrice')}>
        {(h) => {
          const modal = h.latest?.modal ?? 0
          const say = spokenSummary(c.te, c.en, m.te, m.en, modal, f?.summary.direction ?? null, f?.summary.point_mean ?? null)
          return (
            <>
              <section className="card big-card">
                <div className="muted">{t('todayPrice')}</div>
                <div className="price-big">
                  {rupees(modal)} <span className="unit">{t('perQuintal')}</span>
                </div>
                <SourceLine date={h.latest?.date} source={h.source} />
                <SpeakButton id={`detail-${key}`} te={say.te} en={say.en} big />
              </section>

              <section className="card big-card">
                <div className="muted">{t('next7')}</div>
                {!fc.data ? null : !f ? (
                  <p>{lang === 'te' && fc.data && !fc.data.available ? fc.data.reason_te : t('noForecast')}</p>
                ) : (
                  <>
                    <div className={`dir-big dir-${f.summary.direction}`}>
                      <span aria-hidden="true">{f.summary.direction === 'up' ? '▲' : f.summary.direction === 'down' ? '▼' : '▬'}</span>{' '}
                      {f.summary.direction === 'up' ? t('bigUp') : f.summary.direction === 'down' ? t('bigDown') : t('bigFlat')}
                    </div>
                    <div className="kv-row">
                      <span>
                        {t('mostLikely')} <strong>{rupees(f.summary.point_mean)}</strong>
                      </span>
                      <ConfidenceChip level={f.confidence} />
                    </div>
                    <ul className="day-list">
                      {f.points.map((p) => {
                        const diff = p.point - modal
                        const dir = Math.abs(diff) < modal * 0.02 ? 'flat' : diff > 0 ? 'up' : 'down'
                        return (
                          <li key={p.h}>
                            <span>
                              <FmtDate iso={p.date} withYear={false} />
                            </span>
                            <strong>{rupees(p.point)}</strong>
                            <span className={`dir dir-${dir}`} aria-hidden="true">
                              {dir === 'up' ? '▲' : dir === 'down' ? '▼' : '▬'}
                            </span>
                          </li>
                        )
                      })}
                    </ul>
                    <div className="callout callout-good">{bi(f.advice)}</div>
                  </>
                )}
              </section>

              <details className="card more">
                <summary>{t('moreDetails')}</summary>
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
                {f && (
                  <>
                    <p>
                      {t('forecastBand')}: <strong>{rangeText(lang, f.summary.lo, f.summary.hi)}</strong>
                    </p>
                    {f.anomaly && <div className="callout callout-warn">⚠ {bi(f.anomaly)}</div>}
                    <h3>{t('why')}</h3>
                    <ol className="reasons">
                      {f.reasons.slice(0, 3).map((r) => (
                        <li key={r.key}>{bi(r)}</li>
                      ))}
                    </ol>
                  </>
                )}
                <h3>{t('last7')}</h3>
                <PriceChart history={h.history ?? []} lastYear={[]} forecast={f ? f.points : null} showLastYear={false} />
                <p>
                  <Link to="/markets">{t('whereToSell')} →</Link>
                </p>
                <p className="guide-note">{t('guideNote')}</p>
              </details>
            </>
          )
        }}
      </Async>
    </div>
  )
}
