import { Fragment, useState } from 'react'
import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, rowsOf, type Bulletin, type FeedbackRow, type Warning } from '../api'
import { useApp, useAsync } from '../state'
import { fmtDateTime, fmtNum, pct, rangeText, rupees } from '../i18n'
import { Async, Card, ConfidenceChip, ErrorBox, FmtDate, PassChip, TrendChip } from '../components/common'
import { CompareMarkets } from '../components/CompareMarkets'

function Overview() {
  const { t, lang, meta, cropName, marketName, sourceLabel } = useApp()
  const [crop, setCrop] = useState<string>('all')
  const ov = useAsync(() => api.overview(), [])
  return (
    <Card
      title={t('overview')}
      actions={
        <select value={crop} onChange={(e) => setCrop(e.target.value)} aria-label={t('crop')}>
          <option value="all">{t('allCrops')}</option>
          {meta?.crops.map((c) => (
            <option key={c.id} value={c.id}>
              {c[lang]}
            </option>
          ))}
        </select>
      }
    >
      <Async state={ov}>
        {(d) => (
          <>
            <div className="table-scroll">
              <table className="table">
                <thead>
                  <tr>
                    <th>{t('crop')}</th>
                    <th>{t('market')}</th>
                    <th>{t('date')}</th>
                    <th>{t('modal')}</th>
                    <th>{t('change7d')}</th>
                    <th>{t('arrivals')}</th>
                    <th>{t('range7')}</th>
                    <th>{t('confidence')}</th>
                    <th>{t('anomaly')}</th>
                  </tr>
                </thead>
                <tbody>
                  {d.rows
                    .filter((r) => crop === 'all' || r.crop === crop)
                    .map((r) => (
                      <tr key={`${r.crop}-${r.market}`}>
                        <td>{cropName(r.crop)}</td>
                        <td>{marketName(r.market)}</td>
                        <td className="nowrap">
                          <FmtDate iso={r.date} withYear={false} />
                        </td>
                        <td>
                          <strong>{rupees(r.modal)}</strong>
                        </td>
                        <td>
                          <TrendChip trend={r.trend} change={r.change_7d_pct} />
                        </td>
                        <td>{r.arrivals_t != null ? `${fmtNum(r.arrivals_t, 1)} t` : '—'}</td>
                        <td className="nowrap">{r.lo != null && r.hi != null ? rangeText(lang, r.lo, r.hi) : '—'}</td>
                        <td>
                          <ConfidenceChip level={r.confidence} short />
                        </td>
                        <td>{r.anomaly_type ? <span className="chip chip-warn">⚠ {t(`type_${r.anomaly_type}` as 'type_price_spike')}</span> : ''}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
            <p className="source-line">
              {t('dataDate')}: <FmtDate iso={d.data_as_of} /> · {t('source')}: {sourceLabel(d.source)}
            </p>
          </>
        )}
      </Async>
    </Card>
  )
}

function AccuracyReport() {
  const { t, lang, cropName, marketName } = useApp()
  const acc = useAsync(() => api.accuracy(), [])
  return (
    <Card title={t('accuracyReport')}>
      <Async state={acc}>
        {(a) => {
          const label = (m: string) => (m === 'selected' ? t('selected') : a.model_labels?.[m] ?? m)
          const models = Object.keys(a.overall.mape)
          const bars = models.map((m) => ({ model: label(m), key: m, mape: a.overall.mape[m] }))
          const hModels = a.by_horizon.length ? Object.keys(a.by_horizon[0].mape) : []
          return (
            <>
              <p className="muted small">
                {t('testWindow')}: <FmtDate iso={a.test_window.start} /> – <FmtDate iso={a.test_window.end} /> ({a.test_window.days} d)
              </p>
              <h3>{t('successCriteria')}</h3>
              <div className="table-scroll">
                <table className="table">
                  <thead>
                    <tr>
                      <th>{t('criterion')}</th>
                      <th>Target</th>
                      <th>{t('value')}</th>
                      <th>{t('status')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {a.criteria.map((c) => (
                      <tr key={c.key}>
                        <td>{lang === 'te' ? c.name_te || c.name_en : c.name_en}</td>
                        <td>{c.target}</td>
                        <td>{c.value}</td>
                        <td>
                          <PassChip passed={c.passed} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="stat-row">
                <div className="stat">
                  <div className="stat-v">{pct(a.overall.improvement_pct, false)}</div>
                  <div className="stat-l">{t('improvement')}</div>
                </div>
                <div className="stat">
                  <div className="stat-v">{pct(a.overall.coverage * 100, false)}</div>
                  <div className="stat-l">{t('coverage')}</div>
                </div>
                <div className="stat">
                  <div className="stat-v">{pct(a.overall.direction_accuracy * 100, false)}</div>
                  <div className="stat-l">
                    {t('directionAcc')}
                    {a.overall.direction_n ? ` (${t('ofMoves', { n: fmtNum(a.overall.direction_n) })})` : ''}
                  </div>
                </div>
              </div>
              {a.selection_counts && Object.keys(a.selection_counts).length > 0 && (
                <p className="muted small">
                  {t('modelsChosen')}:{' '}
                  {Object.entries(a.selection_counts)
                    .map(([m, n]) => `${label(m)} × ${n}`)
                    .join(' · ')}
                </p>
              )}

              <h3>{t('overallMape')}</h3>
              <div className="chart-wrap">
                <ResponsiveContainer width="100%" height={Math.max(160, bars.length * 38)}>
                  <BarChart data={bars} layout="vertical" margin={{ top: 4, right: 40, bottom: 0, left: 4 }}>
                    <CartesianGrid stroke="#e3e8e2" horizontal={false} />
                    <XAxis type="number" tick={{ fontSize: 12 }} unit="%" />
                    <YAxis type="category" dataKey="model" width={130} tick={{ fontSize: 12 }} interval={0} />
                    <Tooltip formatter={(v: number) => [`${fmtNum(v, 1)}%`, 'MAPE']} />
                    <Bar dataKey="mape" isAnimationActive={false} label={{ position: 'right', fontSize: 12, formatter: (v: number) => fmtNum(v, 1) }}>
                      {bars.map((b) => (
                        <Cell key={b.key} fill={b.key === 'selected' ? '#1b6b3a' : b.key === a.overall.best_baseline ? '#b06d00' : '#9cb3a3'} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>

              <h3>{t('byHorizon')}</h3>
              <div className="table-scroll">
                <table className="table compact">
                  <thead>
                    <tr>
                      <th>{t('daysAhead')}</th>
                      {hModels.map((m) => (
                        <th key={m}>{label(m)}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {a.by_horizon.map((h) => (
                      <tr key={h.h}>
                        <td>{h.h}</td>
                        {hModels.map((m) => (
                          <td key={m}>{fmtNum(h.mape[m], 1)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <h3>{t('perSeries')}</h3>
              <div className="table-scroll">
                <table className="table compact">
                  <thead>
                    <tr>
                      <th>{t('crop')}</th>
                      <th>{t('market')}</th>
                      <th>{t('selected')}</th>
                      <th>MAPE</th>
                      <th>{t('usedToday')}</th>
                      <th>{t('improvement')}</th>
                      <th>{t('coverage')}</th>
                      <th>{t('directionAcc')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {a.series.map((s) => (
                      <tr key={`${s.crop}-${s.market}`}>
                        <td>{cropName(s.crop)}</td>
                        <td>{marketName(s.market)}</td>
                        <td>{label(s.selected)}</td>
                        <td>{fmtNum(s.mape[s.selected], 1)}%</td>
                        <td>{s.production_model ? label(s.production_model) : '–'}</td>
                        <td>{pct(s.improvement_pct)}</td>
                        <td>{pct(s.coverage * 100, false)}</td>
                        <td>{pct(s.direction_accuracy * 100, false)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="muted small">
                {t('updated')}: {fmtDateTime(a.generated_at, lang)}
              </p>
            </>
          )
        }}
      </Async>
    </Card>
  )
}

function AssistantEval() {
  const { t, cropName, marketName } = useApp()
  const ev = useAsync(() => api.evalReport(), [])
  const [showAll, setShowAll] = useState(false)
  const [open, setOpen] = useState<number | null>(null)
  return (
    <Card title={t('assistantTest')}>
      <Async state={ev}>
        {(e) => {
          const rows = showAll ? e.rows : e.rows.filter((r) => !r.correct).concat(e.rows.filter((r) => r.correct).slice(0, 8))
          const fmt = (x: { intent?: string; crop?: string | null; market?: string | null }) =>
            [x.intent, x.crop ? cropName(x.crop) : null, x.market ? marketName(x.market) : null].filter(Boolean).join(' · ')
          return (
            <>
              <div className="stat-row">
                <div className="stat">
                  <div className="stat-v">{pct(e.accuracy * 100, false)}</div>
                  <div className="stat-l">
                    {t('accuracy')} ({e.correct}/{e.total})
                  </div>
                </div>
                <div className="stat">
                  <div className="stat-v">{pct(e.target * 100, false)}</div>
                  <div className="stat-l">Target</div>
                </div>
                <div className="stat">
                  <div className="stat-v">{e.made_up_numbers}</div>
                  <div className="stat-l">{t('madeUpNumbers')}</div>
                </div>
                <div className="stat">
                  <PassChip passed={e.passed} />
                </div>
              </div>
              <div className="table-scroll">
                <table className="table compact">
                  <thead>
                    <tr>
                      <th>{t('question')}</th>
                      <th>{t('expected')}</th>
                      <th>{t('got')}</th>
                      <th>{t('correct')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r, i) => (
                      <Fragment key={i}>
                        <tr
                          className={`${r.correct ? '' : 'row-bad'} ${r.answer ? 'clickable-row' : ''}`}
                          onClick={() => r.answer && setOpen(open === i ? null : i)}
                          title={r.answer ? t('showAnswer') : undefined}
                        >
                          <td>
                            {r.answer && <span aria-hidden="true">{open === i ? '▾ ' : '▸ '}</span>}
                            {r.question}
                          </td>
                          <td>{fmt(r.expected)}</td>
                          <td>{fmt(r.got)}</td>
                          <td>
                            {r.correct ? '✓' : '✗'}
                            {r.unverified_numbers && r.unverified_numbers.length > 0 && (
                              <span className="chip chip-warn" title={t('unverified')}>
                                ⚠ {r.unverified_numbers.length}
                              </span>
                            )}
                          </td>
                        </tr>
                        {open === i && r.answer && (
                          <tr className="answer-row">
                            <td colSpan={4}>
                              <strong>{t('showAnswer')}:</strong> {r.answer}
                              {r.unverified_numbers && r.unverified_numbers.length > 0 && (
                                <div className="small">
                                  {t('unverified')}: {r.unverified_numbers.join(', ')}
                                </div>
                              )}
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    ))}
                  </tbody>
                </table>
              </div>
              {!showAll && e.rows.length > rows.length && (
                <button className="btn btn-link" onClick={() => setShowAll(true)}>
                  + {e.rows.length - rows.length}
                </button>
              )}
            </>
          )
        }}
      </Async>
    </Card>
  )
}

function WarningsReview() {
  const { t, cropName, marketName, bi } = useApp()
  const w = useAsync(() => api.warnings('pending'), [])
  const [err, setErr] = useState<string | null>(null)
  const review = async (id: string, decision: 'approve' | 'reject') => {
    setErr(null)
    try {
      await api.reviewWarning(id, decision)
      w.reload()
    } catch (e) {
      setErr((e as Error).message)
    }
  }
  return (
    <div>
      <h3>{t('pendingWarnings')}</h3>
      {err && <ErrorBox error={err} />}
      <Async state={w}>
        {(d) => {
          const rows = rowsOf<Warning>(d)
          return rows.length === 0 ? (
            <p className="empty">{t('noPendingWarnings')}</p>
          ) : (
            <ul className="feed">
              {rows.map((x) => (
                <li key={x.id} className="callout callout-warn">
                  <div className="small muted">
                    {cropName(x.crop)} · {marketName(x.market)} · <FmtDate iso={x.date} /> · {t(`type_${x.type}` as 'type_price_spike')}
                    {x.magnitude != null && ` · ${t('magnitude')}: ${fmtNum(x.magnitude, 1)}`}
                  </div>
                  <div>{bi(x)}</div>
                  <div className="row-inline">
                    <button className="btn btn-primary btn-small" onClick={() => review(x.id, 'approve')}>
                      {t('approve')}
                    </button>
                    <button className="btn btn-secondary btn-small" onClick={() => review(x.id, 'reject')}>
                      {t('reject')}
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )
        }}
      </Async>
    </div>
  )
}

function BulletinEditor({ b, onDone }: { b: Bulletin; onDone: () => void }) {
  const { t } = useApp()
  const [form, setForm] = useState({ title_en: b.title_en, title_te: b.title_te, body_en: b.body_en, body_te: b.body_te })
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  return (
    <form
      className="stack"
      onSubmit={async (e) => {
        e.preventDefault()
        setBusy(true)
        setErr(null)
        try {
          await api.updateBulletin(b.id, form)
          onDone()
        } catch (ex) {
          setErr((ex as Error).message)
        } finally {
          setBusy(false)
        }
      }}
    >
      <label className="field">
        <span>{t('titleTe')}</span>
        <input value={form.title_te} onChange={(e) => setForm({ ...form, title_te: e.target.value })} />
      </label>
      <label className="field">
        <span>{t('bodyTe')}</span>
        <textarea rows={8} value={form.body_te} onChange={(e) => setForm({ ...form, body_te: e.target.value })} />
      </label>
      <label className="field">
        <span>{t('titleEn')}</span>
        <input value={form.title_en} onChange={(e) => setForm({ ...form, title_en: e.target.value })} />
      </label>
      <label className="field">
        <span>{t('bodyEn')}</span>
        <textarea rows={8} value={form.body_en} onChange={(e) => setForm({ ...form, body_en: e.target.value })} />
      </label>
      {err && <ErrorBox error={err} />}
      <div className="row-inline">
        <button className="btn btn-primary" type="submit" disabled={busy}>
          {t('save')}
        </button>
        <button className="btn btn-secondary" type="button" onClick={onDone}>
          {t('cancel')}
        </button>
      </div>
    </form>
  )
}

function BulletinsReview() {
  const { t, lang } = useApp()
  const list = useAsync(() => api.bulletins('all'), [])
  const [editing, setEditing] = useState<number | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const act = async (fn: () => Promise<unknown>) => {
    setErr(null)
    setBusy(true)
    try {
      await fn()
      list.reload()
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <div>
      <div className="row-between">
        <h3>{t('bulletins')}</h3>
        <button className="btn btn-primary" disabled={busy} onClick={() => act(() => api.draftBulletin())}>
          ✎ {t('draftBulletin')}
        </button>
      </div>
      {err && <ErrorBox error={err} />}
      <Async state={list}>
        {(d) => {
          const rows = rowsOf<Bulletin>(d)
          return rows.length === 0 ? (
            <p className="empty">{t('noBulletinsStaff')}</p>
          ) : (
            <div className="feed">
              {rows.map((b) => (
                <article key={b.id} className="bulletin">
                  <div className="row-between">
                    <div>
                      <strong>{lang === 'te' ? b.title_te || b.title_en : b.title_en}</strong>
                      <div className="small muted">
                        {t('weekOf')}: <FmtDate iso={b.week_start} /> ·{' '}
                        <span className={`chip status-${b.status}`}>{b.status ? t(`status_${b.status}` as 'status_draft') : ''}</span>
                        {b.reviewed_by && ` · ${b.reviewed_by}`}
                      </div>
                    </div>
                  </div>
                  {editing === b.id ? (
                    <BulletinEditor
                      b={b}
                      onDone={() => {
                        setEditing(null)
                        list.reload()
                      }}
                    />
                  ) : (
                    <>
                      <div className="pre">{lang === 'te' ? b.body_te || b.body_en : b.body_en}</div>
                      <div className="row-inline">
                        <button className="btn btn-secondary btn-small" onClick={() => setEditing(b.id)}>
                          {t('edit')}
                        </button>
                        {b.status !== 'approved' && (
                          <button className="btn btn-primary btn-small" disabled={busy} onClick={() => act(() => api.reviewBulletin(b.id, 'approve'))}>
                            {t('approve')}
                          </button>
                        )}
                        {b.status !== 'held' && (
                          <button className="btn btn-secondary btn-small" disabled={busy} onClick={() => act(() => api.reviewBulletin(b.id, 'hold'))}>
                            {t('hold')}
                          </button>
                        )}
                      </div>
                    </>
                  )}
                </article>
              ))}
            </div>
          )
        }}
      </Async>
    </div>
  )
}

function FeedbackList() {
  const { t, lang } = useApp()
  const fb = useAsync(() => api.feedbackList(), [])
  return (
    <div>
      <h3>{t('farmerFeedback')}</h3>
      <Async state={fb}>
        {(d) => {
          const rows = rowsOf<FeedbackRow>(d)
          return rows.length === 0 ? (
            <p className="empty">{t('noFeedback')}</p>
          ) : (
            <div className="table-scroll">
              <table className="table compact">
                <thead>
                  <tr>
                    <th>{t('time')}</th>
                    <th>{t('question')}</th>
                    <th>{t('answer')}</th>
                    <th>👍/👎</th>
                    <th>{t('correction')}</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={r.id ?? i}>
                      <td>{fmtDateTime(r.ts ?? r.created_at, lang)}</td>
                      <td>{r.question}</td>
                      <td className="small">{r.answer}</td>
                      <td>{r.helpful ? '👍' : '👎'}</td>
                      <td>{r.correction ?? ''}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        }}
      </Async>
    </div>
  )
}

export default function DashboardPage() {
  const { t, user } = useApp()
  const staff = user && (user.role === 'officer' || user.role === 'admin')
  return (
    <div className="page">
      <h1 className="page-title">{t('dashboardTitle')}</h1>
      <Overview />
      <Card title={t('collectiveSale')}>
        <p className="muted small">{t('top3')}</p>
        <CompareMarkets unit="t" topN={3} showMap={false} showAlert={false} storageKey="mm_compare_fpo" />
      </Card>
      <AccuracyReport />
      <AssistantEval />
      <Card title={t('staffSection')}>
        {staff ? (
          <div className="stack-lg">
            <WarningsReview />
            <BulletinsReview />
            <FeedbackList />
          </div>
        ) : (
          <div className="callout">
            {t('loginToReview')} <Link to="/login">{t('navLogin')}</Link>
          </div>
        )}
      </Card>
    </div>
  )
}
