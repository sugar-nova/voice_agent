export function float32ToPcm16Le(samples: Float32Array): Uint8Array {
  const pcm = new Uint8Array(samples.length * 2)
  const view = new DataView(pcm.buffer)

  for (let index = 0; index < samples.length; index += 1) {
    const clamped = Math.max(-1, Math.min(1, samples[index]))
    const int16 = clamped < 0 ? Math.round(clamped * 0x8000) : Math.round(clamped * 0x7fff)
    view.setInt16(index * 2, int16, true)
  }

  return pcm
}
