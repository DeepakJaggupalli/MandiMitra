import { useEffect, useState } from 'react'
import { api, type AlertCheckResult } from '../api'
import { useApp, useAsync } from '../state'
import { rupees } from '../i18n'
import { Async, Card, CropMarketPicker, ErrorBox, FmtDate } from '../components/common'

export function AlertsPage() {
  const { t, lang, alerts, setAlerts, addAlert, cropName, marketName, selection, bi } = useApp()
  const [crop, setCrop] = useState(selection.crop)
  const [market, setMarket] = useState(selection.market)
  const [target, setTarget] = useState('')
  const [direction, setDirection] = useState<'above' | 'below'>('above')
  const [checks, setChecks] = useState<Record<string, AlertCheckResult>>({})
  const [checkErr, setCheckErr] = useState<string | null>(null)
  const [perm, setPerm] = useState<string>(typeof Notification !== 'undefined' ? Notification.permission : 'unsupported')
  const feed = useAsync(() => api.feed(), [])

  const alertKey = alerts.map((a) => `${a.id}:${a.target}:${a.direction}`).join('|')
  useEffect(() => {
    if (alerts.length === 0) {
      setChecks({})
      return
    }
    setCheckErr(null)
    api
      .checkAlerts(alerts)
      .then((r) => {
        const map: Record<string, AlertCheckResult> = {}
        for (const x of r.results) map[x.id] = x
        setChecks(map)
      })
      .catch((e: Error) => setCheckErr(e.message))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [alertKey])

  const sorted = [...alerts].sort((a, b) => Number(!!checks[b.id]?.triggered) - Number(!!checks[a.id]?.triggered))

  return (
    <div className="page">
      <h1 className="page-title">{t('navAlerts')}</h1>

      <Card title={t('myAlerts')}>
        {checkErr && <ErrorBox error={checkErr} />}
        {alerts.length === 0 ? (
          <p className="muted">{t('noAlerts')}</p>
        ) : (
          <ul className="alert-list">
            {sorted.map((a) => {
              const c = checks[a.id]
              return (
                <li key={a.id} className={c?.triggered ? 'is-triggered' : ''}>
                  <div>
                    <strong>
                      {cropName(a.crop)} · {marketName(a.market)}
                    </strong>
                    <div className="small">
                      {t('direction')} {a.direction === 'above' ? t('above') : t('below')} <strong>{rupees(a.target)}</strong>
                    </div>
                    {c && (
                      <div className="small muted">
                        {t('current')}: {rupees(c.current)} {c.date && <>(<FmtDate iso={c.date} />)</>}
                      </div>
                    )}
                  </div>
                  <div className="alert-side">
                    {c ? (
                      <span className={`chip ${c.triggered ? 'chip-pass' : ''}`}>{c.triggered ? `🔔 ${t('triggered')}` : t('notYet')}</span>
                    ) : null}
                    <button className="btn btn-small" onClick={() => setAlerts(alerts.filter((x) => x.id !== a.id))}>
                      {t('delete')}
                    </button>
                  </div>
                </li>
              )
            })}
          </ul>
        )}

        <h3>{t('newAlert')}</h3>
        <CropMarketPicker
          crop={crop}
          market={market}
          onChange={(c, m) => {
            setCrop(c)
            setMarket(m)
          }}
        />
        <div className="form-grid">
          <label className="field">
            <span>{t('direction')}</span>
            <select value={direction} onChange={(e) => setDirection(e.target.value as 'above' | 'below')}>
              <option value="above">{t('above')}</option>
              <option value="below">{t('below')}</option>
            </select>
          </label>
          <label className="field">
            <span>{t('target')}</span>
            <input type="number" inputMode="numeric" min={1} value={target} onChange={(e) => setTarget(e.target.value)} />
          </label>
        </div>
        <button
          className="btn btn-primary"
          disabled={!(Number(target) > 0)}
          onClick={() => {
            addAlert({ crop, market, target: Number(target), direction })
            setTarget('')
            setTimeout(() => setPerm(typeof Notification !== 'undefined' ? Notification.permission : 'unsupported'), 1500)
          }}
        >
          {t('add')}
        </button>
        {perm === 'default' && alerts.length > 0 && (
          <button
            className="btn btn-link"
            onClick={() =>
              Notification.requestPermission()
                .then((p) => setPerm(p))
                .catch(() => undefined)
            }
          >
            {t('enableNotifications')}
          </button>
        )}
        <p className="muted small">🔒 {t('privacyNote')}</p>
      </Card>

      <Card title={t('bigMoves')}>
        <Async state={feed}>
          {(f) =>
            f.warnings.length === 0 ? (
              <p className="empty">{t('noWarnings')}</p>
            ) : (
              <ul className="feed">
                {f.warnings.map((w) => (
                  <li key={w.id} className="callout callout-warn">
                    <div className="small muted">
                      {cropName(w.crop)} · {marketName(w.market)} · <FmtDate iso={w.date} /> · {t(`type_${w.type}` as 'type_price_spike')}
                    </div>
                    <div>{bi(w)}</div>
                  </li>
                ))}
              </ul>
            )
          }
        </Async>
      </Card>

      <Card title={t('bulletins')}>
        <Async state={feed}>
          {(f) =>
            f.bulletins.length === 0 ? (
              <p className="empty">{t('noBulletins')}</p>
            ) : (
              <div className="feed">
                {f.bulletins.map((b) => (
                  <article key={b.id} className="bulletin">
                    <h3>{lang === 'te' ? b.title_te || b.title_en : b.title_en}</h3>
                    <div className="small muted">
                      {t('weekOf')}: <FmtDate iso={b.week_start} />
                    </div>
                    <div className="pre">{lang === 'te' ? b.body_te || b.body_en : b.body_en}</div>
                  </article>
                ))}
              </div>
            )
          }
        </Async>
      </Card>
    </div>
  )
}
