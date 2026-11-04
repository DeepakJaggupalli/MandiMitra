import { useEffect, useRef, useState } from 'react'
import { api, type AskContext, type AskResponse, type Lang } from '../api'
import { loadJSON, saveJSON, useApp } from '../state'
import { FmtDate } from '../components/common'

// Minimal Web Speech API typings (not in lib.dom).
interface SpeechRecognitionResultLike {
  isFinal: boolean
  0: { transcript: string }
}
interface SpeechRecognitionEventLike {
  resultIndex: number
  results: ArrayLike<SpeechRecognitionResultLike>
}
interface SpeechRecognitionLike {
  lang: string
  interimResults: boolean
  continuous: boolean
  maxAlternatives: number
  start: () => void
  stop: () => void
  abort: () => void
  onresult: ((e: SpeechRecognitionEventLike) => void) | null
  onerror: ((e: { error: string }) => void) | null
  onend: (() => void) | null
}
type SRCtor = new () => SpeechRecognitionLike

function getSR(): SRCtor | null {
  const w = window as unknown as { SpeechRecognition?: SRCtor; webkitSpeechRecognition?: SRCtor }
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null
}

interface Msg {
  id: string
  role: 'user' | 'bot'
  text: string
  res?: AskResponse
  feedback?: 'up' | 'down' | 'sent'
}

const DEFAULTS: Record<Lang, string[]> = {
  te: ['మదనపల్లెలో టమాటా ధర ఎంత?', 'Madanapalle lo tomato rate entha?', 'కర్నూలులో ఉల్లిపాయ అమ్మాలా ఆగాలా?', '20 క్వింటాళ్ల టమాటా ఎక్కడ అమ్మాలి?'],
  en: [
    'Madanapalle lo tomato rate entha?',
    'Should I sell onion in Kurnool today or wait?',
    'Where should I sell 20 quintals of tomato?',
    'Banana price trend in Kadapa',
  ],
}

function speak(text: string, lang: Lang, onEnd: () => void) {
  if (!('speechSynthesis' in window)) return false
  const synth = window.speechSynthesis
  synth.cancel()
  const u = new SpeechSynthesisUtterance(text)
  const want = lang === 'te' ? 'te' : 'en'
  const voices = synth.getVoices()
  const v =
    voices.find((x) => x.lang.toLowerCase().startsWith(want) && x.lang.toLowerCase().includes('in')) ??
    voices.find((x) => x.lang.toLowerCase().startsWith(want))
  if (v) u.voice = v
  u.lang = lang === 'te' ? 'te-IN' : 'en-IN'
  u.rate = 0.95
  u.onend = onEnd
  u.onerror = onEnd
  synth.speak(u)
  return true
}

