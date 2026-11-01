# Voice Agent: Phase 1 Plan (Echo Agent)

**Goal of Phase 1:** prove the real-time audio pipeline end to end, with measured latency, before any business logic exists.

```
[Browser Mic] --PCM frames--> [Server: VAD -> Streaming STT] --text--> [Echo Logic]
                                                                          |
[Browser Speaker] <--PCM frames-- [Server: Streaming TTS] <------text-----+
```

Stack: **TypeScript + Vite** on the client, **Python (asyncio) + Pipecat** on the server, **Deepgram** for STT, **Cartesia** for TTS, **Silero VAD** for voice activity detection.

> Provider APIs and framework versions change quickly. Treat every code sketch and model name here as a starting point and check the current docs of Pipecat, Deepgram and Cartesia before implementing. Latency figures are ballpark and must be measured on your own setup.

---

## 1. Scope

### In scope
- Capture microphone audio in the browser and stream it to the server.
- Streaming speech-to-text with interim and final transcripts.
- Echo logic that returns `"I heard you say: <transcript>"`.
- Streaming text-to-speech played back in the browser.
- Voice activity detection and end-of-turn detection (basic, silence-based).
- Barge-in: if the user starts talking while the agent is speaking, playback stops immediately.
- Per-stage latency instrumentation, logged and shown in a debug panel.
- Minimal UI: connect/disconnect, mic state, live transcript, latency readout.

### Out of scope (later phases)
- FAQ retrieval, embeddings, LLM fallback (Phase 2).
- Semantic turn detection, multi-language, authentication, persistence.
- Production deployment, autoscaling, monitoring dashboards.
- Telephony (SIP/PSTN).

---

## 2. Success criteria

Phase 1 is done when all of these hold on a normal home or office connection:

| # | Criterion | Target |
|---|---|---|
| 1 | End-to-end latency (user stops speaking -> first agent audio heard), median over 30 utterances | **< 800 ms** (stretch: < 600 ms) |
| 2 | Same metric, 95th percentile | < 1200 ms |
| 3 | Audio playback has no audible glitches or gaps during a 2-minute session | Pass |
| 4 | Agent does not hear and respond to its own voice (echo cancellation works) | Pass, with speakers and headphones |
| 5 | Barge-in stops agent audio | < 200 ms from user speech onset |
| 6 | Session runs 10 minutes without disconnects or memory growth | Pass |
| 7 | Every stage of the latency budget is logged per turn | Pass |

---

## 3. Decisions made

| Decision | Choice | Reason |
|---|---|---|
| Client language | TypeScript + Vite | Type safety, fast dev loop, first-class Web Audio support |
| Server language | Python 3.11+ with asyncio | Workload is I/O-bound; best voice-agent and ML ecosystem |
| Orchestration | **Pipecat** | Frame-based pipeline maps directly onto STT -> logic -> TTS; handles interruptions |
| Transport (Phase 1) | **WebSocket** with raw PCM frames | Simplest to debug and measure. Hidden behind a transport interface |
| Transport (Phase 1b) | WebRTC (Pipecat small WebRTC transport, or LiveKit/Daily) | Lower latency and better on lossy networks; swapped in after the echo works |
| STT | Deepgram streaming | Low latency, interim results, built-in endpointing |
| TTS | Cartesia (streaming) | Very low time to first byte |
| VAD | Silero VAD | Small, accurate, CPU only |

**Assumption to confirm:** WebSocket first, WebRTC second. If you would rather start on WebRTC, only Milestone 3 and the transport layer change; everything else stays the same.

---

## 4. Architecture

### 4.1 Server pipeline (Pipecat)

```
transport.input()
  -> VAD (Silero)
  -> DeepgramSTTService
  -> EchoProcessor            # our code: text in, text out
  -> CartesiaTTSService
  -> transport.output()
```

- Frames flow through the pipeline; the transport and VAD handle interruption frames so that user speech cancels in-flight TTS.
- `EchoProcessor` is the only piece that changes in Phase 2 (replaced by the FAQ brain).
- A latency observer taps the pipeline and records timestamps (section 6).

### 4.2 Client

