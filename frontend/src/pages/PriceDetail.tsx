import { useEffect } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, type ForecastAvailable } from '../api'
import { useApp, useAsync } from '../state'
import { fmtDate, fmtNum, rangeText, rupees } from '../i18n'
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
          const old = !!h.latest?.date && h.latest.date !== h.data_as_of
          const say = spokenSummary(c.te, c.en, m.te, m.en, modal, f?.summary.direction ?? null, f?.summary.point_mean ?? null,
            old ? fmtDate(h.latest!.date, 'te', false) : null, old ? fmtDate(h.latest!.date, 'en', false) : null)
          return (
            <>
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

              <section className="card big-card">
                <div className="muted">{t('next7')}</div>
                {!fc.data ? null : !f ? (
                  <p>{lang === 'te' && fc.data && !fc.data.available ? fc.data.reason_te : t('noForecast')}</p>
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
                  <>
                    <p>
                      {t('forecastBand')}: <strong>{rangeText(lang, f.summary.lo, f.summary.hi)}</strong>
                    </p>
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
