import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type OverviewRow } from '../api'
import { useApp, useAsync } from '../state'
import { fmtDate, rupees } from '../i18n'
import type { Lang } from '../api'
import { Async } from '../components/common'
import { MarketDetail } from '../components/MarketDetail'
import { SpeakButton, spokenSummary } from '../components/Speak'
import { favKey, useFavs } from '../favs'
import { useIsDesktop } from '../useMedia'

export const CROP_ICON: Record<string, string> = { tomato: '🍅', onion: '🧅', banana: '🍌' }

export function DirectionPill({ direction, point }: { direction: OverviewRow['direction']; point?: number | null }) {
  const { t } = useApp()
  if (!direction) return <span className="dir dir-none">{t('noForecastShort')}</span>
  const arrow = direction === 'up' ? '▲' : direction === 'down' ? '▼' : direction === 'unclear' ? '?' : '▬'
  const label =
    direction === 'up' ? t('likelyUp') : direction === 'down' ? t('likelyDown') : direction === 'unclear' ? t('likelyUnclear') : t('likelyFlat')
  const shownPoint = direction === 'unclear' ? null : point
  return (
    <span className={`dir dir-${direction}`}>
      <span aria-hidden="true">{arrow}</span> {label}
      {shownPoint != null && <span className="dir-pt"> · {rupees(shownPoint)}</span>}
    </span>
  )
}

function Tile({ r, asOf, lang, onSelect, active }: {
  r: OverviewRow
  asOf: string
  lang: Lang
  onSelect?: () => void
  active?: boolean
}) {
  const { t, crop, market, cropName, marketName } = useApp()
  const old = r.date !== asOf
  const { isFav, toggle } = useFavs()
  const key = favKey(r.crop, r.market)
  const c = crop(r.crop)
  const m = market(r.market)
  const say = spokenSummary(c?.te ?? r.crop, c?.en ?? r.crop, m?.te ?? r.market, m?.en ?? r.market, r.modal, r.direction, r.point_mean,
    old ? fmtDate(r.date, 'te', false) : null, old ? fmtDate(r.date, 'en', false) : null)
  const fav = isFav(key)
  const body = (
    <>
      <div className="tile-top">
        <span className="tile-name">
          <span aria-hidden="true">{CROP_ICON[r.crop] ?? '🌾'}</span> {cropName(r.crop)}
          <small>{marketName(r.market)}</small>
        </span>
        <span className="tile-actions">
          <button
            type="button"
            className={`icon-btn ${fav ? 'fav-on' : ''}`}
            aria-pressed={fav}
            aria-label={fav ? t('removeFav') : t('addFav')}
            title={fav ? t('removeFav') : t('addFav')}
            onClick={(e) => {
              e.preventDefault()
              e.stopPropagation()
              toggle(key)
            }}
          >
            {fav ? '★' : '☆'}
          </button>
          <SpeakButton id={`tile-${key}`} te={say.te} en={say.en} />
        </span>
      </div>
      <div className="tile-price">
        {rupees(r.modal)} <small>{t('perQuintal')}</small>
      </div>
      {old && (
        <div className="tile-date">
          {t('priceOn', { date: fmtDate(r.date, lang, false) })}{' '}
          {r.frozen_since ? <span className="chip chip-warn">{t('frozenChip')}</span> : r.stale ? <span className="chip chip-warn">{t('oldPrice')}</span> : null}
        </div>
      )}
      <div className="tile-next">
        <span className="muted">{t('next7')}:</span> <DirectionPill direction={r.direction} point={r.point_mean} />
      </div>
    </>
  )
  if (onSelect) {
    return (
      <div
        role="button"
        tabIndex={0}
        aria-pressed={active}
        className={`tile ${active ? 'tile-active' : ''}`}
        onClick={onSelect}
        onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && onSelect()}
      >
        {body}
      </div>
    )
  }
  return (
    <Link to={`/price/${r.crop}/${r.market}`} className="tile">
      {body}
    </Link>
  )
}

