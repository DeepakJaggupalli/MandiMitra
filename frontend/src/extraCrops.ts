import { useEffect, useState } from 'react'
import { loadJSON, saveJSON } from './state'

/** Optional crops the farmer chose to follow (prices only), kept on this phone. */
const KEY = 'mm_extra_crops'
const listeners = new Set<(ids: string[]) => void>()
let current: string[] = loadJSON<string[]>(KEY, [])

export function useExtraCrops() {
  const [ids, setIds] = useState<string[]>(current)
  useEffect(() => {
    listeners.add(setIds)
    return () => {
      listeners.delete(setIds)
    }
  }, [])
  const toggle = (id: string) => {
    current = current.includes(id) ? current.filter((x) => x !== id) : [...current, id]
    saveJSON(KEY, current)
    listeners.forEach((l) => l(current))
  }
  return { ids, has: (id: string) => ids.includes(id), toggle }
}
