import { describe, expect, it } from 'vitest'

import { float32ToPcm16Le } from './pcm'
import { Pcm16RingBuffer } from './playback-buffer'

describe('Pcm16RingBuffer', () => {
  it('preserves samples when pushing and popping PCM16 chunks', () => {
    const ring = new Pcm16RingBuffer(16)
    const source = new Float32Array([0, 0.25, -0.25, 0.5, -0.5, 1, -1])
    ring.pushPcm16(float32ToPcm16Le(source))

    const popped = ring.popSamples(source.length)
    for (let index = 0; index < source.length; index += 1) {
      expect(popped[index]).toBeCloseTo(source[index], 4)
    }
    expect(ring.availableSamples).toBe(0)
  })

  it('clears pending audio on flush', () => {
    const ring = new Pcm16RingBuffer(8)
    ring.pushPcm16(float32ToPcm16Le(new Float32Array([0.2, 0.4, 0.6])))
    expect(ring.availableSamples).toBe(3)

    ring.clear()
    expect(ring.availableSamples).toBe(0)
    expect(Array.from(ring.popSamples(3))).toEqual([0, 0, 0])
  })
})
