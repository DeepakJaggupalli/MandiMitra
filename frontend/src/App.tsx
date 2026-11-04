import { lazy, Suspense, useEffect, useRef } from 'react'
import { Route, Routes, Link } from 'react-router-dom'
import { Layout } from './components/Layout'
import { ErrorBox, Loading } from './components/common'
import { useApp } from './state'
import { api } from './api'
import { PricesPage } from './pages/Prices'
import { MarketsPage } from './pages/Markets'
import { AskPage } from './pages/Ask'
import { AlertsPage } from './pages/Alerts'
import { LoginPage } from './pages/Login'
import { loadJSON, saveJSON } from './state'

const DashboardPage = lazy(() => import('./pages/Dashboard'))
const AdminPage = lazy(() => import('./pages/Admin'))

/** On app start, check the farmer's saved price alerts and notify newly triggered ones. */
function AlertWatcher() {
  const { alerts, t, cropName, marketName } = useApp()
  const done = useRef(false)
  useEffect(() => {
    if (done.current || alerts.length === 0) return
    done.current = true
    api
      .checkAlerts(alerts)
      .then((r) => {
        const seen = loadJSON<Record<string, string>>('mm_alert_seen', {})
        for (const res of r.results) {
          if (!res.triggered || !res.date) continue
          if (seen[res.id] === res.date) continue
          seen[res.id] = res.date
          const a = alerts.find((x) => x.id === res.id)
          if (a && typeof Notification !== 'undefined' && Notification.permission === 'granted') {
            try {
              new Notification('MandiMitra', {
                body: t('alertReachedMsg', {
                  crop: cropName(a.crop),
                  market: marketName(a.market),
                  price: Math.round(res.current ?? 0).toLocaleString('en-IN'),
                  target: a.target.toLocaleString('en-IN'),
                }),
                icon: '/icon-192.png',
              })
            } catch {
              /* some mobile browsers only allow notifications from the service worker */
            }
          }
        }
        saveJSON('mm_alert_seen', seen)
      })
      .catch(() => undefined)
  }, [alerts, t, cropName, marketName])
  return null
}

export function App() {
  const { meta, metaError, reloadMeta, t } = useApp()
  return (
    <Layout>
      <AlertWatcher />
      {metaError && !meta ? (
        <ErrorBox error={metaError} onRetry={reloadMeta} what="meta" />
      ) : !meta ? (
        <Loading />
      ) : (
        <Suspense fallback={<Loading />}>
          <Routes>
            <Route path="/" element={<PricesPage />} />
            <Route path="/markets" element={<MarketsPage />} />
            <Route path="/ask" element={<AskPage />} />
            <Route path="/alerts" element={<AlertsPage />} />
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/admin" element={<AdminPage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route
              path="*"
              element={
                <div className="card">
                  <p>404</p>
                  <Link to="/">{t('navPrices')}</Link>
                </div>
              }
            />
          </Routes>
        </Suspense>
      )}
    </Layout>
  )
}
