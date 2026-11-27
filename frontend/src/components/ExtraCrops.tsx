import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type ExtraCropSummary, type ExtraGroup, type ExtraMarket } from '../api'
import { useApp, useAsync } from '../state'
import { fmtDate, rupees } from '../i18n'
import { Async, SourceLine } from './common'
import { PriceChart } from './PriceChart'
import { SpeakButton } from './Speak'
import { useExtraCrops } from '../extraCrops'

const GROUPS: ExtraGroup[] = ['veg', 'fruit', 'spice', 'field']
const GROUP_ICON: Record<ExtraGroup, string> = { veg: '🥬', fruit: '🥭', spice: '🌶️', field: '🌾' }

/** Searchable list of optional crops, grouped; a crop with no recent AP price cannot be picked. */
export function ExtraCropPicker({ onClose }: { onClose: () => void }) {
  const { t, lang } = useApp()
  const { has, toggle } = useExtraCrops()
  const [q, setQ] = useState('')
  const [showOff, setShowOff] = useState(false)
  const list = useAsync(() => api.extraList(), [])
  return (
    <section className="card picker-panel" aria-label={t('chooseCrops')}>
      <div className="card-head">
        <h2>{t('chooseCrops')}</h2>
        <button type="button" className="btn btn-primary btn-small" onClick={onClose}>
          {t('doneBtn')}
        </button>
      </div>
      <p className="muted small">{t('otherCropsNote')}</p>
      <input className="search" type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t('searchCrop')} aria-label={t('searchCrop')} />
      <Async state={list}>
        {(d) => {
          const needle = q.trim().toLowerCase()
          const match = (c: ExtraCropSummary) => !needle || c.en.toLowerCase().includes(needle) || c.te.includes(q.trim())
          // crops with no recent AP price are folded away (still findable by search or the link below)
          const visible = (c: ExtraCropSummary) => match(c) && (c.n_markets > 0 || showOff || has(c.id) || !!needle)
          const hiddenCount = d.crops.filter((c) => match(c) && !visible(c)).length
          return (
            <>
              {GROUPS.map((g) => {
                const crops = d.crops.filter((c) => c.group === g && visible(c)).sort((a, b) => b.n_markets - a.n_markets)
                if (!crops.length) return null
                return (
                  <div key={g} className="pick-group">
                    <h3>
                      {GROUP_ICON[g]} {t(`grp_${g}` as 'grp_veg')}
                    </h3>
                    <ul>
                      {crops.map((c) => {
                        const off = c.n_markets === 0
                        return (
                          <li key={c.id}>
                            <label className={`pick-row ${off ? 'pick-off' : ''}`}>
                              <input type="checkbox" checked={has(c.id)} disabled={off && !has(c.id)} onChange={() => toggle(c.id)} />
                              <span className="pick-name">
                                {lang === 'te' ? c.te : c.en}
                                <small>{lang === 'te' ? c.en : c.te}</small>
                              </span>
                              <span className="muted small">
                                {off ? t('noRecentPrice') : c.n_markets === 1 ? t('nMarkets1') : t('nMarkets', { n: c.n_markets })}
                              </span>
                            </label>
                          </li>
                        )
                      })}
                    </ul>
                  </div>
                )
              })}
              {hiddenCount > 0 && (
                <button type="button" className="btn btn-link" onClick={() => setShowOff(true)}>
                  {t('showNoPrice', { n: hiddenCount })}
                </button>
              )}
            </>
          )
        }}
      </Async>
    </section>
  )
}

function marketLabel(m: ExtraMarket, lang: 'te' | 'en') {
  return lang === 'te' && m.te ? m.te : m.market
}

/** One followed optional crop on the home screen: its most recent markets as small price tiles. */
function ExtraCropTiles({ id, asOf, onSelect }: { id: string; asOf: string; onSelect?: (id: string, market: string) => void }) {
  const { t, lang } = useApp()
  const { toggle } = useExtraCrops()
  const crop = useAsync(() => api.extraCrop(id), [id])
  return (
    <Async state={crop}>
      {(c) => {
        const name = lang === 'te' ? c.te : c.en
        const top = c.markets.slice(0, 6)
        return (
          <div className="extra-crop">
            <div className="extra-head">
              <h3>
                {name} <span className="chip">{t('priceOnly')}</span>
              </h3>
              <button type="button" className="btn btn-link" onClick={() => toggle(id)}>
                {t('removeCrop')}
              </button>
            </div>
            {top.length === 0 ? (
              <p className="muted small">{t('noRecentPrice')}</p>
            ) : (
              <div className="tiles tiles-side">
                {top.map((m) => {
                  const old = m.date !== asOf
                  const at = lang === 'te' && m.te ? `${m.te}లో` : `${m.market} మార్కెట్‌లో`
                  const te = `${at} ${c.te} ధర ${old ? fmtDate(m.date, 'te', false) + 'న' : 'ఈ రోజు'} క్వింటాల్‌కు ${m.modal} రూపాయలు. ఈ పంటకు అంచనా లేదు.`
                  const en = `${c.en} at ${m.market}: ${old ? 'on ' + fmtDate(m.date, 'en', false) : 'today'} ${m.modal} rupees per quintal. No forecast for this crop.`
                  const inner = (
                    <>
                      <div className="tile-top">
                        <span className="tile-name">
                          {name}
                          <small>{marketLabel(m, lang)}</small>
                        </span>
                        <span className="tile-actions">
                          <SpeakButton id={`x-${id}-${m.market}`} te={te} en={en} />
                        </span>
                      </div>
                      <div className="tile-price">
                        {rupees(m.modal)} <small>{t('perQuintal')}</small>
                      </div>
                      <div className="tile-date">{old ? t('priceOn', { date: fmtDate(m.date, lang, false) }) : t('todayPrice')}</div>
                    </>
                  )
                  return onSelect ? (
                    <div key={m.market} role="button" tabIndex={0} className="tile tile-extra" onClick={() => onSelect(id, m.market)}
                      onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && onSelect(id, m.market)}>
                      {inner}
                    </div>
                  ) : (
                    <Link key={m.market} to={`/crop/${id}?market=${encodeURIComponent(m.market)}`} className="tile tile-extra">
                      {inner}
                    </Link>
                  )
                })}
              </div>
            )}
            {c.markets.length > top.length && (
              onSelect ? (
                <button type="button" className="btn btn-link" onClick={() => onSelect(id, c.markets[0].market)}>
                  {t('allNMarkets', { n: c.markets.length })} →
                </button>
              ) : (
                <Link to={`/crop/${id}`}>{t('allNMarkets', { n: c.markets.length })} →</Link>
              )
            )}
          </div>
        )
      }}
    </Async>
  )
}

