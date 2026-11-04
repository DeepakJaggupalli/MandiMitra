import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, rowsOf, type AuditRow, type PipelineResponse } from '../api'
import { useApp, useAsync } from '../state'
import { fmtDateTime, fmtNum, rupees } from '../i18n'
import { Async, Card, ErrorBox, FmtDate, PassChip } from '../components/common'

function detailText(d: unknown): string {
  if (d === null || d === undefined) return ''
  if (typeof d === 'string') return d
  try {
    return JSON.stringify(d)
  } catch {
    return String(d)
  }
}

function Quality() {
  const { t, lang, cropName, marketName, sourceLabel } = useApp()
  const q = useAsync(() => api.quality(), [])
  const [err, setErr] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)
  const review = async (id: string, decision: 'accept' | 'exclude') => {
    setErr(null)
    setBusyId(id)
    try {
      await api.reviewQuality(id, decision)
      q.reload()
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setBusyId(null)
    }
  }
  return (
    <Card title={t('qualityReport')}>
      <Async state={q}>
        {(r) => (
          <>
            <p className="muted small">
              {t('updated')}: {fmtDateTime(r.generated_at, lang)} · {t('source')}: {typeof r.source === 'string' ? r.source : sourceLabel(r.source)}
            </p>
            <div className="stat-row">
              <div className="stat">
                <div className="stat-v">{fmtNum(r.rows_raw)}</div>
                <div className="stat-l">{t('rowsRaw')}</div>
              </div>
              <div className="stat">
                <div className="stat-v">{fmtNum(r.rows_clean)}</div>
                <div className="stat-l">{t('rowsClean')}</div>
              </div>
              <div className="stat">
                <div className="stat-v">{fmtNum(r.duplicates_removed)}</div>
                <div className="stat-l">{t('duplicates')}</div>
              </div>
              <div className="stat">
                <div className="stat-v">{fmtNum(r.name_fixes)}</div>
                <div className="stat-l">{t('nameFixes')}</div>
              </div>
              <div className="stat">
                <div className="stat-v">{fmtNum(r.unit_fixes)}</div>
                <div className="stat-l">{t('unitFixes')}</div>
              </div>
              {r.unmatched_rows !== undefined && (
                <div className="stat">
                  <div className="stat-v">{fmtNum(r.unmatched_rows)}</div>
                  <div className="stat-l">{t('unmatched')}</div>
                </div>
              )}
            </div>

            <h3>{t('checks')}</h3>
            <ul className="checks">
              {r.checks.map((c, i) => (
                <li key={i}>
                  <PassChip passed={c.passed} /> <strong>{c.name}</strong> <span className="muted small">{c.detail}</span>
                </li>
              ))}
            </ul>

            <h3>{t('series')}</h3>
            <div className="table-scroll">
              <table className="table compact">
                <thead>
                  <tr>
                    <th>{t('crop')}</th>
                    <th>{t('market')}</th>
                    <th>{t('firstDate')}</th>
                    <th>{t('lastDate')}</th>
                    <th>{t('daysReported')}</th>
                    <th>{t('missing')}</th>
                    <th>{t('flagged')}</th>
                    <th>{t('stale')}</th>
                  </tr>
                </thead>
                <tbody>
                  {r.series.map((s) => (
                    <tr key={`${s.crop}-${s.market}`}>
                      <td>{cropName(s.crop)}</td>
                      <td>{marketName(s.market)}</td>
                      <td>
                        <FmtDate iso={s.first_date} />
                      </td>
                      <td>
                        <FmtDate iso={s.last_date} />
                      </td>
                      <td>{fmtNum(s.days_reported)}</td>
                      <td>
                        {fmtNum(s.missing_days)} ({fmtNum(s.missing_pct, 1)}%)
                      </td>
                      <td>{s.flagged}</td>
                      <td>{s.stale ? <span className="chip chip-warn">{t('yes')}</span> : t('no')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <h3>{t('flaggedRecords')}</h3>
            {err && <ErrorBox error={err} />}
            {r.flagged.length === 0 ? (
              <p className="empty">{t('noFlagged')}</p>
            ) : (
              <div className="table-scroll">
                <table className="table compact">
                  <thead>
                    <tr>
                      <th>{t('crop')}</th>
                      <th>{t('market')}</th>
                      <th>{t('date')}</th>
                      <th>{t('rule')}</th>
                      <th>{t('detail')}</th>
                      <th>
                        {t('min')}/{t('modal')}/{t('max')}
                      </th>
                      <th>{t('review')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {r.flagged.map((f) => (
                      <tr key={f.id}>
                        <td>{cropName(f.crop)}</td>
                        <td>{marketName(f.market)}</td>
                        <td>
                          <FmtDate iso={f.date} />
                        </td>
                        <td>{f.rule}</td>
                        <td className="small">{f.detail}</td>
                        <td className="nowrap">
                          {rupees(f.min)} / {rupees(f.modal)} / {rupees(f.max)}
                        </td>
                        <td className="nowrap">
                          {f.review ? (
                            <span className={`chip ${f.review.decision === 'accept' ? 'chip-pass' : 'chip-fail'}`}>
                              {f.review.decision === 'accept' ? t('accept') : t('exclude')} · {f.review.by}
                            </span>
                          ) : (
                            <>
                              <button className="btn btn-small btn-primary" disabled={busyId === f.id} onClick={() => review(f.id, 'accept')}>
                                {t('accept')}
                              </button>{' '}
                              <button className="btn btn-small btn-secondary" disabled={busyId === f.id} onClick={() => review(f.id, 'exclude')}>
                                {t('exclude')}
                              </button>
                            </>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </Async>
    </Card>
  )
}

function Audit() {
  const { t, lang } = useApp()
  const a = useAsync(() => api.audit(100), [])
  return (
    <Card title={t('auditLog')} actions={<button className="btn btn-small" onClick={a.reload}>↻</button>}>
      <Async state={a}>
        {(d) => {
          const rows = rowsOf<AuditRow>(d)
          return rows.length === 0 ? (
            <p className="muted">{t('noData')}</p>
          ) : (
            <div className="table-scroll">
              <table className="table compact">
                <thead>
                  <tr>
                    <th>{t('time')}</th>
                    <th>{t('agent')}</th>
                    <th>{t('action')}</th>
                    <th>{t('detail')}</th>
                    <th>{t('actor')}</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={r.id ?? i}>
                      <td className="nowrap">{fmtDateTime(r.ts, lang)}</td>
                      <td>{r.agent}</td>
                      <td>{r.action}</td>
                      <td className="small detail-cell">{detailText(r.detail)}</td>
                      <td>{r.actor ?? ''}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        }}
      </Async>
    </Card>
  )
}

function PipelineLog() {
  const { t, lang, sourceLabel } = useApp()
  const p = useAsync<PipelineResponse>(() => api.pipeline(), [])
  return (
    <Card title={t('pipelineLog')} actions={<button className="btn btn-small" onClick={p.reload}>↻</button>}>
      <Async state={p}>
        {(d) => {
          const rows = rowsOf<PipelineResponse['rows'][number]>(d.rows)
          const history = rowsOf<PipelineResponse['history'][number]>(d.history)
          return (
            <>
              <p className="muted small">
                {t('updated')}: {fmtDateTime(d.generated_at, lang)} · {t('dataDate')}: <FmtDate iso={d.data_as_of} /> · {t('source')}:{' '}
                {sourceLabel(d.source)}
              </p>
              {rows.length === 0 ? (
                <p className="empty">{t('noData')}</p>
              ) : (
                <div className="table-scroll">
                  <table className="table compact">
                    <thead>
                      <tr>
                        <th>{t('time')}</th>
                        <th>{t('agent')}</th>
                        <th>{t('action')}</th>
                        <th>{t('detail')}</th>
                        <th>{t('level')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((r, i) => (
                        <tr key={i} className={`level-${r.level}`}>
                          <td className="nowrap">{fmtDateTime(r.ts, lang)}</td>
                          <td>{r.agent}</td>
                          <td>{r.action}</td>
                          <td className="small detail-cell">{detailText(r.detail)}</td>
                          <td>{r.level}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              <h3>{t('runHistory')}</h3>
              {history.length === 0 ? (
                <p className="empty">{t('noData')}</p>
              ) : (
                <div className="table-scroll">
                  <table className="table compact">
                    <thead>
                      <tr>
                        <th>{t('date')}</th>
                        <th>{t('status')}</th>
                        <th>{t('source')}</th>
                        <th>{t('dataDate')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {history.map((h, i) => (
                        <tr key={i}>
                          <td>
                            <FmtDate iso={h.date} />
                          </td>
                          <td>
                            <span className={`chip ${h.status === 'ok' ? 'chip-pass' : 'chip-fail'}`}>{h.status}</span>
                          </td>
                          <td>{h.source}</td>
                          <td>
                            <FmtDate iso={h.data_as_of} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )
        }}
      </Async>
    </Card>
  )
}

export default function AdminPage() {
  const { t, user } = useApp()
  if (!user || user.role !== 'admin') {
    return (
      <div className="page">
        <h1 className="page-title">{t('adminTitle')}</h1>
        <div className="callout">
          {t('adminOnly')} <Link to="/login">{t('navLogin')}</Link>
        </div>
      </div>
    )
  }
  return (
    <div className="page">
      <h1 className="page-title">{t('adminTitle')}</h1>
      <Quality />
      <PipelineLog />
      <Audit />
    </div>
  )
}
