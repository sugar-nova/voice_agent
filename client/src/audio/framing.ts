import { FRAME_SAMPLES } from './constants'
import { float32ToPcm16Le } from './pcm'

export type FramingResult = {
  frames: Uint8Array[]
  remainder: Float32Array
}

export function framePcm16(
  input: Float32Array,
  previousRemainder: Float32Array = new Float32Array(0),
): FramingResult {
  const merged = new Float32Array(previousRemainder.length + input.length)
  merged.set(previousRemainder)
  merged.set(input, previousRemainder.length)

  const frames: Uint8Array[] = []
  let offset = 0
  while (offset + FRAME_SAMPLES <= merged.length) {
    const frameSamples = merged.subarray(offset, offset + FRAME_SAMPLES)
    frames.push(float32ToPcm16Le(frameSamples))
    offset += FRAME_SAMPLES
  }

  return {
    frames,
    remainder: merged.slice(offset),
  }
}