```
getUserMedia -> AudioWorklet (capture) -> WebSocket (binary frames) -> server
server -> WebSocket (binary frames) -> jitter buffer -> AudioWorklet (playback) -> speakers
```

### 4.3 Audio formats

| Direction | Format | Frame size |
|---|---|---|
| Client -> server | PCM signed 16-bit little-endian, mono, **16 kHz** | 20 ms = 320 samples = 640 bytes |
| Server -> client | PCM signed 16-bit little-endian, mono, **24 kHz** (match what the TTS provider outputs; resample on the client if the AudioContext rate differs) | 20-40 ms |

### 4.4 WebSocket protocol

- **Binary messages:** raw PCM audio frames (both directions).
- **Text messages:** JSON control and event messages.

```jsonc
// client -> server
{ "type": "start", "sampleRate": 16000 }
{ "type": "stop" }

// server -> client
{ "type": "ready" }
{ "type": "transcript", "text": "...", "final": false }
{ "type": "transcript", "text": "...", "final": true }
{ "type": "agent_text", "text": "I heard you say: ..." }
{ "type": "interrupt" }                      // client must flush its playback buffer now
{ "type": "metrics", "turnId": 7, "stages": { ... } }
{ "type": "error", "message": "..." }
```

---

## 5. Repository structure

Because the server is Python, the shared `core/` folder from the earlier layout no longer applies. Agent logic moves under `server/`.

```
voice_agent/
├── client/
│   ├── public/
│   │   └── worklets/
│   │       ├── capture-processor.js     # AudioWorklet: mic -> PCM16 frames
│   │       └── playback-processor.js    # AudioWorklet: jitter buffer -> speakers
│   └── src/
│       ├── audio/                       # mic setup, AudioContext, worklet loading
│       ├── transport/                   # Transport interface + WebSocketTransport (later WebRTCTransport)
│       ├── agent/                       # session orchestration (connect, state machine)
│       ├── metrics/                     # client-side timing (perceived latency)
│       └── ui/                          # controls, transcript, latency panel
├── server/
│   ├── pyproject.toml
│   ├── app/
│   │   ├── main.py                      # FastAPI app, WebSocket endpoint, health check
│   │   ├── pipeline.py                  # builds the Pipecat pipeline
│   │   ├── config.py                    # settings from env
│   │   ├── agents/
│   │   │   └── echo.py                  # EchoProcessor (Phase 2: agents/faq/)
│   │   ├── observers/
│   │   │   └── latency.py               # per-turn timestamps and metrics
│   │   └── schemas.py                   # message types
│   └── tests/
├── config/
│   └── .env.example
├── scripts/
│   ├── bench_latency.py                 # replays a WAV file through the pipeline
│   └── check_providers.py               # smoke-tests STT/TTS keys and region latency
├── docs/
│   ├── phase1-plan.md                   # this file
│   └── latency-log.md                   # measurements per milestone
└── .env                                 # never committed
```

---

## 6. Latency instrumentation (build this first)

You cannot tune what you do not measure. Record these timestamps for every turn, keyed by `turnId`.

| Timestamp | Event | Where captured |
|---|---|---|
| `t0` | User speech ended (VAD says speech stopped) | Server |
| `t1` | STT final transcript received | Server |
| `t2` | Echo text produced | Server |
| `t3` | TTS first audio chunk received | Server |
| `t4` | First audio frame sent to client | Server |
| `t5` | First audio frame actually played | **Client** (`performance.now()` in the playback worklet message) |

Derived metrics:

| Metric | Formula | Meaning |
|---|---|---|
| Endpointing wait | `t1 - t0` (roughly) | How long STT took after speech stopped |
| STT finalization | `t1 - t0` | Streaming STT cost |
| Logic | `t2 - t1` | Should be near zero for echo |
| TTS time to first byte | `t3 - t2` | Provider TTS latency |
| Server total | `t4 - t0` | What your server controls |
| **Perceived latency** | `t5 - (user actually stopped speaking)` | The number that matters. Includes network and playback buffer |

