import { useEffect, useRef, useState } from 'react'
import Editor from '@monaco-editor/react'
import {
  Activity, ArrowDownToLine, ArrowLeft, ArrowUpRight, Check, ChevronDown,
  CircleHelp, Clock3, Code2, Download, FileAudio2, Lightbulb, Mic, MicOff, Radio,
  RotateCcw, Signal, SignalLow, Sparkles, Square, Wifi, WifiOff,
} from 'lucide-react'
import {
  CartesianGrid, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis,
} from 'recharts'
import { api, sendOutboxEntry } from './lib/api.js'
import { enqueue, flushOutbox, queuedCount } from './lib/offlineQueue.js'

const FALLBACK_DOMAINS = [
  { id: 'backend_systems', name: 'Backend Engineering', subtrack: 'Core System Design', short_code: 'SYS / 01', language: 'python', challenge: 'Design a global rate-limiting tier for checkout at 100,000 peak RPS.', starter_code: 'class RateLimiter:\n    def __init__(self, limit, window_seconds):\n        pass\n\n    def allow(self, key, now):\n        pass\n' },
  { id: 'backend_data_infra', name: 'Backend Engineering', subtrack: 'High-Throughput Data Infrastructure', short_code: 'DATA / 02', language: 'python', challenge: 'Design a real-time IoT aggregation pipeline with out-of-order delivery.', starter_code: 'def aggregate_telemetry(events, watermark_ms, sink):\n    pass\n' },
  { id: 'frontend_architecture', name: 'Frontend Engineering', subtrack: 'High-Performance UI Architectures', short_code: 'UI / 03', language: 'javascript', challenge: 'Build a virtualized table for 500,000 records at 60 FPS.', starter_code: 'function VirtualTable({ rows, rowHeight, viewportHeight }) {\n  // Recycle only the rows visible in the viewport.\n}\n' },
  { id: 'ml_platform', name: 'Data Science & Machine Learning', subtrack: 'Distributed ML Platform Design', short_code: 'ML / 04', language: 'python', challenge: 'Design recommendation inference for personalized feeds under 50 ms.', starter_code: 'def recommend(user_id, request_context, feature_store, model):\n    pass\n' },
]

const EMPTY_WAVEFORM = Array.from({ length: 42 }, (_, index) => 0.12 + ((index * 17) % 29) / 100)
const HINT_INACTIVITY_MS = 12_000
const CONTEST_TIME_LIMIT_MS = 90 * 60_000

function formatTime(milliseconds) {
  const totalSeconds = Math.floor(milliseconds / 1000)
  return `${String(Math.floor(totalSeconds / 60)).padStart(2, '0')}:${String(totalSeconds % 60).padStart(2, '0')}`
}

function estimateAstHint(text) {
  if (/\b(class|interface)\b/.test(text)) return 'TypeDeclaration'
  if (/\b(def|function|=>)\b/.test(text)) return 'Function'
  if (/\b(for|while)\b/.test(text)) return 'Loop'
  if (/\b(if|switch)\b/.test(text)) return 'Branch'
  return 'TextMutation'
}

