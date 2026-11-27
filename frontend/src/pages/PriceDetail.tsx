import { useEffect } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useApp } from '../state'
import { MarketDetail } from '../components/MarketDetail'
import { favKey, useFavs } from '../favs'
import { useIsDesktop } from '../useMedia'
import { CROP_ICON } from './Home'

export function PriceDetailPage() {
  const { crop = '', market = '' } = useParams()
  const { t, crop: cropInfo, cropName, marketName, setSelection } = useApp()
  const { isFav, toggle } = useFavs()
  const desktop = useIsDesktop()
  const navigate = useNavigate()
  const valid = !!cropInfo(crop)?.markets.includes(market)

  useEffect(() => {
    if (valid) setSelection({ crop, market })
  }, [valid, crop, market, setSelection])

  if (!valid) {
    return (
      <div className="page">
        <Link to="/" className="back-link">← {t('backAll')}</Link>
        <p>404</p>
      </div>
    )
  }

  const key = favKey(crop, market)
  const fav = isFav(key)

  return (
    <div className="page page-wide">
      <div className="detail-head">
        <Link to="/" className="back-link">← {t('backAll')}</Link>
        <button type="button" className={`btn btn-secondary ${fav ? 'fav-on' : ''}`} onClick={() => toggle(key)} aria-pressed={fav}>
          {fav ? '★' : '☆'} {fav ? t('removeFav') : t('addFav')}
        </button>
      </div>
      <h1 className="page-title">
        <span aria-hidden="true">{CROP_ICON[crop] ?? '🌾'}</span> {cropName(crop)}, {marketName(market)}
      </h1>
      <MarketDetail crop={crop} market={market} desktop={desktop} onPickMarket={(m) => navigate(`/price/${crop}/${m}`)} />
    </div>
  )
}