Notes:
- Server and client clocks differ. Measure the network portion by ping/pong round trip (half the RTT as an estimate) and report it separately instead of subtracting raw timestamps.
- VAD stop detection itself includes a configured silence timeout (for example 300-500 ms). Log that setting next to each result, since it usually dominates the total.
- Log each turn as one JSON line so results are easy to aggregate.
- Keep a table of results per milestone in `docs/latency-log.md`.

---

## 7. Milestones

Each milestone has tasks and an acceptance test. Do them in order.

### Milestone 0: Project setup and provider checks
**Tasks**
1. Create the repo structure above with `.gitkeep` in empty folders.
2. Client: `npm create vite@latest client -- --template vanilla-ts`; enable strict TypeScript.
3. Server: Python 3.11+, virtual environment, `pyproject.toml`; install `pipecat-ai` with the extras for Deepgram, Cartesia and Silero (check the Pipecat docs for the exact extras names), plus `fastapi` and `uvicorn`.
4. Create `config/.env.example` with `DEEPGRAM_API_KEY`, `CARTESIA_API_KEY`, `CARTESIA_VOICE_ID`, `PORT`, `LOG_LEVEL`. Add `.env` to `.gitignore`.
5. Write `scripts/check_providers.py`: send a short WAV to Deepgram and synthesize one sentence with Cartesia; print time to first result for each.
6. Pick the server region closest to the providers' endpoints and note it in the docs.

**Acceptance:** the check script succeeds, and you have a baseline STT and TTS latency number from your machine.

### Milestone 1: Server pipeline, no browser
**Tasks**
1. Implement `EchoProcessor`: on each final transcript frame emit a text frame `"I heard you say: {text}"`. Ignore empty transcripts.
2. Build the pipeline in `pipeline.py` (transport input -> VAD -> STT -> echo -> TTS -> transport output).
3. Implement `observers/latency.py` and emit one JSON log line per turn.
4. Write `scripts/bench_latency.py` that streams a recorded WAV (16 kHz mono) into the pipeline at real-time speed and writes the TTS output to a WAV file.

**Acceptance:** feeding "what are your opening hours" produces an audio file that says "I heard you say: what are your opening hours", and the log shows all of `t0` to `t4`.

### Milestone 2: Client audio capture and playback (loopback)
**Tasks**
1. Request the mic with `echoCancellation: true`, `noiseSuppression: true`, `autoGainControl: true`, mono.
2. Create an `AudioContext` (request 16 kHz for capture if supported, otherwise resample in the worklet).
3. `capture-processor.js`: convert Float32 to PCM16 and post 20 ms frames to the main thread.
4. `playback-processor.js`: ring buffer with a small target depth (start at about 60-100 ms), an underrun counter, and a `flush()` message.
5. Local test with no server: pipe captured frames straight into playback (use headphones to avoid feedback) and confirm clean audio.

**Acceptance:** you can hear yourself with no crackle, and underrun count stays at 0 over 2 minutes.

### Milestone 3: WebSocket transport, full round trip
**Tasks**
1. Define the `Transport` interface on the client (`connect`, `sendAudio`, `onAudio`, `onEvent`, `close`) and implement `WebSocketTransport` against it.
2. Server: `/ws` endpoint wiring the Pipecat transport; reject connections with no valid `start` message.
3. Client session state machine: `idle -> connecting -> listening -> agent_speaking -> idle`, with `error` and reconnect handling.
4. Handle `interrupt` events by flushing the playback buffer immediately.
5. Add `ping`/`pong` messages every few seconds to estimate network RTT.
6. Report `t5` from the client by sending a `playback_started` event with the turn ID.

**Acceptance:** speak a sentence in the browser; the agent replies with the echo sentence; transcripts appear live; the metrics message arrives with all timestamps.

### Milestone 4: Barge-in and robustness
**Tasks**
1. When VAD detects user speech during agent playback, cancel TTS on the server and send `interrupt`.
2. Make sure echo cancellation is effective: test with laptop speakers at moderate volume. If the agent triggers on its own voice, require headphones for now and note it as a known limitation, or raise the VAD threshold during agent speech.
3. Handle: mic permission denied, WebSocket drop (auto-reconnect with backoff), provider errors (spoken fallback line such as "Sorry, something went wrong"), tab in background, and double-clicking connect.
4. Keep provider connections warm: open STT and TTS connections at session start rather than on first utterance.