export function AskPage() {
  const { t, lang } = useApp()
  const [msgs, setMsgs] = useState<Msg[]>(() => loadJSON<Msg[]>('mm_chat', [], 'session'))
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [listening, setListening] = useState(false)
  const [micMsg, setMicMsg] = useState<string | null>(null)
  const [speakingId, setSpeakingId] = useState<string | null>(null)
  const [correctionFor, setCorrectionFor] = useState<string | null>(null)
  const [correction, setCorrection] = useState('')
  const recRef = useRef<SpeechRecognitionLike | null>(null)
  const endRef = useRef<HTMLDivElement | null>(null)
  const SR = typeof window !== 'undefined' ? getSR() : null

  useEffect(() => {
    saveJSON('mm_chat', msgs.slice(-40), 'session')
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [msgs])

  useEffect(() => {
    // warm up voices list (Chrome loads it async)
    if ('speechSynthesis' in window) window.speechSynthesis.getVoices()
    return () => {
      recRef.current?.abort()
      if ('speechSynthesis' in window) window.speechSynthesis.cancel()
    }
  }, [])

  const lastBot = [...msgs].reverse().find((m) => m.role === 'bot' && m.res)
  const suggestions = lastBot?.res?.suggestions?.length ? lastBot.res.suggestions : DEFAULTS[lang]

  const send = async (q: string) => {
    const question = q.trim()
    if (!question || busy) return
    const uid = `u${Date.now()}`
    setMsgs((m) => [...m, { id: uid, role: 'user', text: question }])
    setInput('')
    setBusy(true)
    try {
      const saved = loadJSON<{ lat?: number; lon?: number; quantity_qtl?: number } | null>('mm_origin', null)
      const ctx: AskContext = {}
      if (saved && typeof saved.lat === 'number' && typeof saved.lon === 'number') {
        ctx.lat = saved.lat
        ctx.lon = saved.lon
        if (typeof saved.quantity_qtl === 'number' && saved.quantity_qtl > 0) ctx.quantity_qtl = saved.quantity_qtl
      }
      const res = await api.ask(question, lang, ctx)
      setMsgs((m) => [...m, { id: `b${Date.now()}`, role: 'bot', text: res.answer, res }])
    } catch (e) {
      setMsgs((m) => [...m, { id: `e${Date.now()}`, role: 'bot', text: `⚠ ${(e as Error).message}` }])
    } finally {
      setBusy(false)
    }
  }

  const toggleMic = () => {
    if (!SR) {
      setMicMsg(t('micUnsupported'))
      return
    }
    if (listening) {
      recRef.current?.stop()
      return
    }
    const rec = new SR()
    rec.lang = lang === 'te' ? 'te-IN' : 'en-IN'
    rec.interimResults = true
    rec.continuous = false
    rec.maxAlternatives = 1
    let finalText = ''
    rec.onresult = (e) => {
      let interim = ''
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i]
        if (r.isFinal) finalText += r[0].transcript
        else interim += r[0].transcript
      }
      setInput((finalText + interim).trim())
    }
    rec.onerror = (e) => {
      setMicMsg(e.error === 'not-allowed' ? 'Microphone permission denied.' : `Mic: ${e.error}`)
    }
    rec.onend = () => {
      setListening(false)
      recRef.current = null
      if (finalText.trim()) void send(finalText)
    }
    recRef.current = rec
    setMicMsg(null)
    setListening(true)
    try {
      rec.start()
    } catch {
      setListening(false)
    }
  }

  const play = (m: Msg) => {
    if (speakingId === m.id) {
      window.speechSynthesis?.cancel()
      setSpeakingId(null)
      return
    }
    const l: Lang = m.res?.lang === 'en' ? 'en' : m.res?.lang === 'te' ? 'te' : lang
    if (speak(m.text, l, () => setSpeakingId(null))) setSpeakingId(m.id)
  }

  const sendFeedback = (m: Msg, helpful: boolean, corr: string | null) => {
    const idx = msgs.findIndex((x) => x.id === m.id)
    const q = [...msgs.slice(0, idx)].reverse().find((x) => x.role === 'user')?.text ?? ''
    api.feedback({ question: q, answer: m.text, helpful, correction: corr }).catch(() => undefined)
    setMsgs((all) => all.map((x) => (x.id === m.id ? { ...x, feedback: 'sent' } : x)))
  }

  return (
    <div className="page chat-page">
      <div className="chat-head">
        <div>
          <h1 className="page-title">{t('askTitle')}</h1>
          <p className="muted small">{t('askSub')}</p>
        </div>
        {msgs.length > 0 && (
          <button className="btn btn-link" onClick={() => setMsgs([])}>
            {t('clearChat')}
          </button>
        )}
      </div>

      <div className="chat" aria-live="polite">
        {msgs.length === 0 && !busy && <div className="chat-empty muted">{t('askEmpty')}</div>}
        {msgs.map((m) => (
          <div key={m.id} className={`bubble ${m.role === 'user' ? 'bubble-user' : 'bubble-bot'}`}>
            <div className="bubble-text">{m.text}</div>
            {m.role === 'bot' && m.res && (
              <div className="bubble-meta">
                {m.res.data_date && (
                  <span>
                    {t('dataDate')}: <FmtDate iso={m.res.data_date} />
                  </span>
                )}
                {m.res.source_label && <span>{m.res.source_label}</span>}
                {m.res.guard === 'passed' && <span title={t('checkedNumbers')}>✓ {t('checkedNumbers')}</span>}
                {m.res.used_llm && <span>{t('aiWritten')}</span>}
              </div>
            )}
            {m.role === 'bot' && m.res && (
              <div className="bubble-actions">
                <button className="btn btn-small" onClick={() => play(m)}>
                  {speakingId === m.id ? `■ ${t('stop')}` : `▶ ${t('play')}`}
                </button>
                {m.feedback === 'sent' ? (
                  <span className="muted small">{t('thanks')}</span>
                ) : (
                  <>
                    <button className="btn btn-small" aria-label={t('helpful')} onClick={() => sendFeedback(m, true, null)}>
                      👍
                    </button>
                    <button
                      className="btn btn-small"
                      aria-label={t('notHelpful')}
                      onClick={() => {
                        setCorrectionFor(m.id)
                        setCorrection('')
                      }}
                    >
                      👎
                    </button>
                  </>
                )}
              </div>
            )}
            {correctionFor === m.id && m.feedback !== 'sent' && (
              <form
                className="correction"
                onSubmit={(e) => {
                  e.preventDefault()
                  sendFeedback(m, false, correction.trim() || null)
                  setCorrectionFor(null)
                }}
              >
                <label className="field">
                  <span>{t('correctionPrompt')}</span>
                  <textarea rows={2} value={correction} onChange={(e) => setCorrection(e.target.value)} />
                </label>
                <button className="btn btn-secondary" type="submit">
                  {t('submit')}
                </button>
              </form>
            )}
          </div>
        ))}
        {busy && <div className="bubble bubble-bot muted">{t('thinking')}</div>}
        <div ref={endRef} />
      </div>

      <div className="chips">
        {suggestions.slice(0, 4).map((s) => (
          <button key={s} className="chip chip-suggest" onClick={() => void send(s)} disabled={busy}>
            {s}
          </button>
        ))}
      </div>

      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault()
          void send(input)
        }}
      >
        {SR && (
          <button
            type="button"
            className={`btn btn-mic ${listening ? 'is-listening' : ''}`}
            onClick={toggleMic}
            aria-pressed={listening}
            aria-label={listening ? t('listening') : t('holdToSpeak')}
            title={listening ? t('listening') : t('holdToSpeak')}
          >
            🎙
          </button>
        )}
        <input value={input} onChange={(e) => setInput(e.target.value)} placeholder={listening ? t('listening') : t('askPlaceholder')} aria-label={t('askPlaceholder')} />
        <button className="btn btn-primary" type="submit" disabled={busy || !input.trim()}>
          {t('send')}
        </button>
      </form>
      {listening && <p className="muted small center">{t('listening')}</p>}
      {(micMsg || !SR) && <p className="muted small center">{micMsg ?? t('micUnsupported')}</p>}
      <p className="guide-note">
        {t('guideNote')} {t('decisionYours')}
      </p>
    </div>
  )
}
