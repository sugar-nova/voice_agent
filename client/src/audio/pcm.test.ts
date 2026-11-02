import { describe, expect, it } from 'vitest'

import { float32ToPcm16Le } from './pcm'

describe('float32ToPcm16Le', () => {
  it('converts known float samples to PCM16 little-endian bytes', () => {
    const samples = new Float32Array([-1, -0.5, 0, 0.5, 1])
    const pcm = float32ToPcm16Le(samples)

    expect(Array.from(pcm)).toEqual([
      0x00,
      0x80, // -32768
      0x00,
      0xc0, // -16384
      0x00,
      0x00, // 0
      0x00,
      0x40, // 16384
      0xff,
      0x7f, // 32767
    ])
  })
})