export function HomePage() {
  const { t, lang, meta, cropName, selection, setSelection, marketName } = useApp()
  const { favs, isFav, toggle } = useFavs()
  const [filter, setFilter] = useState<string>('all')
  const desktop = useIsDesktop()
  const ov = useAsync(() => api.overview(), [])
  const order = (meta?.crops ?? []).map((c) => c.id)

  return (
    <div className={desktop ? 'page page-wide' : 'page'}>
      <Async state={ov} what={t('homeTitle')}>
        {(d) => {
          const rows = [...d.rows].sort(
            (a, b) => order.indexOf(a.crop) - order.indexOf(b.crop) || a.market.localeCompare(b.market),
          )
          const favRows = favs.map((k) => rows.find((r) => favKey(r.crop, r.market) === k)).filter(Boolean) as OverviewRow[]
          const shown = filter === 'all' ? rows : rows.filter((r) => r.crop === filter)
          const chips = (
            <div className="chips-row" role="tablist">
              {['all', ...order].map((id) => (
                <button
                  key={id}
                  role="tab"
                  aria-selected={filter === id}
                  className={`chip-btn ${filter === id ? 'active' : ''}`}
                  onClick={() => setFilter(id)}
                >
                  {id === 'all' ? t('allChip') : `${CROP_ICON[id] ?? ''} ${cropName(id)}`}
                </button>
              ))}
            </div>
          )
          if (desktop) {
            const sel = rows.find((r) => r.crop === selection.crop && r.market === selection.market) ?? favRows[0] ?? rows[0]
            const pick = (r: OverviewRow) => setSelection({ crop: r.crop, market: r.market })
            const selKey = sel ? favKey(sel.crop, sel.market) : ''
            return (
              <div className="desk-home">
                <aside className="desk-list">
                  <div className="home-head">
                    <h1 className="page-title">{t('homeTitle')}</h1>
                    <span className="muted small">{fmtDate(d.data_as_of, lang)}</span>
                  </div>
                  {favRows.length > 0 && (
                    <section>
                      <h2 className="sec-title">★ {t('favourites')}</h2>
                      <div className="tiles tiles-side">
                        {favRows.map((r) => (
                          <Tile key={`f-${r.crop}-${r.market}`} r={r} asOf={d.data_as_of} lang={lang} onSelect={() => pick(r)}
                            active={sel === r} />
                        ))}
                      </div>
                    </section>
                  )}
                  <section>
                    <h2 className="sec-title">{t('allPrices')}</h2>
                    {chips}
                    <div className="tiles tiles-side">
                      {shown.map((r) => (
                        <Tile key={`${r.crop}-${r.market}`} r={r} asOf={d.data_as_of} lang={lang} onSelect={() => pick(r)}
                          active={sel === r} />
                      ))}
                    </div>
                  </section>
                </aside>
                <section className="desk-main">
                  {sel && (
                    <>
                      <div className="detail-head">
                        <h2 className="page-title">
                          <span aria-hidden="true">{CROP_ICON[sel.crop] ?? '🌾'}</span> {cropName(sel.crop)}, {marketName(sel.market)}
                        </h2>
                        <button type="button" className={`btn btn-secondary ${isFav(selKey) ? 'fav-on' : ''}`} onClick={() => toggle(selKey)}
                          aria-pressed={isFav(selKey)}>
                          {isFav(selKey) ? '★' : '☆'} {isFav(selKey) ? t('removeFav') : t('addFav')}
                        </button>
                      </div>
                      <MarketDetail crop={sel.crop} market={sel.market} desktop
                        onPickMarket={(mk) => setSelection({ crop: sel.crop, market: mk })} />
                    </>
                  )}
                </section>
              </div>
            )
          }
          return (
            <>
              <div className="home-head">
                <h1 className="page-title">{t('homeTitle')}</h1>
                <span className="muted small">{fmtDate(d.data_as_of, lang)}</span>
              </div>

              {favRows.length > 0 ? (
                <section>
                  <h2 className="sec-title">★ {t('favourites')}</h2>
                  <div className="tiles">
                    {favRows.map((r) => (
                      <Tile key={`f-${r.crop}-${r.market}`} r={r} asOf={d.data_as_of} lang={lang} />
                    ))}
                  </div>
                </section>
              ) : (
                <p className="hint">{t('favHint')}</p>
              )}

              <section>
                <h2 className="sec-title">{t('allPrices')}</h2>
                {chips}
                <div className="tiles">
                  {shown.map((r) => (
                    <Tile key={`${r.crop}-${r.market}`} r={r} asOf={d.data_as_of} lang={lang} />
                  ))}
                </div>
              </section>
              <p className="guide-note">{t('guideNote')}</p>
            </>
          )
        }}
      </Async>
    </div>
  )
}
