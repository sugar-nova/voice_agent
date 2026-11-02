import type {
  DisconnectHandler,
  EventHandler,
  AudioHandler,
  Transport,
} from './transport'
import {
  UPLINK_SAMPLE_RATE,
  type ClientControlMessage,
  type PongMessage,
  type ServerEventMessage,
} from './types'

type WebSocketTransportOptions = {
  pingIntervalMs?: number
  reconnectInitialDelayMs?: number
  reconnectMaxDelayMs?: number
}

const DEFAULT_PING_INTERVAL_MS = 5000
const DEFAULT_RECONNECT_INITIAL_DELAY_MS = 1500
const DEFAULT_RECONNECT_MAX_DELAY_MS = 8000

export class WebSocketTransport implements Transport {
  private socket: WebSocket | null = null
  private readonly pingIntervalMs: number
  private readonly reconnectInitialDelayMs: number
  private readonly reconnectMaxDelayMs: number
  private pingTimer: number | null = null
  private reconnectTimer: number | null = null
  private audioHandlers: AudioHandler[] = []
  private eventHandlers: EventHandler[] = []
  private disconnectHandlers: DisconnectHandler[] = []
  private shouldReconnect = false
  private connectUrl: string | null = null
  private reconnectAttempt = 0

  constructor(options: WebSocketTransportOptions = {}) {
    this.pingIntervalMs = options.pingIntervalMs ?? DEFAULT_PING_INTERVAL_MS
    this.reconnectInitialDelayMs =
      options.reconnectInitialDelayMs ?? DEFAULT_RECONNECT_INITIAL_DELAY_MS
    this.reconnectMaxDelayMs = options.reconnectMaxDelayMs ?? DEFAULT_RECONNECT_MAX_DELAY_MS
  }

  connect(url: string): Promise<void> {
    if (this.socket || this.reconnectTimer !== null) {
      throw new Error('WebSocketTransport is already connected')
    }

    this.shouldReconnect = true
    this.connectUrl = url
    this.reconnectAttempt = 0
    return this.openSocket(url, true)
  }

  sendAudio(chunk: Uint8Array): void {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      return
    }
    const copy = Uint8Array.from(chunk)
    this.socket.send(copy.buffer)
  }

  onAudio(handler: AudioHandler): () => void {
    this.audioHandlers.push(handler)
    return () => {
      this.audioHandlers = this.audioHandlers.filter((current) => current !== handler)
    }
  }

  onEvent(handler: EventHandler): () => void {
    this.eventHandlers.push(handler)
    return () => {
      this.eventHandlers = this.eventHandlers.filter((current) => current !== handler)
    }
  }

  onDisconnect(handler: DisconnectHandler): () => void {
    this.disconnectHandlers.push(handler)
    return () => {
      this.disconnectHandlers = this.disconnectHandlers.filter((current) => current !== handler)
    }
  }

  close(): void {
    this.shouldReconnect = false
    this.connectUrl = null
    this.reconnectAttempt = 0
    this.stopReconnectLoop()

    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.sendControl({ type: 'stop' })
    }

    this.stopPingLoop()
    this.socket?.close()
    this.socket = null
  }

  sendClientEvent(message: ClientControlMessage): void {
    this.sendControl(message)
  }

  private startPingLoop(): void {
    this.stopPingLoop()
    this.pingTimer = globalThis.setInterval(() => {
      if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
        return
      }

      const sentAtMs = Date.now()
      this.sendControl({
        type: 'ping',
        pingId: String(sentAtMs),
        sentAtMs,
      })
    }, this.pingIntervalMs)
  }

  private stopPingLoop(): void {
    if (this.pingTimer === null) {
      return
    }
    globalThis.clearInterval(this.pingTimer)
    this.pingTimer = null
  }

  private stopReconnectLoop(): void {
    if (this.reconnectTimer === null) {
      return
    }
    globalThis.clearTimeout(this.reconnectTimer)
    this.reconnectTimer = null
  }

  private openSocket(url: string, isInitial: boolean): Promise<void> {
    const socket = new WebSocket(url)
    socket.binaryType = 'arraybuffer'
    this.socket = socket

    return new Promise((resolve, reject) => {
      let settled = false

      socket.addEventListener('open', () => {
        if (this.socket !== socket) {
          return
        }
        this.reconnectAttempt = 0
        this.sendControl({ type: 'start', sampleRate: UPLINK_SAMPLE_RATE })
        this.startPingLoop()
        if (!settled) {
          settled = true
          resolve()
        }
      })

      socket.addEventListener('error', () => {
        if (isInitial && !settled) {
          settled = true
          reject(new Error('WebSocket connection failed'))
        }
      })

      socket.addEventListener('close', () => {
        if (this.socket === socket) {
          this.stopPingLoop()
          this.socket = null
        }
        if (isInitial && !settled) {
          settled = true
          reject(new Error('WebSocket connection closed before ready'))
        }
        if (!this.shouldReconnect) {
          return
        }
        this.scheduleReconnect()
      })

      socket.addEventListener('message', (event) => {
        void this.handleMessage(event.data)
      })
    })
  }

  private scheduleReconnect(): void {
    if (!this.connectUrl || this.reconnectTimer !== null || this.socket) {
      return
    }
    const attempt = this.reconnectAttempt + 1
    const delayMs = Math.min(
      this.reconnectMaxDelayMs,
      this.reconnectInitialDelayMs * 2 ** (attempt - 1),
    )
    this.reconnectAttempt = attempt
    this.notifyDisconnectHandlers({ attempt, delayMs })
    this.reconnectTimer = globalThis.setTimeout(() => {
      this.reconnectTimer = null
      if (!this.shouldReconnect || !this.connectUrl || this.socket) {
        return
      }
      void this.openSocket(this.connectUrl, false)
    }, delayMs)
  }

  private notifyDisconnectHandlers(info: { attempt: number; delayMs: number }): void {
    for (const handler of this.disconnectHandlers) {
      handler(info)
    }
  }

  private sendControl(message: ClientControlMessage): void {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      return
    }
    this.socket.send(JSON.stringify(message))
  }

  private async handleMessage(data: unknown): Promise<void> {
    if (data instanceof ArrayBuffer) {
      this.dispatchAudio(new Uint8Array(data))
      return
    }

    if (data instanceof Blob) {
      const buffer = await data.arrayBuffer()
      this.dispatchAudio(new Uint8Array(buffer))
      return
    }

    if (typeof data !== 'string') {
      return
    }

    let parsed: ServerEventMessage
    try {
      parsed = JSON.parse(data) as ServerEventMessage
    } catch {
      console.warn('[transport] Ignored malformed JSON event')
      return
    }

    if (parsed.type === 'pong') {
      this.handlePong(parsed)
      return
    }

    this.dispatchEvent(parsed)
  }

  private handlePong(pong: PongMessage): void {
    const rttMs = Math.max(0, Date.now() - pong.sentAtMs)
    const enrichedPong: PongMessage = {
      ...pong,
      rttMs,
    }
    console.info(`[transport] RTT estimate ${rttMs} ms`)
    this.dispatchEvent(enrichedPong)
  }

  private dispatchAudio(chunk: Uint8Array): void {
    for (const handler of this.audioHandlers) {
      handler(chunk)
    }
  }

  private dispatchEvent(event: ServerEventMessage): void {
    for (const handler of this.eventHandlers) {
      handler(event)
    }
  }
}
