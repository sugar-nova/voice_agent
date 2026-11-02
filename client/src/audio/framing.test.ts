import { describe, expect, it } from 'vitest'

import { FRAME_BYTES, FRAME_SAMPLES } from './constants'
import { framePcm16 } from './framing'

describe('framePcm16', () => {
  it('emits fixed-size 20 ms frames and keeps remainder', () => {
    const source = new Float32Array(FRAME_SAMPLES * 2 + 10).fill(0.25)
    const firstPass = framePcm16(source)

    expect(firstPass.frames).toHaveLength(2)
    expect(firstPass.frames[0].byteLength).toBe(FRAME_BYTES)
    expect(firstPass.frames[1].byteLength).toBe(FRAME_BYTES)
    expect(firstPass.remainder.length).toBe(10)

    const secondPassInput = new Float32Array(FRAME_SAMPLES - 10).fill(0.5)
    const secondPass = framePcm16(secondPassInput, firstPass.remainder)

    expect(secondPass.frames).toHaveLength(1)
    expect(secondPass.frames[0].byteLength).toBe(FRAME_BYTES)
    expect(secondPass.remainder.length).toBe(0)
  })
})
