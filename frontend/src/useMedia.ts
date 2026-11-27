import { useEffect, useState } from 'react'

/** True on desktop-width screens. Phones and small tablets get the simple farmer view. */
export function useIsDesktop(minWidth = 1024): boolean {
  const query = `(min-width: ${minWidth}px)`
  const [match, setMatch] = useState(() => typeof window !== 'undefined' && window.matchMedia(query).matches)
  useEffect(() => {
    const mq = window.matchMedia(query)
    const update = () => setMatch(mq.matches)
    update()
    mq.addEventListener('change', update)
    return () => mq.removeEventListener('change', update)
  }, [query])
  return match
}
