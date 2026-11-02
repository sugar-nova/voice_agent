export const UPLINK_SAMPLE_RATE = 16_000
export const UPLINK_CHANNELS = 1
export const UPLINK_BITS_PER_SAMPLE = 16
export const UPLINK_FRAME_BYTES = 640

// Downlink audio from server TTS is expected at 24 kHz PCM16 mono.
export const DOWNLINK_SAMPLE_RATE = 24_000
export const DOWNLINK_CHANNELS = 1
export const DOWNLINK_BITS_PER_SAMPLE = 16

export type StartMessage = {
  type: 'start'
  sampleRate: number
}

export type StopMessage = {
  type: 'stop'
}

export type PingMessage = {
  type: 'ping'
  pingId: string
  sentAtMs: number
}

export type PlaybackStartedMessage = {
  type: 'playback_started'
  turnId: number
  playedAtMs: number
}

export type PongMessage = {
  type: 'pong'
  pingId: string
  sentAtMs: number
  rttMs?: number
}

export type TranscriptEvent = {
  type: 'transcript'
  text: string
  final: boolean
}

export type AgentTextEvent = {
  type: 'agent_text'
  text: string
}

export type ReadyEvent = {
  type: 'ready'
}

export type InterruptEvent = {
  type: 'interrupt'
}

export type MetricsEvent = {
  type: 'metrics'
  turnId: number
  stages: Record<string, number | undefined>
  vad_silence_ms?: number
  extra?: MetricsExtra
}

export type BrainMetricsEvent = {
  route: 'l1_hit' | 'l2_rag' | 'deflect'
  embed_ms: number
  redis_knn_ms: number
  redis_similarity?: number | null
  qdrant_search_ms?: number | null
  llm_first_token_ms?: number | null
  brain_ms: number
}

export type MetricsExtra = {
  clientPlayedAtMs?: number
  brain?: BrainMetricsEvent
  [key: string]: unknown
}

export type ErrorEvent = {
  type: 'error'
  message: string
}

export type ClientControlMessage = StartMessage | StopMessage | PingMessage | PlaybackStartedMessage

export type ServerEventMessage =
  | ReadyEvent
  | TranscriptEvent
  | AgentTextEvent
  | InterruptEvent
  | MetricsEvent
  | ErrorEvent
  | PongMessage
