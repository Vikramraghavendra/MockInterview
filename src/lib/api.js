const API_BASE = import.meta.env.VITE_API_BASE || ''

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options)
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.detail || `Request failed (${response.status})`)
  }
  return response.status === 204 ? null : response.json()
}

export const api = {
  domains: () => request('/api/domains'),
  startSession: (domainId) => request('/api/session/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ domain_id: domainId }),
  }),
  sendCodeEvent: (entry) => request('/api/session/code/event', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(entry),
  }),
  sendAudioChunk: (entry) => {
    const form = new FormData()
    form.append('session_id', entry.session_id)
    form.append('timestamp_ms', String(entry.timestamp_ms))
    form.append('chunk', entry.blob, `audio-${entry.timestamp_ms}.webm`)
    return request('/api/session/audio/chunk', { method: 'POST', body: form })
  },
  submitSession: (payload) => request('/api/session/submit', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }),
  getSession: (sessionId) => request(`/api/session/${sessionId}`),
}

export async function sendOutboxEntry(entry) {
  if (entry.kind === 'audio') return api.sendAudioChunk(entry)
  if (entry.kind === 'submit') return api.submitSession(entry.payload)
  return api.sendCodeEvent(entry.payload)
}