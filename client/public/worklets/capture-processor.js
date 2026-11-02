const FRAME_SAMPLES = 320
const TARGET_SAMPLE_RATE = 16000

class CaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super()
    this.pendingInput = []
    this.pendingOutput = []
    this.readPosition = 0
    this.resampleStep = sampleRate / TARGET_SAMPLE_RATE
  }

  process(inputs) {
    const input = inputs[0]
    if (!input || input.length === 0) {
      return true
    }

    const channelData = input[0]
    if (!channelData) {
      return true
    }

    for (let index = 0; index < channelData.length; index += 1) {
      this.pendingInput.push(channelData[index])
    }

    if (this.resampleStep === 1) {
      for (let index = 0; index < this.pendingInput.length; index += 1) {
        this.pendingOutput.push(this.pendingInput[index])
      }
      this.pendingInput = []
      this.readPosition = 0
    } else {
      while (this.readPosition + 1 < this.pendingInput.length) {
        const leftIndex = Math.floor(this.readPosition)
        const rightIndex = leftIndex + 1
        const fraction = this.readPosition - leftIndex
        const left = this.pendingInput[leftIndex]
        const right = this.pendingInput[rightIndex]
        const interpolated = left + (right - left) * fraction
        this.pendingOutput.push(interpolated)
        this.readPosition += this.resampleStep
      }

      const consumed = Math.floor(this.readPosition)
      if (consumed > 0) {
        this.pendingInput.splice(0, consumed)
        this.readPosition -= consumed
      }
    }

    while (this.pendingOutput.length >= FRAME_SAMPLES) {
      const samples = this.pendingOutput.splice(0, FRAME_SAMPLES)
      const frame = new Uint8Array(FRAME_SAMPLES * 2)
      const view = new DataView(frame.buffer)

      for (let sampleIndex = 0; sampleIndex < samples.length; sampleIndex += 1) {
        const clamped = Math.max(-1, Math.min(1, samples[sampleIndex]))
        const int16 = clamped < 0 ? Math.round(clamped * 0x8000) : Math.round(clamped * 0x7fff)
        view.setInt16(sampleIndex * 2, int16, true)
      }

      this.port.postMessage({ type: 'frame', frame: frame.buffer }, [frame.buffer])
    }

    return true
  }
}

registerProcessor('capture-processor', CaptureProcessor)
