import { useEffect } from 'react'
import { MapContainer, Marker, Popup, TileLayer, useMap } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import type { Market } from '../api'
import { useApp } from '../state'
import { rupees } from '../i18n'

const marketIcon = (label: string, best: boolean) =>
  L.divIcon({
    className: 'mm-pin-wrap',
    html: `<div class="mm-pin ${best ? 'mm-pin-best' : ''}">${label}</div>`,
    iconSize: [28, 28],
    iconAnchor: [14, 14],
  })

const homeIcon = L.divIcon({
  className: 'mm-pin-wrap',
  html: '<div class="mm-pin mm-pin-home">⌂</div>',
  iconSize: [28, 28],
  iconAnchor: [14, 14],
})

function Fit({ points }: { points: [number, number][] }) {
  const map = useMap()
  const key = points.map((p) => p.join(',')).join('|')
  useEffect(() => {
    if (points.length === 0) return
    if (points.length === 1) {
      map.setView(points[0], 9)
      return
    }
    map.fitBounds(L.latLngBounds(points), { padding: [24, 24] })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, key])
  return null
}

export interface MapMarket {
  market: Market
  rank?: number
  net?: number
  best?: boolean
}

export function MarketMap({ markets, origin }: { markets: MapMarket[]; origin?: { lat: number; lon: number } | null }) {
  const { lang } = useApp()
  const pts: [number, number][] = markets.map((m) => [m.market.lat, m.market.lon])
  if (origin) pts.push([origin.lat, origin.lon])
  const center: [number, number] = pts[0] ?? [14.6, 78.6]
  return (
    <div className="map-wrap">
      <MapContainer center={center} zoom={7} scrollWheelZoom={false} style={{ height: '100%', width: '100%' }}>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <Fit points={pts} />
        {markets.map((m) => (
          <Marker key={m.market.id} position={[m.market.lat, m.market.lon]} icon={marketIcon(m.rank ? String(m.rank) : '•', !!m.best)}>
            <Popup>
              <strong>{m.market[lang]}</strong>
              {m.net !== undefined && <div>{rupees(m.net)} / qtl</div>}
            </Popup>
          </Marker>
        ))}
        {origin && <Marker position={[origin.lat, origin.lon]} icon={homeIcon} />}
      </MapContainer>
    </div>
  )
}
