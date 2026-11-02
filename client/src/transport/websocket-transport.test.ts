import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { WebSocketTransport } from './websocket-transport'

type MessageListener = (event: { data: unknown }) => void
type EventListener = () => void

class MockWebSocket {
  static readonly CONNECTING = 0
  static readonly OPEN = 1
  static readonly CLOSING = 2
  static readonly CLOSED = 3
  static instances: MockWebSocket[] = []

  readonly url: string
  readyState = MockWebSocket.CONNECTING
  binaryType = 'blob'
  sentPayloads: unknown[] = []

  private openListeners: EventListener[] = []
  private closeListeners: EventListener[] = []
  private errorListeners: EventListener[] = []
  private messageListeners: MessageListener[] = []

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }

  addEventListener(type: string, handler: EventListener | MessageListener): void {
    if (type === 'open') {
      this.openListeners.push(handler as EventListener)
      return
    }
    if (type === 'close') {
      this.closeListeners.push(handler as EventListener)
      return
    }
    if (type === 'error') {
      this.errorListeners.push(handler as EventListener)
      return
    }
    if (type === 'message') {
      this.messageListeners.push(handler as MessageListener)
    }
  }

  send(payload: unknown): void {
    this.sentPayloads.push(payload)
  }

  close(): void {
    this.readyState = MockWebSocket.CLOSED
    for (const listener of this.closeListeners) {
      listener()
    }
  }

  emitOpen(): void {
    this.readyState = MockWebSocket.OPEN
    for (const listener of this.openListeners) {
      listener()
    }
  }

  emitError(): void {
    for (const listener of this.errorListeners) {
      listener()
    }
  }

  emitMessage(data: unknown): void {
    for (const listener of this.messageListeners) {
      listener({ data })
    }
  }
}

describe('WebSocketTransport', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    vi.useFakeTimers()
    vi.stubGlobal('WebSocket', MockWebSocket)
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('connects, sends start, and forwards binary audio/events', async () => {
    const transport = new WebSocketTransport({ pingIntervalMs: 2000 })
    const audioHandler = vi.fn()
    const eventHandler = vi.fn()
    transport.onAudio(audioHandler)
    transport.onEvent(eventHandler)

    const connectPromise = transport.connect('ws://localhost:9000/ws')
    const socket = MockWebSocket.instances[0]
    socket.emitOpen()
    await connectPromise

    expect(typeof socket.sentPayloads[0]).toBe('string')
    expect(JSON.parse(socket.sentPayloads[0] as string)).toEqual({
      type: 'start',
      sampleRate: 16000,
    })

    const audioChunk = new Uint8Array([1, 2, 3, 4])
    transport.sendAudio(audioChunk)
    expect(Array.from(new Uint8Array(socket.sentPayloads[1] as ArrayBuffer))).toEqual([1, 2, 3, 4])

    const downlinkChunk = new Uint8Array([9, 8, 7]).buffer
    socket.emitMessage(downlinkChunk)
    expect(audioHandler).toHaveBeenCalledWith(new Uint8Array([9, 8, 7]))

    socket.emitMessage(JSON.stringify({ type: 'transcript', text: 'hello', final: true }))
    expect(eventHandler).toHaveBeenCalledWith({
      type: 'transcript',
      text: 'hello',
      final: true,
    })
  })

  it('sends stop on close and emits RTT on pong', async () => {
    const infoSpy = vi.spyOn(console, 'info').mockImplementation(() => {})
    const transport = new WebSocketTransport({ pingIntervalMs: 1000 })
    const eventHandler = vi.fn()
    transport.onEvent(eventHandler)

    const connectPromise = transport.connect('ws://localhost:9000/ws')
    const socket = MockWebSocket.instances[0]
    socket.emitOpen()
    await connectPromise

    vi.setSystemTime(new Date('2026-11-02T10:00:00.000Z'))
    vi.advanceTimersByTime(1000)

    const pingMessage = JSON.parse(socket.sentPayloads[1] as string) as {
      type: string
      pingId: string
      sentAtMs: number
    }
    expect(pingMessage.type).toBe('ping')

    vi.setSystemTime(new Date('2026-11-02T10:00:01.075Z'))
    socket.emitMessage(
      JSON.stringify({
        type: 'pong',
        pingId: pingMessage.pingId,
        sentAtMs: pingMessage.sentAtMs,
      }),
    )

    expect(infoSpy).toHaveBeenCalledWith('[transport] RTT estimate 75 ms')
    expect(eventHandler).toHaveBeenCalledWith({
      type: 'pong',
      pingId: pingMessage.pingId,
      sentAtMs: pingMessage.sentAtMs,
      rttMs: 75,
    })

    transport.close()
    expect(JSON.parse(socket.sentPayloads.at(-1) as string)).toEqual({ type: 'stop' })
  })

  it('rejects connect promise on websocket error', async () => {
    const transport = new WebSocketTransport()
    const connectPromise = transport.connect('ws://localhost:9000/ws')
    const socket = MockWebSocket.instances[0]
    socket.emitError()
    await expect(connectPromise).rejects.toThrow('WebSocket connection failed')
  })

  it('auto-reconnects with backoff and resends start', async () => {
    const transport = new WebSocketTransport({
      reconnectInitialDelayMs: 1000,
      reconnectMaxDelayMs: 4000,
    })
    const disconnectHandler = vi.fn()
    transport.onDisconnect(disconnectHandler)

    const connectPromise = transport.connect('ws://localhost:9000/ws')
    const firstSocket = MockWebSocket.instances[0]
    firstSocket.emitOpen()
    await connectPromise

    firstSocket.close()
    expect(disconnectHandler).toHaveBeenCalledWith({ attempt: 1, delayMs: 1000 })

    vi.advanceTimersByTime(1000)
    expect(MockWebSocket.instances).toHaveLength(2)
    const secondSocket = MockWebSocket.instances[1]
    secondSocket.emitOpen()

    expect(JSON.parse(secondSocket.sentPayloads[0] as string)).toEqual({
      type: 'start',
      sampleRate: 16000,
    })
  })
})
