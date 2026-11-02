export class Pcm16RingBuffer {
  private readonly capacitySamples: number
  private readonly buffer: Float32Array
  private writeIndex = 0
  private readIndex = 0
  private samplesAvailable = 0

  constructor(capacitySamples: number) {
    this.capacitySamples = capacitySamples
    this.buffer = new Float32Array(capacitySamples)
  }

  get availableSamples(): number {
    return this.samplesAvailable
  }

  clear(): void {
    this.writeIndex = 0
    this.readIndex = 0
    this.samplesAvailable = 0
  }

  pushPcm16(frame: Uint8Array): void {
    const sampleCount = Math.floor(frame.byteLength / 2)
    const view = new DataView(frame.buffer, frame.byteOffset, frame.byteLength)

    for (let index = 0; index < sampleCount; index += 1) {
      if (this.samplesAvailable === this.capacitySamples) {
        this.readIndex = (this.readIndex + 1) % this.capacitySamples
        this.samplesAvailable -= 1
      }

      const int16 = view.getInt16(index * 2, true)
      this.buffer[this.writeIndex] = int16 < 0 ? int16 / 0x8000 : int16 / 0x7fff
      this.writeIndex = (this.writeIndex + 1) % this.capacitySamples
      this.samplesAvailable += 1
    }
  }

  popSamples(sampleCount: number): Float32Array {
    const output = new Float32Array(sampleCount)
    const samplesToRead = Math.min(sampleCount, this.samplesAvailable)

    for (let index = 0; index < samplesToRead; index += 1) {
      output[index] = this.buffer[this.readIndex]
      this.readIndex = (this.readIndex + 1) % this.capacitySamples
      this.samplesAvailable -= 1
    }

    return output
  }
}
