import {
  PLAYBACK_TARGET_BUFFER_MS,
  TARGET_SAMPLE_RATE,
} from './constants'
import { DOWNLINK_SAMPLE_RATE } from '../transport/types'

type PlaybackMetrics = {
  underruns: number
  bufferedSamples: number
}

type FirstSampleEvent = {
  contextTimeSeconds: number
}

type PlaybackCallbacks = {
  onMetrics: (metrics: PlaybackMetrics) => void
  onFirstSamplePlayed: (event: FirstSampleEvent) => void
}

export type PlaybackSession = {
  enqueueFrame: (frame: Uint8Array) => void
  flush: () => void
  stop: () => void
}

type PlaybackMessage =
  | { type: 'underrun'; underruns: number; bufferedSamples: number }
  | { type: 'first_sample_played'; contextTimeSeconds: number }

export async function startPlayback(
  audioContext: AudioContext,
  callbacks: PlaybackCallbacks,
): Promise<PlaybackSession> {
  await audioContext.audioWorklet.addModule('/worklets/playback-processor.js')
  const playbackNode = new AudioWorkletNode(audioContext, 'playback-processor')
  const gainNode = audioContext.createGain()
  gainNode.gain.value = 1

  playbackNode.connect(gainNode)
  gainNode.connect(audioContext.destination)

  playbackNode.port.postMessage({
    type: 'set_target_buffer_ms',
    value: PLAYBACK_TARGET_BUFFER_MS,
  })
  playbackNode.port.postMessage({
    type: 'set_input_sample_rate',
    value: DOWNLINK_SAMPLE_RATE,
  })

  playbackNode.port.onmessage = (event: MessageEvent<PlaybackMessage>) => {
    if (event.data.type === 'underrun') {
      callbacks.onMetrics({
        underruns: event.data.underruns,
        bufferedSamples: event.data.bufferedSamples,
      })
      return
    }

    if (event.data.type === 'first_sample_played') {
      callbacks.onFirstSamplePlayed({
        contextTimeSeconds: event.data.contextTimeSeconds,
      })
    }
  }

  if (audioContext.sampleRate !== TARGET_SAMPLE_RATE) {
    console.warn(
      `[audio] Playback context at ${audioContext.sampleRate} Hz; expected ${TARGET_SAMPLE_RATE} Hz target.`,
    )
  }

  return {
    enqueueFrame: (frame: Uint8Array) => {
      const copy = Uint8Array.from(frame)
      playbackNode.port.postMessage({ type: 'enqueue', frame: copy.buffer })
    },
    flush: () => {
      playbackNode.port.postMessage({ type: 'flush' })
    },
    stop: () => {
      playbackNode.disconnect()
      gainNode.disconnect()
      playbackNode.port.close()
    },
  }
}
