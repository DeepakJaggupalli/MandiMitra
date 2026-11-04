// Generates public/icon-192.png and public/icon-512.png without extra dependencies.
// Draws the same design as public/icon.svg (green tile, white rising line, yellow dot).
import { deflateSync } from 'node:zlib'
import { writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const here = dirname(fileURLToPath(import.meta.url))

function crc32(buf) {
  let c, crc = 0xffffffff
  for (let n = 0; n < buf.length; n++) {
    c = (crc ^ buf[n]) & 0xff
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
    crc = (crc >>> 8) ^ c
  }
  return (crc ^ 0xffffffff) >>> 0
}

function chunk(type, data) {
  const len = Buffer.alloc(4)
  len.writeUInt32BE(data.length)
  const td = Buffer.concat([Buffer.from(type), data])
  const crc = Buffer.alloc(4)
  crc.writeUInt32BE(crc32(td))
  return Buffer.concat([len, td, crc])
}

function segDist(px, py, ax, ay, bx, by) {
  const dx = bx - ax, dy = by - ay
  const t = Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
  const cx = ax + t * dx, cy = ay + t * dy
  return Math.hypot(px - cx, py - cy)
}

function render(size) {
  const s = size / 512
  const line = [[96, 352], [176, 272], [240, 320], [336, 208], [416, 160]]
  const raw = Buffer.alloc((size * 4 + 1) * size)
  for (let y = 0; y < size; y++) {
    raw[y * (size * 4 + 1)] = 0
    for (let x = 0; x < size; x++) {
      const X = (x + 0.5) / s, Y = (y + 0.5) / s
      let r = 0, g = 0, b = 0, a = 0
      // rounded rect r=96
      const rr = 96
      const qx = Math.max(rr - X, X - (512 - rr), 0)
      const qy = Math.max(rr - Y, Y - (512 - rr), 0)
      if (Math.hypot(qx, qy) <= rr) { r = 0x1b; g = 0x6b; b = 0x3a; a = 255 }
      if (a) {
        // bottom bar
        if (Y >= 384 && Y <= 416 && X >= 96 && X <= 416) {
          const ex = Math.max(112 - X, X - 400, 0)
          if (Math.hypot(ex, Math.max(400 - Y, Y - 400, 0) > 0 ? 0 : 0) <= 16) { r = 0xcd; g = 0xe8; b = 0xd4 }
        }
        let d = Infinity
        for (let i = 0; i < line.length - 1; i++) d = Math.min(d, segDist(X, Y, ...line[i], ...line[i + 1]))
        if (d <= 18) { r = 255; g = 255; b = 255 }
        if (Math.hypot(X - 416, Y - 160) <= 30) { r = 0xf2; g = 0xb6; b = 0x32 }
      }
      const o = y * (size * 4 + 1) + 1 + x * 4
      raw[o] = r; raw[o + 1] = g; raw[o + 2] = b; raw[o + 3] = a
    }
  }
  const ihdr = Buffer.alloc(13)
  ihdr.writeUInt32BE(size, 0)
  ihdr.writeUInt32BE(size, 4)
  ihdr[8] = 8; ihdr[9] = 6; ihdr[10] = 0; ihdr[11] = 0; ihdr[12] = 0
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', ihdr),
    chunk('IDAT', deflateSync(raw)),
    chunk('IEND', Buffer.alloc(0)),
  ])
}

for (const size of [192, 512]) {
  writeFileSync(join(here, '..', 'public', `icon-${size}.png`), render(size))
  console.log(`wrote icon-${size}.png`)
}
