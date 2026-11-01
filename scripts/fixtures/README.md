# Audio fixtures

| File | Format | Purpose |
|------|--------|---------|
| `hello.wav` | 16 kHz, mono, PCM16 | Deepgram STT smoke test (`check_providers.py`) |

Regenerate on macOS:

```bash
python scripts/generate_hello_fixture.py
```

Without macOS `say`, record ~1–2 s of clear speech or convert with ffmpeg:

```bash
ffmpeg -i your-recording.wav -ar 16000 -ac 1 scripts/fixtures/hello.wav
```
