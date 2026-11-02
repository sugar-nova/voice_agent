import { FRAME_BYTES, TARGET_SAMPLE_RATE } from './constants'

type CaptureMetrics = {
  receivedFrames: number
  receivedBytes: number
}

type CaptureCallbacks = {
  onFrame: (frame: Uint8Array) => void
  onMetrics: (metrics: CaptureMetrics) => void
}

type CaptureOptions = {
  audioContext?: AudioContext
}

export type CaptureSession = {
  audioContext: AudioContext
  stop: () => void
}

export async function startCapture(
  stream: MediaStream,
  callbacks: CaptureCallbacks,
  options: CaptureOptions = {},
): Promise<CaptureSession> {
  const audioContext = options.audioContext ?? new AudioContext()
  const ownsAudioContext = !options.audioContext

  console.info(`[audio] Capture AudioContext sampleRate=${audioContext.sampleRate}`)

  if (audioContext.sampleRate !== TARGET_SAMPLE_RATE) {
    console.warn(
      `[audio] Expected ${TARGET_SAMPLE_RATE} Hz; current rate is ${audioContext.sampleRate} Hz. ` +
        'Resample plan: downsample on main thread before uplink in Milestone 3.',
    )
  }

  await audioContext.audioWorklet.addModule('/worklets/capture-processor.js')
  const sourceNode = audioContext.createMediaStreamSource(stream)
  const captureNode = new AudioWorkletNode(audioContext, 'capture-processor')
  const silentSink = audioContext.createGain()
  silentSink.gain.value = 0

  sourceNode.connect(captureNode)
  captureNode.connect(silentSink)
  silentSink.connect(audioContext.destination)

  let receivedFrames = 0
  let receivedBytes = 0

  captureNode.port.onmessage = (event: MessageEvent<{ type: string; frame?: ArrayBuffer }>) => {
    if (event.data.type !== 'frame' || !event.data.frame) {
      return
    }

    const frame = new Uint8Array(event.data.frame)
    if (frame.byteLength !== FRAME_BYTES) {
      console.warn(`[audio] Unexpected frame size ${frame.byteLength} bytes`)
      return
    }

    receivedFrames += 1
    receivedBytes += frame.byteLength
    callbacks.onFrame(frame)
    callbacks.onMetrics({ receivedFrames, receivedBytes })
  }

  return {
    audioContext,
    stop: () => {
      captureNode.disconnect()
      silentSink.disconnect()
      sourceNode.disconnect()
      captureNode.port.close()
      if (ownsAudioContext) {
        audioContext.close()
      }
    },
  }
}
