import { Link, useParams, useSearchParams } from 'react-router-dom'
import { useApp } from '../state'
import { ExtraCropDetail } from '../components/ExtraCrops'

/** /crop/:id — every market for one optional crop (prices only). */
export function ExtraCropPage() {
  const { id = '' } = useParams()
  const [sp, setSp] = useSearchParams()
  const { t } = useApp()
  return (
    <div className="page page-wide">
      <Link to="/" className="back-link">
        ← {t('backAll')}
      </Link>
      <ExtraCropDetail id={id} market={sp.get('market')} onPickMarket={(m) => setSp({ market: m }, { replace: true })} />
    </div>
  )
}
