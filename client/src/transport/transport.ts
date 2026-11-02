import type { ServerEventMessage } from './types'

export type AudioHandler = (chunk: Uint8Array) => void
export type EventHandler = (event: ServerEventMessage) => void
export type DisconnectInfo = { attempt: number; delayMs: number }
export type DisconnectHandler = (info: DisconnectInfo) => void

export interface Transport {
  connect(url: string): Promise<void>
  sendAudio(chunk: Uint8Array): void
  onAudio(handler: AudioHandler): () => void
  onEvent(handler: EventHandler): () => void
  onDisconnect(handler: DisconnectHandler): () => void
  close(): void
}
