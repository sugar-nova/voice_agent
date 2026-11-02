class PlaybackProcessor extends AudioWorkletProcessor {
  constructor() {
    super()
    this.inputSampleRate = 24000
    // ~15 s at 48 kHz — full TTS utterances are much longer than the old ~0.7 s buffer.
    this.capacitySamples = Math.max(720000, Math.floor(sampleRate * 15))
    this.buffer = new Float32Array(this.capacitySamples)
    this.writeIndex = 0
    this.readIndex = 0
    this.samplesAvailable = 0
    this.targetBufferMs = 100
    this.targetBufferSamples = this.bufferSamplesForMs(this.targetBufferMs)
    this.started = false
    this.startupWaitSamples = 0
    this.underruns = 0
    this.firstSamplePending = true
    this.resampleInput = []
    this.resampleReadPosition = 0
    this.resampleStep = this.inputSampleRate / sampleRate

    this.port.onmessage = (event) => {
      if (!event.data || !event.data.type) {
        return
      }

      if (event.data.type === 'enqueue' && event.data.frame) {
        this.pushPcm16(new Uint8Array(event.data.frame))
        return
      }

      if (event.data.type === 'flush') {
        this.flush()
        return
      }

      if (event.data.type === 'set_target_buffer_ms') {
        this.targetBufferMs = Math.max(20, Math.floor(event.data.value))
        this.targetBufferSamples = this.bufferSamplesForMs(this.targetBufferMs)
        return
      }

      if (event.data.type === 'set_input_sample_rate') {
        this.inputSampleRate = Math.max(8000, Math.floor(event.data.value))
        this.resampleStep = this.inputSampleRate / sampleRate
      }
    }
  }

  bufferSamplesForMs(bufferMs) {
    return Math.max(1, Math.floor((sampleRate * bufferMs) / 1000))
  }

  flush() {
    this.writeIndex = 0
    this.readIndex = 0
    this.samplesAvailable = 0
    this.started = false
    this.startupWaitSamples = 0
    this.firstSamplePending = true
    this.resampleInput = []
    this.resampleReadPosition = 0
  }

  pushPcm16(frame) {
    const view = new DataView(frame.buffer, frame.byteOffset, frame.byteLength)
    const sampleCount = Math.floor(frame.byteLength / 2)
    const decoded = new Float32Array(sampleCount)

    for (let index = 0; index < sampleCount; index += 1) {
      const int16 = view.getInt16(index * 2, true)
      decoded[index] = int16 < 0 ? int16 / 0x8000 : int16 / 0x7fff
    }

    for (let index = 0; index < decoded.length; index += 1) {
      this.resampleInput.push(decoded[index])
    }

    if (this.resampleStep === 1) {
      for (let index = 0; index < this.resampleInput.length; index += 1) {
        this.pushSample(this.resampleInput[index])
      }
      this.resampleInput = []
      this.resampleReadPosition = 0
      return
    }

    while (this.resampleReadPosition + 1 < this.resampleInput.length) {
      const leftIndex = Math.floor(this.resampleReadPosition)
      const rightIndex = leftIndex + 1
      const fraction = this.resampleReadPosition - leftIndex
      const left = this.resampleInput[leftIndex]
      const right = this.resampleInput[rightIndex]
      const interpolated = left + (right - left) * fraction
      this.pushSample(interpolated)
      this.resampleReadPosition += this.resampleStep
    }

    const consumed = Math.floor(this.resampleReadPosition)
    if (consumed > 0) {
      this.resampleInput.splice(0, consumed)
      this.resampleReadPosition -= consumed
    }
  }

  pushSample(sample) {
    if (this.samplesAvailable === this.capacitySamples) {
      this.readIndex = (this.readIndex + 1) % this.capacitySamples
      this.samplesAvailable -= 1
    }

    this.buffer[this.writeIndex] = sample
    this.writeIndex = (this.writeIndex + 1) % this.capacitySamples
    this.samplesAvailable += 1
  }

  process(_inputs, outputs) {
    const output = outputs[0]
    if (!output || output.length === 0) {
      return true
    }

    const channel = output[0]
    if (!channel) {
      return true
    }

    channel.fill(0)

    if (!this.started) {
      if (this.samplesAvailable >= this.targetBufferSamples) {
        this.started = true
        this.startupWaitSamples = 0
      } else if (this.samplesAvailable > 0) {
        // Avoid one-turn delay on short utterances: after waiting ~200 ms,
        // start with whatever audio is buffered.
        this.startupWaitSamples += channel.length
        if (this.startupWaitSamples >= sampleRate * 0.2) {
          this.started = true
          this.startupWaitSamples = 0
        }
      } else {
        this.startupWaitSamples = 0
      }
    }

    if (!this.started) {
      return true
    }

    let emitted = 0
    while (emitted < channel.length && this.samplesAvailable > 0) {
      channel[emitted] = this.buffer[this.readIndex]
      this.readIndex = (this.readIndex + 1) % this.capacitySamples
      this.samplesAvailable -= 1
      emitted += 1
    }

    if (emitted > 0 && this.firstSamplePending) {
      this.firstSamplePending = false
      this.port.postMessage({
        type: 'first_sample_played',
        contextTimeSeconds: currentTime,
      })
    }

    if (emitted < channel.length) {
      this.underruns += 1
      // Keep playing when more audio arrives; do not pause (pausing dropped queued TTS).
      this.port.postMessage({
        type: 'underrun',
        underruns: this.underruns,
        bufferedSamples: this.samplesAvailable,
      })
    }

    return true
  }
}

registerProcessor('playback-processor', PlaybackProcessor)
