import { useApp } from '../state'
import { Card } from '../components/common'
import { CompareMarkets } from '../components/CompareMarkets'

export function MarketsPage() {
  const { t } = useApp()
  return (
    <div className="page">
      <h1 className="page-title">{t('whereToSell')}</h1>
      <Card>
        <CompareMarkets unit="qtl" showMap showAlert storageKey="mm_compare" />
      </Card>
      <p className="guide-note">{t('guideNote')} {t('decisionYours')}</p>
    </div>
  )
}
