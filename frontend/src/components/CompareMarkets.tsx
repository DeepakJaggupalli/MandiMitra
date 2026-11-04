import { useEffect, useMemo, useRef, useState } from 'react'
import { api, type CompareResponse, type Place } from '../api'
import { loadJSON, saveJSON, useApp, useAsync } from '../state'
import { rangeText, rupees, fmtNum } from '../i18n'
import { ConfidenceChip, ErrorBox, FmtDate, Loading } from './common'
import { MarketMap } from './MarketMap'

interface Costs {
  rate: string
  commission: string
  handling: string
}

function haversineKm(a: { lat: number; lon: number }, b: { lat: number; lon: number }) {
  const R = 6371
  const dLat = ((b.lat - a.lat) * Math.PI) / 180
  const dLon = ((b.lon - a.lon) * Math.PI) / 180
  const s = Math.sin(dLat / 2) ** 2 + Math.cos((a.lat * Math.PI) / 180) * Math.cos((b.lat * Math.PI) / 180) * Math.sin(dLon / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(s))
}

export function CompareMarkets({
  unit = 'qtl',
  topN,
  showMap = true,
  showAlert = true,
  storageKey = 'mm_compare',
}: {
  unit?: 'qtl' | 't'
  topN?: number
  showMap?: boolean
  showAlert?: boolean
  storageKey?: string
}) {
  const { t, lang, meta, selection, marketName, market, addAlert, sourceLabel } = useApp()
  const saved = loadJSON(storageKey, { crop: selection.crop, qty: unit === 't' ? '10' : '20', place: '' })
  const [crop, setCrop] = useState<string>(saved.crop)
  const [qty, setQty] = useState<string>(saved.qty)
  const [placeId, setPlaceId] = useState<string>(saved.place)
  const [geo, setGeo] = useState<{ lat: number; lon: number } | null>(null)
  const [geoMsg, setGeoMsg] = useState<string | null>(null)
  const [costs, setCosts] = useState<Costs | null>(loadJSON<Costs | null>('mm_costs', null))
  const [result, setResult] = useState<CompareResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [alertPrice, setAlertPrice] = useState<string>('')
  const [alertMarket, setAlertMarket] = useState<string>('')
  const [alertMsg, setAlertMsg] = useState<string | null>(null)
  const places = useAsync(() => api.places(), [])

  const placeRows: Place[] = places.data?.rows ?? []

  // default pickup: the place nearest to the selected market
  useEffect(() => {
    if (placeId || placeRows.length === 0) return
    const m = market(selection.market)
    let best = placeRows[0]
    if (m) {
      let bd = Infinity
      for (const p of placeRows) {
        const d = haversineKm(p, m)
        if (d < bd) {
          bd = d
          best = p
        }
      }
    }
    setPlaceId(best.id)
  }, [placeRows, placeId, market, selection.market])

  useEffect(() => {
    if (meta && !meta.crops.some((c) => c.id === crop) && meta.crops.length) setCrop(meta.crops[0].id)
  }, [meta, crop])

  const origin = useMemo(() => {
    if (placeId === '__geo' && geo) return geo
    const p = placeRows.find((x) => x.id === placeId)
    return p ? { lat: p.lat, lon: p.lon } : null
  }, [placeId, geo, placeRows])

  const qtyNum = Number(qty)
  const quantityQtl = unit === 't' ? qtyNum * 10 : qtyNum

  const reqId = useRef(0)
  const run = () => {
    if (!origin || !crop || !(quantityQtl > 0)) return
    const id = ++reqId.current
    setBusy(true)
    setError(null)
    const body = {
      crop,
      quantity_qtl: quantityQtl,
      lat: origin.lat,
      lon: origin.lon,
      ...(costs && costs.rate !== '' && !Number.isNaN(Number(costs.rate)) ? { transport_rate_per_qtl_km: Number(costs.rate) } : {}),
      ...(costs && costs.commission !== '' && !Number.isNaN(Number(costs.commission)) ? { commission_pct: Number(costs.commission) } : {}),
      ...(costs && costs.handling !== '' && !Number.isNaN(Number(costs.handling)) ? { handling_per_qtl: Number(costs.handling) } : {}),
    }
    api
      .compare(body)
      .then((r) => {
        if (id !== reqId.current) return
        setResult(r)
        setBusy(false)
        if (!costs) {
          setCosts({
            rate: String(r.assumptions.transport_rate_per_qtl_km),
            commission: String(r.assumptions.commission_pct),
            handling: String(r.assumptions.handling_per_qtl),
          })
        }
        if (r.rows.length && !alertMarket) {
          setAlertMarket(r.rows[0].market)
        }
      })
      .catch((e: Error) => {
        if (id !== reqId.current) return
        setError(e.message)
        setBusy(false)
      })
  }

  // auto-run (debounced) when inputs change
  useEffect(() => {
    const h = setTimeout(run, 350)
    return () => clearTimeout(h)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [crop, quantityQtl, origin?.lat, origin?.lon, costs?.rate, costs?.commission, costs?.handling])

  useEffect(() => {
    saveJSON(storageKey, { crop, qty, place: placeId === '__geo' ? '' : placeId })
  }, [crop, qty, placeId, storageKey])

  useEffect(() => {
    if (costs) saveJSON('mm_costs', costs)
  }, [costs])

  // remember the farmer's pickup point + lot size so the assistant can answer "where should I sell" for them
  useEffect(() => {
    if (!origin || storageKey !== 'mm_compare') return
    const label = placeId === '__geo' ? 'geo' : placeRows.find((x) => x.id === placeId)?.en ?? ''
    saveJSON('mm_origin', { lat: origin.lat, lon: origin.lon, label, quantity_qtl: quantityQtl > 0 ? quantityQtl : undefined })
  }, [origin, placeId, placeRows, quantityQtl, storageKey])

  const locate = () => {
    if (!navigator.geolocation) {
      setGeoMsg(t('locationFailed'))
      return
    }
    setGeoMsg(t('locating'))
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setGeo({ lat: pos.coords.latitude, lon: pos.coords.longitude })
        setPlaceId('__geo')
        setGeoMsg(null)
      },
      () => setGeoMsg(t('locationFailed')),
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 600000 },
    )
  }

  const rows = result ? (topN ? result.rows.slice(0, topN) : result.rows) : []
  const bvn = result?.best_vs_nearest

  return (
    <div className="compare">
      <div className="form-grid">
        <label className="field">
          <span>{t('crop')}</span>
          <select value={crop} onChange={(e) => setCrop(e.target.value)}>
            {meta?.crops.map((c) => (
              <option key={c.id} value={c.id}>
                {c[lang]}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>
            {unit === 't' ? t('quantityTonnes') : `${t('quantity')} (${t('quintals')})`}
          </span>
          <input type="number" inputMode="decimal" min={0.1} step={unit === 't' ? 0.5 : 1} value={qty} onChange={(e) => setQty(e.target.value)} />
        </label>
        <label className="field field-wide">
          <span>{t('pickup')}</span>
          <div className="row-inline">
            <select value={placeId} onChange={(e) => setPlaceId(e.target.value)}>
              {placeId === '__geo' && <option value="__geo">{t('myLocation')}</option>}
              {placeRows.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.en} ({p.district})
                </option>
              ))}
            </select>
            <button type="button" className="btn btn-secondary" onClick={locate}>
              📍 {t('useLocation')}
            </button>
          </div>
          {geoMsg && <small className="muted">{geoMsg}</small>}
          {places.error && <ErrorBox error={places.error} onRetry={places.reload} />}
        </label>
      </div>

      <details className="costs">
        <summary>{t('advanced')}</summary>
        <div className="form-grid">
          <label className="field">
            <span>{t('transportRate')}</span>
            <input
              type="number"
              inputMode="decimal"
              step={0.05}
              min={0}
              value={costs?.rate ?? ''}
              onChange={(e) => setCosts({ rate: e.target.value, commission: costs?.commission ?? '', handling: costs?.handling ?? '' })}
            />
          </label>
          <label className="field">
            <span>{t('commissionPct')}</span>
            <input
              type="number"
              inputMode="decimal"
              step={0.5}
              min={0}
              max={30}
              value={costs?.commission ?? ''}
              onChange={(e) => setCosts({ rate: costs?.rate ?? '', commission: e.target.value, handling: costs?.handling ?? '' })}
            />
          </label>
          <label className="field">
            <span>{t('handling')}</span>
            <input
              type="number"
              inputMode="decimal"
              step={1}
              min={0}
              value={costs?.handling ?? ''}
              onChange={(e) => setCosts({ rate: costs?.rate ?? '', commission: costs?.commission ?? '', handling: e.target.value })}
            />
          </label>
        </div>
      </details>
      <div className="row-inline">
        <button className="btn btn-primary" onClick={run} disabled={busy || !origin}>
          {t('compare')}
        </button>
        {busy && <span className="spinner" aria-label={t('loading')} />}
      </div>

      {error && <ErrorBox error={error} onRetry={run} />}
      {!result && !error && (busy || places.loading) && <Loading />}

      {result && (
        <>
          <p className="muted small">{t('moneyInHand')}</p>
          {bvn && (
            <div className="callout callout-good">
              {bvn.best === bvn.nearest || bvn.extra_total <= 0
                ? t('summaryNearestBest', { nearest: marketName(bvn.nearest) })
                : t('summaryLine', {
                    best: marketName(bvn.best),
                    extra: rupees(bvn.extra_total),
                    qty: fmtNum(result.quantity_qtl, 1),
                    nearest: marketName(bvn.nearest),
                  })}
            </div>
          )}
          <ol className="rank-list">
            {rows.map((r) => (
              <li key={r.market} className={`rank-card ${r.badges.includes('best') ? 'is-best' : ''}`}>
                <div className="rank-head">
                  <span className="rank-no">{r.rank}</span>
                  <div className="rank-title">
                    <strong>{marketName(r.market)}</strong>
                    <div className="badges">
                      {r.badges.map((b) => (
                        <span key={b} className={`chip badge-${b}`}>
                          {t(`badge_${b}` as 'badge_best')}
                        </span>
                      ))}
                      {r.flags.map((f) => (
                        <span key={f} className="chip chip-warn">
                          ⚠ {['arrival_flood', 'stale', 'price_spike', 'price_crash'].includes(f) ? t(`flag_${f}` as 'flag_stale') : f}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="rank-net">
                    <div className="big">{rupees(r.net_per_qtl)}</div>
                    <div className="muted small">{t('perQuintal')}</div>
                  </div>
                </div>
                <div className="breakdown">
                  {rupees(r.modal)} − {rupees(r.transport)} <span className="muted">({t('transport')})</span> − {rupees(r.commission)}{' '}
                  <span className="muted">({t('commission')})</span> − {rupees(r.handling)} <span className="muted">({t('handlingShort')})</span>
                </div>
                <div className="rank-foot">
                  <span>
                    <strong>{rupees(r.net_total)}</strong> {t('forLot')}
                  </span>
                  <span>
                    {t('distance')}: {fmtNum(r.distance_km)} {t('km')}
                  </span>
                  {r.forecast && (
                    <span>
                      {t('range7')}: {rangeText(lang, r.forecast.lo, r.forecast.hi)} <ConfidenceChip level={r.forecast.confidence} short />
                    </span>
                  )}
                  <span className="muted small">
                    {t('dataDate')}: <FmtDate iso={r.date} />
                  </span>
                </div>
              </li>
            ))}
          </ol>
          <p className="muted small">
            {t('estimateNote')} · {t('source')}: {sourceLabel(result.source)} · {t('dataDate')}: <FmtDate iso={result.data_as_of} />
          </p>

          {showAlert && rows.length > 0 && (
            <div className="alert-maker">
              <strong>{t('alertMeAt')}</strong>
              <div className="row-inline">
                <select value={alertMarket} onChange={(e) => setAlertMarket(e.target.value)} aria-label={t('market')}>
                  {result.rows.map((r) => (
                    <option key={r.market} value={r.market}>
                      {marketName(r.market)}
                    </option>
                  ))}
                </select>
                <input
                  type="number"
                  inputMode="numeric"
                  placeholder="₹"
                  aria-label={t('target')}
                  value={alertPrice}
                  onChange={(e) => setAlertPrice(e.target.value)}
                />
                <button
                  className="btn btn-secondary"
                  disabled={!(Number(alertPrice) > 0) || !alertMarket}
                  onClick={() => {
                    const cur = result.rows.find((r) => r.market === alertMarket)?.modal ?? 0
                    const target = Number(alertPrice)
                    addAlert({ crop, market: alertMarket, target, direction: target >= cur ? 'above' : 'below' })
                    setAlertMsg(t('alertSaved'))
                    setAlertPrice('')
                  }}
                >
                  🔔 {t('setAlert')}
                </button>
              </div>
              {alertMsg && <small className="ok">{alertMsg}</small>}
            </div>
          )}

          {showMap && meta && (
            <MarketMap
              origin={result.origin}
              markets={result.rows
                .map((r) => ({ market: meta.markets.find((m) => m.id === r.market)!, rank: r.rank, net: r.net_per_qtl, best: r.badges.includes('best') }))
                .filter((m) => m.market)}
            />
          )}
        </>
      )}
    </div>
  )
}