/** "Other crops (your choice)" section for the home screen (phone and desktop). */
export function ExtraCropsSection({ asOf, onSelect }: { asOf: string; onSelect?: (id: string, market: string) => void }) {
  const { t } = useApp()
  const { ids } = useExtraCrops()
  const [open, setOpen] = useState(false)
  return (
    <section className="extra-section">
      <div className="extra-head">
        <h2 className="sec-title">{t('otherCrops')}</h2>
        <button type="button" className="btn btn-secondary btn-small" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
          {t('addCrop')}
        </button>
      </div>
      {open && <ExtraCropPicker onClose={() => setOpen(false)} />}
      {ids.length === 0 && !open && <p className="hint">{t('extraEmpty')}</p>}
      {ids.map((id) => (
        <ExtraCropTiles key={id} id={id} asOf={asOf} onSelect={onSelect} />
      ))}
    </section>
  )
}

/** Every market for one optional crop, with a 30-day chart for the chosen market. Prices only. */
export function ExtraCropDetail({ id, market, onPickMarket }: { id: string; market?: string | null; onPickMarket?: (m: string) => void }) {
  const { t, lang } = useApp()
  const [localSel, setLocalSel] = useState<string | null>(null)
  const crop = useAsync(() => api.extraCrop(id), [id])
  const sel = market ?? localSel
  const pick = (m: string) => (onPickMarket ? onPickMarket(m) : setLocalSel(m))
  return (
    <Async state={crop}>
      {(c) => <ExtraBody c={c} sel={sel} pick={pick} t={t} lang={lang} />}
    </Async>
  )
}

function ExtraBody({ c, sel, pick, t, lang }: {
  c: Awaited<ReturnType<typeof api.extraCrop>>
  sel: string | null
  pick: (m: string) => void
  t: ReturnType<typeof useApp>['t']
  lang: 'te' | 'en'
}) {
  const chosen = c.markets.find((m) => m.market === sel) ?? c.markets[0]
  const history = useMemo(
    () => (chosen ? chosen.history.map(([date, min, max, modal]) => ({ date, min, max, modal, arrivals_t: null })) : []),
    [chosen],
  )
  return (
    <div className="page">
      <h2 className="page-title">
        {lang === 'te' ? c.te : c.en} <span className="chip">{t('priceOnly')}</span>
      </h2>
      <p className="callout">{t('otherCropsNote')}</p>
      {chosen && (
        <section className="card">
          <div className="card-head">
            <h2>{marketLabel(chosen, lang)}</h2>
            <span className="price-big">
              {rupees(chosen.modal)} <span className="unit">{t('perQuintal')}</span>
            </span>
          </div>
          <div className="kv-row">
            <span>
              {t('min')} <strong>{rupees(chosen.min)}</strong>
            </span>
            <span>
              {t('max')} <strong>{rupees(chosen.max)}</strong>
            </span>
            {chosen.varieties.length > 0 && (
              <span className="muted small">
                {t('varietyLabel')}: {chosen.varieties.join(', ')}
              </span>
            )}
          </div>
          {chosen.varieties.length > 1 && <div className="muted small">{t('medianOfVarieties', { n: chosen.varieties.length })}</div>}
          <SourceLine date={chosen.date} source={c.source} />
          {history.length > 1 && <PriceChart history={history} lastYear={[]} forecast={null} showLastYear={false} />}
        </section>
      )}
      <section className="card">
        <div className="card-head">
          <h2>{t('allNMarkets', { n: c.markets.length })}</h2>
        </div>
        <p className="muted small">{t('pickMarketForChart')}</p>
        <div className="table-scroll">
          <table className="table clickable">
            <thead>
              <tr>
                <th>{t('market')}</th>
                <th>{t('districtLabel')}</th>
                <th>{t('modal')}</th>
                <th>
                  {t('min')} – {t('max')}
                </th>
                <th>{t('date')}</th>
              </tr>
            </thead>
            <tbody>
              {c.markets.map((m) => (
                <tr key={m.market} className={chosen && m.market === chosen.market ? 'row-active' : ''} onClick={() => pick(m.market)}
                  tabIndex={0} onKeyDown={(e) => e.key === 'Enter' && pick(m.market)}>
                  <td>{marketLabel(m, lang)}</td>
                  <td>{m.district}</td>
                  <td>
                    <strong>{rupees(m.modal)}</strong>
                  </td>
                  <td>
                    {rupees(m.min)} – {rupees(m.max)}
                  </td>
                  <td>{fmtDate(m.date, lang, false)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