**Acceptance:** interrupting mid-sentence stops audio quickly, the agent then echoes the new utterance, and none of the failure cases above crash the session.

### Milestone 5: Latency tuning and benchmark
**Tasks**
1. Run 30 scripted utterances (mix of 3-word, 10-word and 25-word sentences) and record the metrics.
2. Tune, one change at a time, re-measuring after each:
   - VAD silence timeout and Deepgram endpointing settings.
   - Client playback buffer depth.
   - Audio frame size (20 ms vs 40 ms).
   - Sending the TTS request as soon as the final transcript arrives.
   - Server region and connection reuse.
3. Record before/after results in `docs/latency-log.md`.
4. Optionally try the WebRTC transport (Phase 1b) and compare p50/p95.

**Acceptance:** success criteria 1-7 in section 2 are met, with the data written down.

---

## 8. Testing plan

| Level | What | How |
|---|---|---|
| Unit (server) | `EchoProcessor` behavior: normal text, empty text, long text, special characters | pytest |
| Unit (client) | PCM conversion, ring buffer, state machine | Vitest |
| Integration | Pipeline fed with recorded WAV, asserts on transcript text and non-empty audio output | pytest with `bench_latency.py` |
| Manual | Different mics, speakers vs headphones, Chrome, Safari, Firefox, mobile Chrome | Checklist in `docs/` |
| Network | Throttle to simulate 100 ms latency and 2% packet loss (browser dev tools or `tc`) | Compare WebSocket and WebRTC |

Browser note: Safari and iOS have stricter AudioContext and AudioWorklet rules (user gesture required to start audio). Start the AudioContext from the Connect button click.

---

## 9. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Agent hears its own voice and loops | Broken conversation | Echo cancellation constraints, headphones for early testing, VAD threshold while speaking |
| WebSocket (TCP) stutters on bad networks | Choppy audio | Small jitter buffer, measure, then move to WebRTC (Phase 1b) |
| Silence-based endpointing adds 300-500 ms | Misses latency target | Tune timeout; semantic turn detection in a later phase |
| Provider cold starts or new connections | Slow first turn | Warm connections at session start |
| Pipecat or provider API changes | Build breaks | Pin versions in `pyproject.toml`; read release notes before upgrading |
| Sample-rate mismatches | Pitch-shifted or noisy audio | Explicit formats in section 4.3; log the AudioContext rate on connect |
| API keys exposed | Security issue | Keys only on the server, never sent to the browser; `.env` in `.gitignore` |
| Costs while testing | Unexpected bill | Disconnect idle sessions after 60 s of silence; set provider spend limits |

---

## 10. Definition of done

- [ ] All milestones 0-5 completed, each with its acceptance test passed
- [ ] Success criteria table (section 2) filled with real measurements
- [ ] `docs/latency-log.md` contains before/after tuning data
- [ ] README explains how to run client and server in under 5 commands
- [ ] Versions pinned; `.env.example` complete; no secrets in git
- [ ] Known limitations written down (for example "use headphones")

---

## 11. Handoff to Phase 2 (FAQ brain)

Phase 1 leaves these seams ready:

1. **Swap point:** replace `agents/echo.py` with `agents/faq/` that takes a final transcript and returns answer text. Nothing else in the pipeline changes.
2. **Fast path:** high-confidence vector match returns the stored answer directly, with no LLM call.
3. **Pre-generated audio:** cache TTS audio for the most common answers and play it directly.
4. **LLM fallback:** a small fast model streaming tokens to TTS sentence by sentence, for fuzzy or multi-part questions.
5. **Metrics:** the existing latency observer gains `retrieval_ms` and `llm_first_token_ms` fields.

---

## 12. Suggested order of the first working session

1. Milestone 0, steps 1-5 (about an hour).
2. Milestone 1 with the WAV benchmark. Getting a correct echo from a file proves the providers and the pipeline before the browser is involved.
3. Milestone 2 in parallel if two people are working; otherwise afterwards.
