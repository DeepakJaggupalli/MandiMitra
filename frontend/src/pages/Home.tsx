import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type OverviewRow } from '../api'
import { useApp, useAsync } from '../state'
import { fmtDate, rupees } from '../i18n'
import { Async } from '../components/common'
import { SpeakButton, spokenSummary } from '../components/Speak'
import { favKey, useFavs } from '../favs'

export const CROP_ICON: Record<string, string> = { tomato: '🍅', onion: '🧅', banana: '🍌' }

export function DirectionPill({ direction, point }: { direction: OverviewRow['direction']; point?: number | null }) {
  const { t } = useApp()
  if (!direction) return <span className="dir dir-none">{t('noForecastShort')}</span>
  const arrow = direction === 'up' ? '▲' : direction === 'down' ? '▼' : '▬'
  const label = direction === 'up' ? t('likelyUp') : direction === 'down' ? t('likelyDown') : t('likelyFlat')
  return (
    <span className={`dir dir-${direction}`}>
      <span aria-hidden="true">{arrow}</span> {label}
      {point != null && <span className="dir-pt"> · {rupees(point)}</span>}
    </span>
  )
}

function Tile({ r }: { r: OverviewRow }) {
  const { t, crop, market, cropName, marketName } = useApp()
  const { isFav, toggle } = useFavs()
  const key = favKey(r.crop, r.market)
  const c = crop(r.crop)
  const m = market(r.market)
  const say = spokenSummary(c?.te ?? r.crop, c?.en ?? r.crop, m?.te ?? r.market, m?.en ?? r.market, r.modal, r.direction, r.point_mean)
  const fav = isFav(key)
  return (
    <Link to={`/price/${r.crop}/${r.market}`} className="tile">
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
      <div className="tile-next">
        <span className="muted">{t('next7')}:</span> <DirectionPill direction={r.direction} point={r.point_mean} />
      </div>
    </Link>
  )
}

export function HomePage() {
  const { t, lang, meta, cropName } = useApp()
  const { favs } = useFavs()
  const [filter, setFilter] = useState<string>('all')
  const ov = useAsync(() => api.overview(), [])
  const order = (meta?.crops ?? []).map((c) => c.id)

  return (
    <div className="page">
      <Async state={ov} what={t('homeTitle')}>
        {(d) => {
          const rows = [...d.rows].sort(
            (a, b) => order.indexOf(a.crop) - order.indexOf(b.crop) || a.market.localeCompare(b.market),
          )
          const favRows = favs.map((k) => rows.find((r) => favKey(r.crop, r.market) === k)).filter(Boolean) as OverviewRow[]
          const shown = filter === 'all' ? rows : rows.filter((r) => r.crop === filter)
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
                      <Tile key={`f-${r.crop}-${r.market}`} r={r} />
                    ))}
                  </div>
                </section>
              ) : (
                <p className="hint">{t('favHint')}</p>
              )}

              <section>
                <h2 className="sec-title">{t('allPrices')}</h2>
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
                <div className="tiles">
                  {shown.map((r) => (
                    <Tile key={`${r.crop}-${r.market}`} r={r} />
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
