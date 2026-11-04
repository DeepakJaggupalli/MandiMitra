import { Area, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { ForecastPoint, PricePoint } from '../api'
import { useApp } from '../state'
import { fmtDate, rupees, shortDate } from '../i18n'

interface Row {
  date: string
  modal?: number
  minmax?: [number, number]
  ly?: number
  point?: number
  band?: [number, number]
}

export function PriceChart({
  history,
  lastYear,
  forecast,
  showLastYear,
}: {
  history: PricePoint[]
  lastYear: { date: string; modal: number }[]
  forecast: ForecastPoint[] | null
  showLastYear: boolean
}) {
  const { t, lang } = useApp()
  const map = new Map<string, Row>()
  const get = (d: string) => {
    let r = map.get(d)
    if (!r) {
      r = { date: d }
      map.set(d, r)
    }
    return r
  }
  for (const h of history) {
    const r = get(h.date)
    r.modal = h.modal
    if (h.min != null && h.max != null) r.minmax = [h.min, h.max]
  }
  if (showLastYear) {
    const first = history.length ? history[0].date : null
    for (const l of lastYear) {
      if (first && l.date < first) continue
      get(l.date).ly = l.modal
    }
  }
  if (forecast && forecast.length && history.length) {
    const last = history[history.length - 1]
    const r = get(last.date)
    r.point = last.modal
    r.band = [last.modal, last.modal]
    for (const f of forecast) {
      const fr = get(f.date)
      fr.point = f.point
      fr.band = [f.lo, f.hi]
    }
  }
  const data = Array.from(map.values()).sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0))
  const lastActual = history.length ? history[history.length - 1].date : undefined

  if (data.length === 0) return <p className="muted">{t('noData')}</p>

  const names: Record<string, string> = {
    modal: t('actual'),
    minmax: t('minMax'),
    ly: t('lastYear'),
    point: t('forecastLine'),
    band: t('forecastBand'),
  }

  return (
    <div className="chart-wrap" role="img" aria-label={t('chartTitle')}>
      <ResponsiveContainer width="100%" height={280}>
        <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="#e3e8e2" vertical={false} />
          <XAxis dataKey="date" tickFormatter={shortDate} minTickGap={28} tick={{ fontSize: 12 }} />
          <YAxis
            width={56}
            tick={{ fontSize: 12 }}
            tickFormatter={(v: number) => `₹${Math.round(v).toLocaleString('en-IN')}`}
            domain={['auto', 'auto']}
          />
          <Tooltip
            labelFormatter={(d: string) => fmtDate(d, lang) + (lastActual && d > lastActual ? ` · ${t('forecastLine')}` : '')}
            formatter={(value: unknown, name: string) => {
              const label = names[name] ?? name
              if (Array.isArray(value)) return [`${rupees(value[0])} – ${rupees(value[1])}`, label]
              return [rupees(value as number), label]
            }}
          />
          <Legend formatter={(v: string) => names[v] ?? v} wrapperStyle={{ fontSize: 12 }} />
          <Area dataKey="minmax" stroke="none" fill="#9cc7a8" fillOpacity={0.25} isAnimationActive={false} name="minmax" connectNulls />
          <Area dataKey="band" stroke="none" fill="#f2b632" fillOpacity={0.3} isAnimationActive={false} name="band" connectNulls />
          {showLastYear && (
            <Line dataKey="ly" stroke="#8a8f99" strokeDasharray="2 3" dot={false} strokeWidth={1.5} isAnimationActive={false} name="ly" connectNulls />
          )}
          <Line dataKey="modal" stroke="#1b6b3a" strokeWidth={2.2} dot={false} isAnimationActive={false} name="modal" connectNulls />
          <Line dataKey="point" stroke="#b06d00" strokeWidth={2.2} strokeDasharray="6 4" dot={{ r: 2 }} isAnimationActive={false} name="point" connectNulls />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}
