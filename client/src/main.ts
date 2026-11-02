import './style.css'
import { startCapture, type CaptureSession } from './audio/capture'
import { getMicrophoneStream } from './audio/mic'
import { startPlayback, type PlaybackSession } from './audio/playback'
import { WebSocketTransport } from './transport/websocket-transport'
import type { MetricsEvent, ServerEventMessage } from './transport/types'

document.querySelector<HTMLDivElement>('#app')!.innerHTML = `
  <main>
    <h1>Voice Agent</h1>
    <p class="subtitle">Microphone in, spoken reply out, over a WebSocket</p>

    <section class="panel">
      <button id="session-toggle" type="button">Connect</button>
      <div class="kv"><span>State</span><strong id="state-value">idle</strong></div>
      <div class="kv"><span>Mic</span><strong id="mic-value">inactive</strong></div>
      <div class="kv"><span>Status</span><strong id="status-value">Idle</strong></div>
      <div class="kv"><span>Frames</span><strong id="frames-value">0</strong></div>
      <div class="kv"><span>Bytes</span><strong id="bytes-value">0</strong></div>
      <div class="kv"><span>Underruns</span><strong id="underruns-value">0</strong></div>
      <div class="kv"><span>RTT</span><strong id="rtt-value">-</strong></div>
    </section>

    <section class="panel">
      <h2>Transcript</h2>
      <p id="transcript-interim">Interim: -</p>
      <p id="transcript-final">Final: -</p>
    </section>

    <section class="panel">
      <h2>Latency / Metrics</h2>
      <pre id="metrics-value">Waiting for metrics...</pre>
    </section>
  </main>
`

const sessionButton = document.querySelector<HTMLButtonElement>('#session-toggle')
const stateValue = document.querySelector<HTMLElement>('#state-value')
const micValue = document.querySelector<HTMLElement>('#mic-value')
const statusValue = document.querySelector<HTMLElement>('#status-value')
const framesValue = document.querySelector<HTMLElement>('#frames-value')
const bytesValue = document.querySelector<HTMLElement>('#bytes-value')
const underrunsValue = document.querySelector<HTMLElement>('#underruns-value')
const rttValue = document.querySelector<HTMLElement>('#rtt-value')
const transcriptInterim = document.querySelector<HTMLParagraphElement>('#transcript-interim')
const transcriptFinal = document.querySelector<HTMLParagraphElement>('#transcript-final')
const metricsValue = document.querySelector<HTMLPreElement>('#metrics-value')

if (
  !sessionButton ||
  !stateValue ||
  !micValue ||
  !statusValue ||
  !framesValue ||
  !bytesValue ||
  !underrunsValue ||
  !rttValue ||
  !transcriptInterim ||
  !transcriptFinal ||
  !metricsValue
) {
  throw new Error('App failed to initialize capture controls')
}

type SessionState = 'idle' | 'connecting' | 'listening' | 'agent_speaking' | 'error'

let stream: MediaStream | null = null
let captureSession: CaptureSession | null = null
let playbackSession: PlaybackSession | null = null
let transport: WebSocketTransport | null = null
let state: SessionState = 'idle'
let receivedFrames = 0
let receivedBytes = 0
let totalUnderruns = 0
let lastRttMs: number | null = null
let latestMetricsTurnId = 0
let currentPlaybackTurnId: number | null = null
const sessionButtonElement = sessionButton
const transcriptInterimElement = transcriptInterim
const transcriptFinalElement = transcriptFinal
const metricsValueElement = metricsValue

const setStatus = (text: string) => {
  statusValue.textContent = text
}

const setState = (next: SessionState) => {
  state = next
  stateValue.textContent = next
  console.info(`[session] state=${next}`)
}

const setMicStatus = (value: 'inactive' | 'active' | 'error') => {
  micValue.textContent = value
}

const setStats = (): void => {
  framesValue.textContent = String(receivedFrames)
  bytesValue.textContent = String(receivedBytes)
  underrunsValue.textContent = String(totalUnderruns)
  rttValue.textContent = lastRttMs === null ? '-' : `${lastRttMs} ms`
}

const renderMetrics = (event: MetricsEvent): void => {
  const lines = [
    `turnId: ${event.turnId}`,
    `rttMs: ${lastRttMs ?? '-'}`,
    `t0: ${event.stages.t0 ?? '-'}`,
    `t1: ${event.stages.t1 ?? '-'}`,
    `t2: ${event.stages.t2 ?? '-'}`,
    `t3: ${event.stages.t3 ?? '-'}`,
    `t4: ${event.stages.t4 ?? '-'}`,
    `clientPlayedAtMs: ${String(event.extra?.clientPlayedAtMs ?? '-')}`,
  ]
  if (event.extra?.brain) {
    lines.push('', 'brain:', JSON.stringify(event.extra.brain, null, 2))
  }
  metricsValue.textContent = lines.join('\n')
}

