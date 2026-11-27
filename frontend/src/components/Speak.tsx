import { useEffect, useState } from 'react'
import { useApp } from '../state'

/** Only one thing speaks at a time; every button listens to this. */
let activeId: string | null = null
const listeners = new Set<(id: string | null) => void>()
const setActive = (id: string | null) => {
  activeId = id
  listeners.forEach((l) => l(id))
}

function pickVoice(want: 'te' | 'en'): SpeechSynthesisVoice | undefined {
  const voices = window.speechSynthesis.getVoices()
  return (
    voices.find((v) => v.lang.toLowerCase().startsWith(want) && v.lang.toLowerCase().includes('in')) ??
    voices.find((v) => v.lang.toLowerCase().startsWith(want))
  )
}

/**
 * Speaker button. Reads the Telugu text with a Telugu voice; if the phone has no Telugu
 * voice it reads the English text instead and says so.
 */
export function SpeakButton({ id, te, en, big = false }: { id: string; te: string; en: string; big?: boolean }) {
  const { t, lang } = useApp()
  const [speaking, setSpeaking] = useState(activeId === id)
  const [note, setNote] = useState<string | null>(null)
  const supported = typeof window !== 'undefined' && 'speechSynthesis' in window

  useEffect(() => {
    const l = (a: string | null) => setSpeaking(a === id)
    listeners.add(l)
    if (supported) window.speechSynthesis.getVoices() // warm up the voice list
    return () => {
      listeners.delete(l)
    }
  }, [id, supported])

  if (!supported) return null

  const onClick = (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    const synth = window.speechSynthesis
    synth.cancel()
    if (speaking) {
      setActive(null)
      return
    }
    let useLang: 'te' | 'en' = lang
    let voice = pickVoice(useLang)
    if (useLang === 'te' && !voice && synth.getVoices().length > 0) {
      useLang = 'en'
      voice = pickVoice('en')
      setNote(t('noTeVoice'))
    } else {
      setNote(null)
    }
    const u = new SpeechSynthesisUtterance(useLang === 'te' ? te : en)
    if (voice) u.voice = voice
    u.lang = useLang === 'te' ? 'te-IN' : 'en-IN'
    u.rate = 0.9
    u.onend = u.onerror = () => {
      if (activeId === id) setActive(null)
    }
    setActive(id)
    synth.speak(u)
  }

  return (
    <>
      <button
        type="button"
        className={big ? 'btn btn-primary btn-listen' : 'icon-btn'}
        onClick={onClick}
        aria-label={speaking ? t('stopAudio') : t('listen')}
        title={speaking ? t('stopAudio') : t('listen')}
      >
        <span aria-hidden="true">{speaking ? '⏹' : '🔊'}</span>
        {big && <span>{speaking ? t('stopAudio') : t('listen')}</span>}
      </button>
      {big && note && <p className="muted small">{note}</p>}
    </>
  )
}

/** Plain spoken summary (no ₹ sign or commas, so voices read it as a number). */
export function spokenSummary(
  cropTe: string, cropEn: string, marketTe: string, marketEn: string, modal: number,
  direction: 'up' | 'down' | 'flat' | null, pointMean: number | null,
): { te: string; en: string } {
  const n = Math.round(modal)
  let te = `${marketTe}లో ${cropTe} ధర ఈ రోజు క్వింటాల్‌కు ${n} రూపాయలు.`
  let en = `${cropEn} at ${marketEn}: today ${n} rupees per quintal.`
  if (direction && pointMean != null) {
    const p = Math.round(pointMean)
    const dirTe = direction === 'up' ? 'పెరిగే అవకాశం ఉంది' : direction === 'down' ? 'తగ్గే అవకాశం ఉంది' : 'దాదాపు ఇలాగే ఉండే అవకాశం ఉంది'
    const dirEn = direction === 'up' ? 'likely to rise' : direction === 'down' ? 'likely to fall' : 'likely to stay about the same'
    te += ` వచ్చే 7 రోజుల్లో ధర ${dirTe}, సుమారు ${p} రూపాయలు.`
    en += ` In the next 7 days the price is ${dirEn}, around ${p} rupees.`
  }
  return { te, en }
}
