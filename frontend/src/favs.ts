import { useEffect, useState } from 'react'
import { loadJSON, saveJSON } from './state'

/** Favourite crop-market pairs ("onion|kadapa"), kept on this phone only. */
const KEY = 'mm_favs'
const listeners = new Set<(f: string[]) => void>()
let current: string[] = loadJSON<string[]>(KEY, [])

export const favKey = (crop: string, market: string) => `${crop}|${market}`

export function useFavs() {
  const [favs, setFavs] = useState<string[]>(current)
  useEffect(() => {
    listeners.add(setFavs)
    return () => {
      listeners.delete(setFavs)
    }
  }, [])
  const toggle = (key: string) => {
    current = current.includes(key) ? current.filter((k) => k !== key) : [...current, key]
    saveJSON(KEY, current)
    listeners.forEach((l) => l(current))
  }
  return { favs, isFav: (key: string) => favs.includes(key), toggle }
}