const wsUrl = () => {
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${protocol}://${window.location.host}/ws`
}

const handleServerEvent = (event: ServerEventMessage) => {
  if (event.type === 'ready') {
    setState('listening')
    setStatus('Connected and listening')
    return
  }

  if (event.type === 'transcript') {
    if (event.final) {
      transcriptFinal.textContent = `Final: ${event.text}`
      transcriptInterim.textContent = 'Interim: -'
    } else {
      transcriptInterim.textContent = `Interim: ${event.text}`
    }
    return
  }

  if (event.type === 'agent_text') {
    setState('agent_speaking')
    setStatus(`Agent: ${event.text}`)
    currentPlaybackTurnId = latestMetricsTurnId + 1
    return
  }

  if (event.type === 'interrupt') {
    playbackSession?.flush()
    setState('listening')
    setStatus('Interrupted: playback flushed')
    return
  }

  if (event.type === 'metrics') {
    latestMetricsTurnId = event.turnId
    renderMetrics(event)
    setState('listening')
    return
  }

  if (event.type === 'pong') {
    if (typeof event.rttMs === 'number') {
      lastRttMs = event.rttMs
      setStats()
    }
    return
  }

  if (event.type === 'error') {
    setState('error')
    setStatus(`Server error: ${event.message}`)
  }
}

async function start(): Promise<void> {
  setState('connecting')
  setMicStatus('inactive')
  setStatus('Requesting microphone permission...')
  stream = await getMicrophoneStream()
  setMicStatus('active')
  const audioContext = new AudioContext()
  console.info(`[audio] Session AudioContext sampleRate=${audioContext.sampleRate}`)
  setStatus('Microphone active. Connecting WebSocket...')

  playbackSession = await startPlayback(audioContext, {
    onMetrics: ({ underruns }) => {
      totalUnderruns = underruns
      setStats()
    },
    onFirstSamplePlayed: ({ contextTimeSeconds }) => {
      console.info(`[playback] first sample played at contextTime=${contextTimeSeconds.toFixed(3)}s`)
      if (transport && currentPlaybackTurnId !== null) {
        transport.sendClientEvent({
          type: 'playback_started',
          turnId: currentPlaybackTurnId,
          playedAtMs: Date.now(),
        })
      }
    },
  })

  transport = new WebSocketTransport()
  transport.onDisconnect(({ attempt, delayMs }) => {
    setState('connecting')
    setStatus(`Connection dropped. Reconnecting in ${Math.round(delayMs / 1000)}s (attempt ${attempt})`)
  })
  transport.onAudio((chunk) => {
    playbackSession?.enqueueFrame(chunk)
  })
  transport.onEvent(handleServerEvent)
  await transport.connect(wsUrl())

  captureSession = await startCapture(stream, {
    onFrame: (frame: Uint8Array) => {
      transport?.sendAudio(frame)
    },
    onMetrics: ({ receivedFrames: frames, receivedBytes: bytes }) => {
      receivedFrames = frames
      receivedBytes = bytes
      setStats()
    },
  }, { audioContext })

  totalUnderruns = 0
  receivedFrames = 0
  receivedBytes = 0
  sessionButtonElement.textContent = 'Disconnect'
  setStats()
  setStatus('Connected. Streaming microphone uplink')
}

function stop(nextState: SessionState = 'idle'): void {
  transport?.close()
  transport = null

  if (captureSession) {
    captureSession.stop()
    captureSession.audioContext.close()
  }
  playbackSession?.flush()
  playbackSession?.stop()
  captureSession = null
  playbackSession = null

  if (stream) {
    for (const track of stream.getTracks()) {
      track.stop()
    }
  }
  stream = null

  sessionButtonElement.textContent = 'Connect'
  transcriptInterimElement.textContent = 'Interim: -'
  transcriptFinalElement.textContent = 'Final: -'
  metricsValueElement.textContent = 'Waiting for metrics...'
  setMicStatus('inactive')
  setState(nextState)
  if (nextState === 'idle') {
    setStatus('Idle')
  }
  totalUnderruns = 0
  receivedFrames = 0
  receivedBytes = 0
  lastRttMs = null
  currentPlaybackTurnId = null
  setStats()
}

sessionButtonElement.addEventListener('click', async () => {
  if (state !== 'idle') {
    stop()
    return
  }

  try {
    await start()
  } catch (error) {
    setStatus(`Session failed: ${String(error)}`)
    stop('error')
    setMicStatus('error')
  }
})