function App() {
  const [domains, setDomains] = useState(FALLBACK_DOMAINS)
  const [domainId, setDomainId] = useState(FALLBACK_DOMAINS[0].id)
  const [screen, setScreen] = useState('setup')
  const [session, setSession] = useState(null)
  const [code, setCode] = useState('')
  const [elapsedMs, setElapsedMs] = useState(0)
  const [starting, setStarting] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [micWarning, setMicWarning] = useState('')
  const [micActive, setMicActive] = useState(false)
  const [waveform, setWaveform] = useState(EMPTY_WAVEFORM)
  const [online, setOnline] = useState(navigator.onLine)
  const [outboxSize, setOutboxSize] = useState(0)
  const [result, setResult] = useState(null)
  const [selectedEvent, setSelectedEvent] = useState(null)
  const [offlineSubmit, setOfflineSubmit] = useState(false)
  const [hintAvailable, setHintAvailable] = useState(false)
  const [hintsUsed, setHintsUsed] = useState(0)
  const [currentHint, setCurrentHint] = useState('')
  const editorRef = useRef(null)
  const sessionStartedAt = useRef(0)
  const elapsedRef = useRef(0)
  const recorderRef = useRef(null)
  const streamRef = useRef(null)
  const audioContextRef = useRef(null)
  const animationRef = useRef(null)
  const codeBufferRef = useRef([])
  const codeBufferTimerRef = useRef(null)
  const writeTasksRef = useRef(new Set())
  const sessionRef = useRef(null)
  const lastVoiceActivityMs = useRef(0)
  const lastCodeActivityMs = useRef(0)
  const lastHintActivityMs = useRef(0)
  const hintsUsedRef = useRef(0)

  const selectedDomain = domains.find((domain) => domain.id === domainId) || domains[0]
  const editorLanguage = selectedDomain?.language || 'python'

  useEffect(() => {
    api.domains().then(setDomains).catch(() => {})
    const updateOnline = () => setOnline(navigator.onLine)
    window.addEventListener('online', updateOnline)
    window.addEventListener('offline', updateOnline)
    return () => {
      window.removeEventListener('online', updateOnline)
      window.removeEventListener('offline', updateOnline)
    }
  }, [])

  useEffect(() => {
    if (screen !== 'active') return undefined
    const ticker = window.setInterval(() => {
      const current = Math.round(performance.now() - sessionStartedAt.current)
      elapsedRef.current = current
      setElapsedMs(current)
    }, 200)
    return () => window.clearInterval(ticker)
  }, [screen])

  useEffect(() => {
    if (screen !== 'active') return undefined
    const timer = window.setInterval(() => {
      const lastActivity = Math.max(
        lastVoiceActivityMs.current,
        lastCodeActivityMs.current,
        lastHintActivityMs.current,
      )
      const hasHints = hintsUsedRef.current < (selectedDomain?.hints?.length || 0)
      setHintAvailable(hasHints && elapsedRef.current - lastActivity >= HINT_INACTIVITY_MS)
    }, 350)
    return () => window.clearInterval(timer)
  }, [screen, domainId, selectedDomain?.hints?.length])

  useEffect(() => {
    if (screen !== 'processing' || !session) return undefined
    let active = true
    const check = async () => {
      try {
        const status = await api.getSession(session.session_id)
        if (!active) return
        if (status.status === 'COMPLETED') {
          setResult(status.result)
          setScreen('completed')
        } else if (status.status === 'FAILED') {
          setError('Analysis could not be completed. Your captured session is still available locally.')
          setScreen('failed')
        }
      } catch {
        setOnline(false)
      }
    }
    check()
    const timer = window.setInterval(check, 2200)
    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [screen, session])

  useEffect(() => {
    if (!session || !['active', 'processing'].includes(screen) || !online) return undefined
    let cancelled = false
    const flush = async () => {
      const remaining = await flushOutbox(session.session_id, sendOutboxEntry)
      if (cancelled) return
      setOutboxSize(remaining)
      if (offlineSubmit && remaining === 0) setOfflineSubmit(false)
    }
    flush()
    return () => { cancelled = true }
  }, [online, screen, session, offlineSubmit])

  useEffect(() => () => {
    if (codeBufferTimerRef.current) window.clearTimeout(codeBufferTimerRef.current)
    if (animationRef.current) cancelAnimationFrame(animationRef.current)
    recorderRef.current?.stream?.getTracks().forEach((track) => track.stop())
    audioContextRef.current?.close().catch(() => {})
  }, [])

  function persistEvent(entry) {
    const task = enqueue(entry)
      .then(async () => {
        const count = await queuedCount(entry.session_id)
        setOutboxSize(count)
        if (navigator.onLine) {
          const remaining = await flushOutbox(entry.session_id, sendOutboxEntry)
          setOutboxSize(remaining)
        }
      })
      .catch(() => setError('The local recovery queue is unavailable. Keep this tab open until you reconnect.'))
      .finally(() => writeTasksRef.current.delete(task))
    writeTasksRef.current.add(task)
    return task
  }

  async function beginCapture() {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false })
    streamRef.current = stream
    let audioContext
    try {
      audioContext = new AudioContext({ sampleRate: 16000 })
    } catch {
      audioContext = new AudioContext()
    }
    audioContextRef.current = audioContext
    const source = audioContext.createMediaStreamSource(stream)
    const analyser = audioContext.createAnalyser()
    analyser.fftSize = 128
    source.connect(analyser)
    const destination = audioContext.createMediaStreamDestination()
    destination.channelCount = 1
    source.connect(destination)
    const frequencies = new Uint8Array(analyser.frequencyBinCount)
    const audioSamples = new Uint8Array(analyser.fftSize)
    let lastWaveformUpdate = 0
    const drawWaveform = () => {
      const now = performance.now()
      if (now - lastWaveformUpdate >= 80) {
        analyser.getByteFrequencyData(frequencies)
        analyser.getByteTimeDomainData(audioSamples)
        let energy = 0
        for (const sample of audioSamples) {
          const normalized = (sample - 128) / 128
          energy += normalized * normalized
        }
        if (Math.sqrt(energy / audioSamples.length) > 0.025) {
          lastVoiceActivityMs.current = elapsedRef.current
        }
        setWaveform(Array.from({ length: 42 }, (_, index) => {
          const value = frequencies[Math.floor(index * frequencies.length / 42)] / 255
          return Math.max(0.08, Math.min(1, value))
        }))
        lastWaveformUpdate = now
      }
      animationRef.current = requestAnimationFrame(drawWaveform)
    }
    drawWaveform()

    const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
      ? 'audio/webm;codecs=opus'
      : undefined
    const recorder = new MediaRecorder(destination.stream, mimeType ? { mimeType } : undefined)
    recorderRef.current = recorder
    recorder.ondataavailable = (event) => {
      if (!event.data.size) return
      const timestamp = Math.max(0, elapsedRef.current - 1000)
      persistEvent({ kind: 'audio', session_id: sessionRef.current.session_id, timestamp_ms: timestamp, blob: event.data })
    }
    recorder.start(1000)
    setMicActive(true)
  }

  async function startInterview() {
    if (starting || !selectedDomain) return
    setStarting(true)
    setError('')
    setMicWarning('')
    try {
      const created = await api.startSession(domainId)
      sessionRef.current = created
      setSession(created)
      setCode(created.starter_code || selectedDomain.starter_code || '')
      sessionStartedAt.current = performance.now()
      elapsedRef.current = 0
      setElapsedMs(0)
      lastVoiceActivityMs.current = 0
      lastCodeActivityMs.current = 0
      lastHintActivityMs.current = 0
      hintsUsedRef.current = 0
      setHintsUsed(0)
      setHintAvailable(false)
      setCurrentHint('')
      setScreen('active')
      try {
        await beginCapture()
      } catch {
        setMicWarning('Microphone access is off. You can still work in the editor; audio analysis will be unavailable.')
      }
    } catch (reason) {
      setError(`${reason.message}. Start the API server and try again.`)
    } finally {
      setStarting(false)
    }
  }

  function recordCodeChange(event) {
    if (!sessionRef.current) return
    lastCodeActivityMs.current = elapsedRef.current
    for (const change of event.changes) {
      codeBufferRef.current.push({
        text: change.text,
        deleted: change.rangeLength,
        range: {
          start_line: change.range.startLineNumber,
          end_line: change.range.endLineNumber,
          start_col: change.range.startColumn,
          end_col: change.range.endColumn,
        },
        total_lines: editorRef.current?.getModel()?.getLineCount() || 0,
      })
    }
    if (codeBufferTimerRef.current) window.clearTimeout(codeBufferTimerRef.current)
    codeBufferTimerRef.current = window.setTimeout(flushCodeBuffer, 220)
  }

  function flushCodeBuffer() {
    if (codeBufferTimerRef.current) window.clearTimeout(codeBufferTimerRef.current)
    codeBufferTimerRef.current = null
    const changes = codeBufferRef.current.splice(0)
    if (!changes.length || !sessionRef.current) return
    const inserted = changes.map((change) => change.text).join('')
    persistEvent({
      kind: 'code',
      session_id: sessionRef.current.session_id,
      payload: {
        session_id: sessionRef.current.session_id,
        session_timestamp_ms: elapsedRef.current,
        data: {
          text_inserted: inserted,
          text_deleted_length: changes.reduce((total, change) => total + change.deleted, 0),
          change_range: changes[0].range,
          changes: changes.map((change) => change.range),
          total_lines: changes[changes.length - 1].total_lines,
          ast_node_hint: estimateAstHint(inserted),
        },
      },
    })
  }

  function revealHint() {
    const hints = selectedDomain?.hints || []
    const hintIndex = hintsUsedRef.current
    const hint = hints[hintIndex]
    if (!hint || !sessionRef.current) return
    hintsUsedRef.current += 1
    setHintsUsed(hintsUsedRef.current)
    setHintAvailable(false)
    setCurrentHint(hint)
    lastHintActivityMs.current = elapsedRef.current
    persistEvent({
      kind: 'code',
      session_id: sessionRef.current.session_id,
      payload: {
        session_id: sessionRef.current.session_id,
        session_timestamp_ms: elapsedRef.current,
        event_type: 'HINT_USED',
        data: { hint_id: `${domainId}-${hintIndex + 1}`, hint_index: hintIndex + 1, penalty_points: 5 },
      },
    })
  }

  async function stopCapture() {
    const recorder = recorderRef.current
    if (recorder && recorder.state !== 'inactive') {
      await new Promise((resolve) => {
        recorder.addEventListener('stop', resolve, { once: true })
        recorder.stop()
      })
    }
    if (animationRef.current) cancelAnimationFrame(animationRef.current)
    animationRef.current = null
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
    audioContextRef.current?.close().catch(() => {})
    audioContextRef.current = null
    setMicActive(false)
    setWaveform(EMPTY_WAVEFORM)
  }

  async function finishInterview() {
    if (!session || submitting) return
    setSubmitting(true)
    setError('')
    flushCodeBuffer()
    await stopCapture()
    await Promise.all([...writeTasksRef.current])
    const payload = {
      session_id: session.session_id,
      duration_ms: elapsedRef.current,
      hints_used: hintsUsedRef.current,
      final_code: code,
    }
    await persistEvent({ kind: 'submit', session_id: session.session_id, payload })
    const remaining = await flushOutbox(session.session_id, sendOutboxEntry)
    setOutboxSize(remaining)
    setOfflineSubmit(remaining > 0)
    setScreen('processing')
    setSubmitting(false)
  }

  function onEditorMount(editor) {
    editorRef.current = editor
    editor.onDidChangeModelContent(recordCodeChange)
    requestAnimationFrame(() => editor.layout())
    window.setTimeout(() => editor.layout(), 80)
  }

  function resetStudio() {
    if (screen === 'active' || screen === 'processing') return
    setResult(null)
    setSession(null)
    sessionRef.current = null
    setError('')
    setMicWarning('')
    setScreen('setup')
  }

  function jumpToEvent(event) {
    setSelectedEvent(event)
    const line = event.data?.change_range?.start_line
    if (line && editorRef.current) {
      editorRef.current.revealLineInCenter(line)
      editorRef.current.setPosition({ lineNumber: line, column: event.data?.change_range?.start_col || 1 })
    }
  }

  const report = result?.report
  const codeguruReview = report?.codeguru_review
  const contestReport = report?.contest_simulation
  const timeline = result?.timeline || []
  const chartData = timeline.map((event, index) => ({
    ...event,
    chart_id: index,
    seconds: Math.round(event.session_timestamp_ms / 1000),
    lane: event.event_type === 'CODE_MUTATION' ? 1 : event.event_type === 'SILENCE_GAP' ? 0.5 : event.event_type === 'HINT_USED' ? -0.5 : 0,
  }))

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <button className="brand-lockup" onClick={resetStudio} aria-label="InterviewRunway home">
          <span className="brand-mark"><Activity size={18} strokeWidth={2.2} /></span>
          <span>InterviewRunway<span className="brand-period">.</span></span>
        </button>
        <div className="sidebar-rule" />
        <p className="eyebrow sidebar-label">INTERVIEWRUNWAY <span>01</span></p>
        <div className={`side-step ${screen === 'setup' ? 'is-current' : 'is-done'}`}>
          <span className="step-marker">{screen === 'setup' ? '01' : <Check size={13} />}</span>
          <span>Set the room</span>
        </div>
        <div className={`side-step ${screen === 'active' ? 'is-current' : ['processing', 'completed', 'failed'].includes(screen) ? 'is-done' : ''}`}>
          <span className="step-marker">{['processing', 'completed', 'failed'].includes(screen) ? <Check size={13} /> : '02'}</span>
          <span>Think out loud</span>
        </div>
        <div className={`side-step ${['processing', 'completed', 'failed'].includes(screen) ? 'is-current' : ''}`}>
          <span className="step-marker">03</span>
          <span>Review the tape</span>
        </div>
        <div className="sidebar-bottom">
          <div className="sidebar-note-mark"><Sparkles size={16} /></div>
          <p>Good interviews leave a trail.</p>
          <span>SESSION SIGNAL / LOCAL FIRST</span>
        </div>
      </aside>

      <main className="main-shell">
        <header className="topbar">
          <div className="crumbs"><span>Workspace</span><span className="crumb-divider">/</span><strong>{screen === 'setup' ? 'InterviewRunway' : screen === 'active' ? 'Live session' : screen === 'completed' ? 'Session review' : 'Processing'}</strong></div>
          <div className="topbar-status">
            <span className={`connection-dot ${online ? 'online' : 'offline'}`} />
            <span>{online ? 'Connected' : 'Offline queue active'}</span>
            <span className="topbar-divider" />
            <button className="icon-button help-button" title="About this session" aria-label="About this session"><CircleHelp size={17} /></button>
          </div>
        </header>

        {screen === 'setup' && (
          <section className="setup-view page-enter">
            <div className="setup-heading">
              <p className="eyebrow"><span className="eyebrow-line" /> PROJECT / INTERVIEW PRACTICE</p>
              <h1>Interview<em>Runway</em></h1>
              <p className="setup-deck">Make your thinking visible. One prompt, one editor, and a useful record of how you got there.</p>
            </div>

            <div className="setup-grid">
              <section className="setup-controls">
                <label className="field-label" htmlFor="domain-select">Choose your track <span>REQUIRED</span></label>
                <div className="select-wrap">
                  <select id="domain-select" value={domainId} onChange={(event) => setDomainId(event.target.value)}>
                    {domains.map((domain) => <option key={domain.id} value={domain.id}>{domain.name} / {domain.subtrack}</option>)}
                  </select>
                  <ChevronDown size={17} />
                </div>
                <div className="setup-checklist">
                  <div><span className="check-icon"><Code2 size={15} /></span><span>Code in a focused workspace</span><span className="check-state">READY</span></div>
                  <div><span className="check-icon"><Mic size={15} /></span><span>Capture spoken reasoning</span><span className="check-state">OPTIONAL</span></div>
                  <div><span className="check-icon"><Signal size={15} /></span><span>Save through brief disconnects</span><span className="check-state">ON</span></div>
                </div>
                <button className="primary-button start-button" onClick={startInterview} disabled={starting}>
                  <span>{starting ? 'Preparing session…' : 'Start interview'}</span>
                  <ArrowUpRight size={18} />
                </button>
                <p className="privacy-note"><Wifi size={13} /> Your draft stays in this session workspace.</p>
                {error && <p className="inline-error">{error}</p>}
              </section>

              <section className="prompt-sheet" aria-label="Interview prompt">
                <div className="prompt-topline"><span className="eyebrow">TODAY'S PROMPT</span><span className="prompt-index">{String(Math.max(1, domains.findIndex((item) => item.id === domainId) + 1)).padStart(2, '0')} / {String(domains.length).padStart(2, '0')}</span></div>
                <div className="prompt-illustration" aria-hidden="true">
                  <div className="orbit orbit-one" /><div className="orbit orbit-two" />
                  <div className="prompt-glyph"><span /><span /><span /><span /><span /></div>
                  <span className="prompt-coordinate">{selectedDomain?.short_code || 'TRACK'}</span>
                </div>
                <p className="prompt-track">{selectedDomain?.company_round || selectedDomain?.name} / {selectedDomain?.difficulty || 'ADVANCED'}</p>
                <p className="prompt-subtrack">{selectedDomain?.name || 'Technical interview'} / {selectedDomain?.subtrack}</p>
                <h2>{selectedDomain?.challenge || 'Choose a track to load your prompt.'}</h2>
                <div className="prompt-footer"><span><Clock3 size={14} /> 90 MIN ROUND</span><span>ORIGINAL CHALLENGE</span></div>
                <details className="prep-details">
                  <summary>Preparation notes & question bank <ChevronDown size={14} /></summary>
                  <div className="prep-content">
                    <p className="eyebrow">QUESTIONS TO ASK</p>
                    <ul>{(selectedDomain?.question_bank || []).map((question) => <li key={question}>{question}</li>)}</ul>
                    <p className="eyebrow">TRACK PREPARATION</p>
                    <ul>{(selectedDomain?.preparation_materials || []).map((material) => <li key={material}>{material}</li>)}</ul>
                    {(selectedDomain?.preparation_masterclass || []).map((module) => <div className="masterclass-module" key={module.title}><strong>{module.title}</strong><ul>{module.principles.map((principle) => <li key={principle}>{principle}</li>)}</ul></div>)}
                    <p className="eyebrow">EVALUATION PHASES</p>
                    {(selectedDomain?.rubric_phases || []).map((phase) => <div className="prep-phase" key={phase.name}><strong>{phase.window} / {phase.name}</strong><span>{phase.checks.join(' ')}</span></div>)}
                  </div>
                </details>
              </section>
            </div>
            <footer className="setup-footer"><span>INTERVIEWRUNWAY / INTERVIEW PRACTICE</span><span>BUILD SIGNAL, NOT JUST SYNTAX.</span></footer>
          </section>
        )}

        {screen === 'active' && (
          <section className="session-view page-enter">
            <div className="session-heading">
              <div>
                <p className="eyebrow"><span className="live-dot" /> LIVE SESSION <span className="heading-slash">/</span> {selectedDomain?.name} / {selectedDomain?.subtrack}</p>
                <h1>{selectedDomain?.challenge}</h1>
              </div>
              <div className="session-clock"><Clock3 size={16} /><span>{formatTime(Math.max(0, CONTEST_TIME_LIMIT_MS - elapsedMs))}</span><small>TIME LEFT / 90 MIN</small></div>
            </div>
            <div className="capture-strip">
              <div className={`mic-state ${micActive ? 'capturing' : ''}`}><span className="mic-state-icon">{micActive ? <Mic size={15} /> : <MicOff size={15} />}</span><div><strong>{micActive ? 'Voice capture on' : 'Voice capture off'}</strong><small>{micActive ? 'LOCAL AUDIO / LIVE' : 'EDITOR IS READY'}</small></div></div>
              <div className="waveform" aria-label={micActive ? 'Microphone audio level' : 'Microphone inactive'}>{waveform.map((height, index) => <span key={index} style={{ height: `${Math.max(4, height * 32)}px` }} />)}</div>
              <div className="capture-meta"><span className="capture-pulse" />{online ? 'SYNCING' : 'SAVED LOCALLY'}<span className="capture-separator">/</span>{outboxSize} queued</div>
              <button className="finish-button" onClick={finishInterview} disabled={submitting}><Square size={12} fill="currentColor" />{submitting ? 'Finishing…' : 'Finish session'}</button>
            </div>
            {micWarning && <p className="notice-line"><MicOff size={14} /> {micWarning}</p>}
            {error && <p className="notice-line error-line">{error}</p>}
            {hintAvailable && <div className="hint-unlocked"><Lightbulb size={17} /><div><strong>A structured hint is available</strong><small>Unlocked after 12 seconds without detected voice or code activity.</small></div><button onClick={revealHint}>Reveal hint / -5 pts</button></div>}
            {currentHint && <div className="hint-revealed"><span>HINT {hintsUsed} / {selectedDomain?.hints?.length || 0}</span><p>{currentHint}</p><small>Contest adjustment: -{hintsUsed * 5} points</small></div>}
            <div className="editor-frame">
              <div className="editor-toolbar"><div className="editor-tab"><span className="file-dot" />solution.{editorLanguage === 'javascript' ? 'jsx' : 'py'}<span className="tab-close">×</span></div><div className="editor-language">{editorLanguage.toUpperCase()} <ChevronDown size={12} /></div><div className="editor-save"><span className="save-indicator" />AUTO-SAVED</div></div>
              <div className="editor-body">
                <Editor
                  height="100%"
                  language={editorLanguage}
                  value={code}
                  onChange={(value) => setCode(value ?? '')}
                  onMount={onEditorMount}
                  options={{
                    automaticLayout: true,
                    minimap: { enabled: false },
                    fontSize: 14,
                    lineHeight: 23,
                    fontFamily: 'IBM Plex Mono, Consolas, monospace',
                    padding: { top: 20, bottom: 20 },
                    scrollBeyondLastLine: false,
                    renderLineHighlight: 'gutter',
                    cursorBlinking: 'smooth',
                    smoothScrolling: true,
                    wordWrap: 'on',
                    tabSize: 4,
                    theme: 'vs-dark',
                  }}
                />
              </div>
              <div className="editor-status"><span>Ln {editorRef.current?.getPosition()?.lineNumber || 1}, Col {editorRef.current?.getPosition()?.column || 1}</span><span>UTF-8</span><span>{editorLanguage}</span><span className="editor-status-right"><Activity size={13} /> INPUT LATENCY TARGET &lt; 16MS</span></div>
            </div>
            <div className="session-footnote"><span><FileAudio2 size={14} /> Audio is aligned to the same session clock as code edits.</span><span>{online ? <Wifi size={14} /> : <WifiOff size={14} />}{online ? 'Connection stable' : 'Reconnecting automatically'}</span></div>
          </section>
        )}

        {screen === 'processing' && (
          <section className="processing-view page-enter">
            <div className="processing-art"><div className="processing-ring ring-a" /><div className="processing-ring ring-b" /><div className="processing-core"><Activity size={31} /></div></div>
            <p className="eyebrow"><span className="live-dot" /> SESSION {session?.session_id?.slice(0, 8).toUpperCase()}</p>
            <h1>{offlineSubmit ? 'Waiting for your signal.' : 'Reading the room.'}</h1>
            <p>{offlineSubmit ? 'Your audio and code are safely queued on this device. Processing will begin when the connection returns.' : 'Code changes and spoken notes are being aligned into one review.'}</p>
            <div className="processing-steps"><span className="step-active"><i />Aligning timeline</span><span><i />Checking domain rubric</span><span><i />Building session report</span></div>
            {outboxSize > 0 && <span className="queued-label"><ArrowDownToLine size={14} /> {outboxSize} events waiting to sync</span>}
          </section>
        )}

        {screen === 'completed' && report && (
          <section className="review-view page-enter">
            <div className="review-heading"><div><p className="eyebrow">SESSION REVIEW <span className="heading-slash">/</span> {selectedDomain?.name} / {selectedDomain?.subtrack}</p><h1>A record of your reasoning.</h1></div><a className="download-button" href={`/api/session/${session.session_id}/download-card`} download><Download size={15} /> Share card</a></div>
            <div className="review-summary">
              <div className="score-block"><div className="score-ring" style={{ '--score': `${report.communication_score || 0}%` }}><div><strong>{report.communication_score ?? '—'}</strong><span> / 100</span></div></div><div><p className="eyebrow">COMMUNICATION SCORE</p><h2>{report.structural_classification === 'STRATEGIC_THINKER' ? 'Strategic thinker' : report.structural_classification === 'SYNTAX_NARRATOR' ? 'Syntax narrator' : 'Not enough speech'}</h2><p>{report.critique_summary}</p></div></div>
              <div className="summary-metrics"><div><span>WORDS SPOKEN</span><strong>{report.interaction_metrics?.spoken_words ?? 0}</strong><small>{report.interaction_metrics?.words_per_minute ?? 0} / MIN</small></div><div><span>CHARS TYPED</span><strong>{report.interaction_metrics?.characters_typed ?? 0}</strong><small>{report.interaction_metrics?.characters_per_minute ?? 0} / MIN</small></div><div><span>DEAD AIR FLAGS</span><strong>{report.interaction_metrics?.dead_air_flags?.length ?? 0}</strong><small>OVER 12 SECONDS</small></div><div><span>HINT PENALTY</span><strong>-{contestReport?.hint_penalty_points ?? 0}</strong><small>{contestReport?.hints_used ?? 0} HINTS / 90 MIN</small></div></div>
            </div>

            <div className="review-grid">
              <section className="timeline-panel">
                <div className="panel-heading"><div><p className="eyebrow">SESSION TAPE</p><h2>Code & conversation</h2></div><div className="chart-legend"><span><i className="legend-code" />Code</span><span><i className="legend-speech" />Speech</span></div></div>
                <div className="chart-wrap">
                  {chartData.length ? <ResponsiveContainer width="100%" height="100%"><ScatterChart margin={{ top: 12, right: 12, bottom: 4, left: -18 }} onClick={(event) => { if (event?.activePayload?.[0]?.payload) jumpToEvent(event.activePayload[0].payload) }}>
                    <CartesianGrid stroke="#d8ddd5" vertical={false} strokeDasharray="3 5" />
                    <XAxis dataKey="seconds" type="number" name="Time" tickFormatter={(value) => { const seconds = Math.floor(value); return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}` }} stroke="#748078" tickLine={false} axisLine={false} fontSize={11} />
                    <YAxis dataKey="lane" type="number" domain={[-0.7, 1.35]} ticks={[-0.5, 0, 1]} tickFormatter={(value) => value === 1 ? 'CODE' : value === -0.5 ? 'HINT' : 'VOICE'} stroke="#748078" tickLine={false} axisLine={false} fontSize={10} />
                    <Tooltip cursor={{ strokeDasharray: '3 3' }} content={({ active, payload }) => active && payload?.length ? <div className="chart-tooltip"><b>{formatTime(payload[0].payload.session_timestamp_ms)}</b><span>{payload[0].payload.event_type === 'CODE_MUTATION' ? 'Code mutation' : payload[0].payload.event_type === 'HINT_USED' ? 'Hint revealed' : payload[0].payload.word}</span></div> : null} />
                    <Scatter data={chartData} shape={(props) => <circle cx={props.cx} cy={props.cy} r={props.payload.event_type === 'CODE_MUTATION' ? 4 : 3} fill={props.payload.event_type === 'CODE_MUTATION' ? '#d95d39' : props.payload.event_type === 'SILENCE_GAP' || props.payload.event_type === 'HINT_USED' ? '#c08a36' : '#277267'} stroke="none" cursor="pointer" />} />
                  </ScatterChart></ResponsiveContainer> : <div className="empty-chart"><Radio size={20} /><span>No timeline events were captured.</span></div>}
                </div>
                <div className="event-list">
                  {timeline.slice(0, 8).map((event, index) => <button key={`${event.event_type}-${event.session_timestamp_ms}-${index}`} className={`event-row ${selectedEvent?.event_type === event.event_type && selectedEvent?.session_timestamp_ms === event.session_timestamp_ms ? 'selected' : ''}`} onClick={() => jumpToEvent(event)}><span className={`event-marker ${event.event_type === 'CODE_MUTATION' ? 'code-marker' : 'speech-marker'}`} /><time>{formatTime(event.session_timestamp_ms)}</time><span className="event-label">{event.event_type === 'CODE_MUTATION' ? `Code edit · line ${event.data?.change_range?.start_line || '—'}` : event.event_type === 'SILENCE_GAP' ? 'Silence without a code edit' : event.event_type === 'HINT_USED' ? `Hint ${event.data?.hint_index || ''} revealed` : `“${event.word}”`}</span>{event.silence_warning && <span className="silence-tag">{Math.round(event.gap_duration_ms / 1000)}s quiet</span>}</button>)}
                  {timeline.length > 8 && <span className="event-overflow">+ {timeline.length - 8} more events in the chart</span>}
                </div>
              </section>

              <div className="review-side">
                <section className="rubric-panel"><div className="panel-heading"><div><p className="eyebrow">EXPECTATIONS MATRIX</p><h2>Domain signals</h2></div><span className="rubric-domain">{selectedDomain?.subtrack}</span></div>
                  <div className="rubric-list">{(report.rubric || []).map((item, index) => <div className="rubric-item" key={`${item.expectation}-${index}`}><span className={`rubric-check ${item.met ? 'met' : ''}`}>{item.met ? <Check size={13} /> : <span />}</span><div><strong>{item.expectation}</strong><small>{item.evidence}</small></div></div>)}</div>
                  <div className="assumption-flag"><span>{report.assumption_validation ? 'YES' : 'NOT OBSERVED'}</span><div><strong>Assumptions stated up front</strong><small>Based on the available transcript</small></div></div>
                  {(report.evaluation_flags || []).length > 0 && <div className="evaluation-flags"><p className="eyebrow">EVALUATION FLAGS</p>{report.evaluation_flags.map((flag, index) => <div className="evaluation-flag" key={`${flag.code}-${index}`}><span>{flag.code}</span><strong>{flag.title}</strong><small>{flag.phase ? `${flag.phase} / ` : ''}{flag.detail}</small></div>)}</div>}
                </section>
                {codeguruReview && <section className="codeguru-panel"><div className="panel-heading"><div><p className="eyebrow">CODEGURU-STYLE REVIEW</p><h2>Engineering signals</h2></div><span className="rubric-domain">{codeguruReview.language?.toUpperCase()}</span></div><div className="codeguru-parser"><span>{codeguruReview.parser?.name}</span><span>{codeguruReview.parser?.status?.replace('_', ' ')}</span><small>{codeguruReview.parser?.evidence?.join(' ') || 'No parser evidence available.'}</small></div>{(codeguruReview.areas || []).map((area) => <div className="codeguru-area" key={area.key}><div><strong>{area.label}</strong><span className={`quality-status ${area.status}`}>{area.status.replace('_', ' ')}</span></div><p>{area.evidence.join(' ') || area.guidance}</p></div>)}<p className="codeguru-note">Static signals are coaching prompts, not correctness verdicts.</p></section>}
                {contestReport && <section className="contest-panel"><div className="panel-heading"><div><p className="eyebrow">ROUND SIMULATION</p><h2>Cadence & constraints</h2></div><span className="rubric-domain">90 MIN</span></div><div className="contest-stats"><span>{formatTime(contestReport.time_remaining_ms || 0)}<small>TIME REMAINING</small></span><span>{contestReport.complexity_spikes}<small>COMPLEXITY SPIKES</small></span><span>{contestReport.spoken_words_per_minute}<small>WORDS / MIN</small></span></div>{contestReport.cadence_flags?.map((flag, index) => <p className="contest-flag" key={`${flag.code}-${index}`}>{flag.detail}</p>)}</section>}
                <section className="code-review-panel"><div className="panel-heading"><div><p className="eyebrow">FINAL DRAFT</p><h2>Code snapshot</h2></div><span className="code-language-tag">{editorLanguage.toUpperCase()}</span></div>
                  <Editor height="250px" language={editorLanguage} value={code} onMount={(editor) => { editorRef.current = editor }} options={{ readOnly: true, minimap: { enabled: false }, fontSize: 12, lineHeight: 20, fontFamily: 'IBM Plex Mono, Consolas, monospace', padding: { top: 12 }, scrollBeyondLastLine: false, automaticLayout: true, wordWrap: 'on', theme: 'vs-dark', domReadOnly: true }} />
                </section>
              </div>
            </div>
            <div className="review-bottom"><span><span className="success-dot" /> REVIEW READY <span className="heading-slash">/</span> {report.evaluator}</span><button className="text-button" onClick={resetStudio}><RotateCcw size={14} /> New practice session</button></div>
          </section>
        )}

        {screen === 'failed' && (
          <section className="processing-view failed-view page-enter"><div className="failed-mark"><SignalLow size={25} /></div><p className="eyebrow">SESSION CAPTURED</p><h1>Review couldn't finish.</h1><p>{error || 'The worker could not process this session.'} Check that the backend, Redis, and Ollama are available, then start a new session.</p><button className="primary-button" onClick={resetStudio}>Back to setup <ArrowLeft size={16} /></button></section>
        )}
      </main>
    </div>
  )
}

export default App