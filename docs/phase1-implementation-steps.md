# Phase 1 — Micro implementation steps

One step = one focused change you can implement, run, and check off. Do them **in order** unless noted.

**Spec:** [phase1-plan.md](./phase1-plan.md)  
**How to use:** pick the next unchecked step, implement only that step, pass its **Done when**, then move on.

---

## Legend

| Field | Meaning |
|-------|---------|
| **ID** | Stable reference (e.g. `M0-07`) |
| **Done when** | Minimum proof this step worked |
| **Depends on** | Must be complete first |

---

## Milestone 0 — Project setup and provider checks

### M0 — Repository and layout

| ID | Step | Done when |
|----|------|-----------|
| **M0-01** | Add root `.gitignore`: `.env`, `__pycache__/`, `.venv/`, `venv/`, `node_modules/`, `dist/`, `.DS_Store`, `*.wav` under `tmp/` or `artifacts/` if you use them for benches. | File exists; `git status` does not show ignored junk. |
| **M0-02** | Align folders with [phase1-plan §5](./phase1-plan.md#5-repository-structure): `client/public/worklets/`, `client/src/{audio,transport,agent,metrics,ui}/`, `server/app/{agents,observers}/`, `server/tests/`, keep `config/`, `scripts/`, `docs/`. Remove or stop using obsolete `core/` and old `server/src/` placeholders when you migrate. | Tree matches the plan; empty dirs have `.gitkeep` where needed. |
| **M0-03** | Add root `README.md` section (or short `README` stub): one sentence on Phase 1 goal + pointer to this file. | New contributor knows where the step list lives. |

### M0 — Client scaffold

| ID | Step | Done when |
|----|------|-----------|
| **M0-04** | Scaffold client: `npm create vite@latest client -- --template vanilla-ts` (from repo root). | `client/package.json` exists; `npm run dev` serves the default Vite page. |
| **M0-05** | Enable `"strict": true` (and related strict flags you want) in `client/tsconfig.json`. | `npm run build` succeeds with strict on. |
| **M0-06** | Add npm scripts you will use later: `dev`, `build`, `preview`, placeholder `test` (Vitest added in M2-xx). | Scripts run without error. |

### M0 — Server scaffold

| ID | Step | Depends on |
|----|------|------------|
| **M0-07** | Create `server/pyproject.toml` with Python **3.11+**, project name, and **pinned** dependencies (start minimal: `fastapi`, `uvicorn[standard]`). | `python -m venv .venv && pip install -e server` (or equivalent) works. |
| **M0-08** | Add Pipecat + provider extras per current Pipecat docs (Deepgram, Cartesia, Silero/VAD). Pin versions. | `pip install` succeeds; import `pipecat` in a one-line smoke script. |
| **M0-09** | Add empty modules: `server/app/main.py`, `config.py`, `schemas.py`, `pipeline.py`, `agents/echo.py`, `observers/latency.py`. | Package imports without circular errors. |
| **M0-10** | Add `GET /health` in `main.py` returning `{ "status": "ok" }`. | `curl localhost:PORT/health` returns 200. |

### M0 — Config and secrets

| ID | Step | Done when |
|----|------|-----------|
| **M0-11** | Create `config/.env.example` with `DEEPGRAM_API_KEY`, `CARTESIA_API_KEY`, `CARTESIA_VOICE_ID`, `PORT`, `LOG_LEVEL` (comments for each). | Example documents every required var. |
| **M0-12** | Load settings in `server/app/config.py` from env (path to `.env` at repo root or `config/` — pick one and document it). | Server prints loaded config at startup (keys redacted). |
| **M0-13** | Copy `.env.example` → `.env` locally; never commit `.env`. | Provider keys available to server process only. |

### M0 — Provider smoke test

| ID | Step | Depends on |
|----|------|------------|
| **M0-14** | Add a tiny **16 kHz mono** WAV fixture (e.g. `scripts/fixtures/hello.wav`, ~1 s) or document how to generate it. | File exists and plays in a normal player. |
| **M0-15** | `scripts/check_providers.py` — **Deepgram only**: send fixture WAV, print transcript + time-to-first/final result. | Script exits 0; latency number printed. |
| **M0-16** | Extend `check_providers.py` — **Cartesia only**: synthesize one short sentence, print time to first audio byte (or first chunk). | Script exits 0; latency number printed. |
| **M0-17** | Document chosen **server region** and provider endpoints in `docs/latency-log.md` (create file with a “Baseline — Milestone 0” section). | Note saved for later comparison. |

**Milestone 0 acceptance:** M0-15 and M0-16 both pass; you have baseline STT/TTS numbers written down.

---

## Milestone 1 — Server pipeline (no browser)

Build **latency observer early** (plan §6): you need `t0`–`t4` before tuning anything.

### M1 — Echo agent (unit-sized)

| ID | Step | Done when |
|----|------|-----------|
| **M1-01** | Define shared message/event types in `schemas.py` (transcript, agent text, metrics shape — match plan §4.4 fields you need on server-side first). | Types importable from echo + observer. |
| **M1-02** | Implement `EchoProcessor` skeleton: pass-through for non-final frames; no-op on empty final text. | Unit test or manual call shows empty ignored. |
| **M1-03** | On **final** transcript with text, emit agent text: `I heard you say: {text}`. | Test: input `"hello"` → exact output string. |
| **M1-04** | pytest for echo: normal text, empty, long text, punctuation/unicode. | `pytest server/tests` green for echo tests. |

### M1 — Latency observer

| ID | Step | Done when |
|----|------|-----------|
| **M1-05** | Define `turnId` generation and timestamp fields `t0`–`t4` in `observers/latency.py` (plan §6 table). | Docstring or comment maps events → fields. |
| **M1-06** | Hook observer into pipeline stages (or frame taps): record `t0` on VAD speech-end, `t1` STT final, `t2` echo out, `t3` TTS first chunk, `t4` first outbound audio frame. | One turn produces all five timestamps in memory. |
| **M1-07** | Emit **one JSON log line per turn** to stdout/logger (include `turnId`, `stages`, VAD silence timeout setting when known). | Log line parseable with `jq`. |

### M1 — Pipeline assembly

| ID | Step | Depends on |
|----|------|------------|
| **M1-08** | Choose Pipecat transport for **file/bench mode** (local or in-memory transport — per Pipecat docs for offline testing). | Audio/text frames flow in a minimal script. |
| **M1-09** | Wire **Silero VAD** into pipeline after transport input. | VAD fires on speech in fixture. |
| **M1-10** | Wire **Deepgram STT** (streaming) after VAD. | Final transcript matches fixture words (roughly). |
| **M1-11** | Insert **EchoProcessor** after STT. | Agent text frame appears in pipeline. |
| **M1-12** | Wire **Cartesia TTS** after echo. | Audio frames non-empty. |
| **M1-13** | Wire transport **output**; consolidate in `pipeline.py` factory `build_pipeline(...)`. | Single function builds full chain. |

### M1 — WAV benchmark script

| ID | Step | Done when |
|----|------|-----------|
| **M1-14** | `scripts/bench_latency.py`: load 16 kHz mono WAV, stream into pipeline at **real-time** rate. | Script runs without blocking errors. |
| **M1-15** | Write TTS output to an output WAV file. | Output file playable. |
| **M1-16** | Bench uses utterance *"what are your opening hours"* (or your fixture with that text). | Spoken output contains *"I heard you say: what are your opening hours"*. |
| **M1-17** | Bench run prints or logs **t0–t4** for that turn. | All five timestamps present. |

**Milestone 1 acceptance:** M1-16 + M1-17 pass.

---

## Milestone 2 — Client audio (loopback, no server)

### M2 — Mic and AudioContext

| ID | Step | Done when |
|----|------|-----------|
| **M2-01** | Add Vitest + config for client unit tests. | `npm test` runs (even if zero tests). |
| **M2-02** | `getUserMedia` helper with `echoCancellation`, `noiseSuppression`, `autoGainControl`, mono. | Permission prompt works; track active. |
| **M2-03** | Create `AudioContext`; log actual sample rate; document resample plan if not 16 kHz. | Rate visible in console on start. |
| **M2-04** | Load `capture-processor.js` from `public/worklets/`; register worklet node. | No worklet load errors. |

### M2 — Capture worklet

| ID | Step | Done when |
|----|------|-----------|
| **M2-05** | Capture worklet: Float32 → **PCM16 LE** conversion. | Unit test on known float buffer → expected bytes. |
| **M2-06** | Emit **20 ms** frames (320 samples @ 16 kHz = 640 bytes); post to main thread. | Frame size constant verified in test. |
| **M2-07** | Main thread receives frames without dropping (counter in dev mode). | 10 s capture shows stable frame count. |

### M2 — Playback worklet

| ID | Step | Done when |
|----|------|-----------|
| **M2-08** | Playback worklet: ring buffer accepting PCM16 chunks. | Test push/pop sample accuracy. |
| **M2-09** | Target buffer depth **~60–100 ms**; track **underrun** count. | Underruns logged. |
| **M2-10** | Implement `flush()` message — clears buffer immediately. | After flush, no old audio plays. |
| **M2-11** | Playback worklet reports **first sample played** timestamp (for later `t5`). | Message received on main thread once per flush/play cycle. |

### M2 — Local loopback

| ID | Step | Done when |
|----|------|-----------|
| **M2-12** | Dev-only loopback: route captured frames directly to playback (no WebSocket). | Hear yourself in **headphones**. |
| **M2-13** | Run loopback **2 minutes**; underrun count stays **0**. | Counter logged at end. |
| **M2-14** | Minimal UI button: Start/Stop loopback (user gesture starts AudioContext — plan §8 Safari note). | Works after single click. |

**Milestone 2 acceptance:** M2-13 + M2-14 pass.

---

## Milestone 3 — WebSocket full round trip

### M3 — Protocol types (client)

| ID | Step | Done when |
|----|------|-----------|
| **M3-01** | TypeScript types for all JSON messages in plan §4.4 (`start`, `stop`, `ready`, `transcript`, `agent_text`, `interrupt`, `metrics`, `error`). | Shared `types.ts` compiles. |
| **M3-02** | Constants for audio: uplink 16 kHz PCM16 mono, 640-byte frames; downlink 24 kHz (document). | Documented next to types. |

### M3 — Transport layer

| ID | Step | Done when |
|----|------|-----------|
| **M3-03** | Define `Transport` interface: `connect`, `sendAudio`, `onAudio`, `onEvent`, `close`. | Interface in `client/src/transport/`. |
| **M3-04** | `WebSocketTransport`: open WS, send binary PCM, receive binary PCM. | Connects to a echo WS test server or mock. |
| **M3-05** | Send JSON `start` with `sampleRate: 16000` after connect; send `stop` on close. | Server can read start payload. |
| **M3-06** | Parse incoming JSON events; dispatch to handlers. | Transcript event reaches UI callback. |
| **M3-07** | Add `ping`/`pong` JSON messages; compute RTT estimate. | RTT shown in dev console. |

### M3 — Server WebSocket

| ID | Step | Depends on |
|----|------|------------|
| **M3-08** | `WebSocket /ws` endpoint; wait for valid `start` before accepting audio. | Invalid first message → close with error. |
| **M3-09** | Bridge WS binary frames ↔ Pipecat transport input/output. | Frames reach pipeline. |
| **M3-10** | Emit `ready` after pipeline session is up. | Client receives `ready`. |
| **M3-11** | Emit `transcript` (interim + final), `agent_text`, `metrics`, `error` as JSON. | Client UI can bind each type. |
| **M3-12** | On interrupt path from pipeline, send `{ "type": "interrupt" }`. | Client receives interrupt event. |

### M3 — Session orchestration (client)

| ID | Step | Done when |
|----|------|-----------|
| **M3-13** | State machine: `idle → connecting → listening → agent_speaking → listening` (+ `error`). | Transitions logged in dev mode. |
| **M3-14** | Connect button: start AudioContext + WS + mic capture → uplink frames. | Server receives audio. |
| **M3-15** | Downlink: WS audio → playback worklet. | Hear TTS from server. |
| **M3-16** | On `interrupt`, call playback `flush()`. | Barge-in audio cut (manual test in M4). |
| **M3-17** | Client sends `playback_started` with `turnId` when worklet plays first sample; server/client merge into metrics for **t5**. | Metrics event includes client timing fields. |

### M3 — Minimal UI

| ID | Step | Done when |
|----|------|-----------|
| **M3-18** | UI: Connect / Disconnect, mic status, live transcript (interim + final). | Visible during session. |
| **M3-19** | UI: latency / metrics panel (last turn stages + RTT). | Updates after each agent turn. |

**Milestone 3 acceptance:** Speak one sentence → hear echo → transcripts + metrics with timestamps (including t5 path started).

---

## Milestone 4 — Barge-in and robustness

### M4 — Barge-in

| ID | Step | Done when |
|----|------|-----------|
| **M4-01** | Server: user speech during agent TTS → cancel TTS + emit interrupt frame/event. | Interrupt JSON received on client. |
| **M4-02** | Client: flush + return to `listening` quickly. | **< 200 ms** subjectively or measured from speech onset. |
| **M4-03** | New utterance after interrupt gets full echo response. | Second turn correct. |

### M4 — Echo / self-trigger

| ID | Step | Done when |
|----|------|-----------|
| **M4-04** | Test with **laptop speakers** at moderate volume; note if agent hears itself. | Result documented in README/latency-log. |
| **M4-05** | Mitigation if needed: headphones requirement and/or higher VAD threshold while agent speaks. | Config flag or doc’d workaround. |

### M4 — Failure handling

| ID | Step | Done when |
|----|------|-----------|
| **M4-06** | Mic permission denied → clear UI message, no crash. | Manual test. |
| **M4-07** | WebSocket drop → auto-reconnect with backoff; resend `start`. | Kill server mid-session; recovers. |
| **M4-08** | Provider error → `error` event + spoken fallback (*"Sorry, something went wrong"* via TTS or pre-recorded beep). | Simulated bad key or mock. |
| **M4-09** | Tab background: session pauses or continues per your choice (document behavior). | Manual test note. |
| **M4-10** | Double-click Connect: idempotent (no duplicate WS/mic). | Rapid clicks safe. |
| **M4-11** | **Warm connections**: open STT + TTS at session start, not first utterance. | First turn not an outlier vs second. |

**Milestone 4 acceptance:** M4-01–M4-03 + failure cases M4-06–M4-10 pass.

---

## Milestone 4B — Knowledge brain (**L1 delivery now**; L2 deferred)

Replace the echo agent with a **scoped FAQ brain**. Source of truth = the Wise **"Where is my money"** help section only ([link](https://wise.com/help/topics/5bVKT0uQdBrDp6T62keyfz/sending-money)).

**Phase 1B focus (ship now):**

- **Layer 1 — Redis Stack semantic router:** embed the user query; KNN against **engineered question variants** (`embedded_questions` per intent in `faqs.yaml`). If similarity **≥ `BRAIN_L1_THRESHOLD`** (baseline **0.95**, tune with `scripts/eval_l1_threshold.py`), return the voice-optimized answer **straight to TTS** (no LLM).
- **Out-of-scope gate:** any query below threshold (with `BRAIN_ENABLE_L2=false`) → deflect handoff + end session.

**Layer 2 (implemented, opt-in):** Qdrant retrieval + streamed local-LLM answers for in-scope questions L1 misses (`BRAIN_ENABLE_L2=true`). Steps **M4B-08–M4B-12** are under **Layer 2** below. Still open for L2: browser E2E of the `l2_rag` path (M4B-17) and L2 latency rows (M4B-22, M5-11–M5-13).

**Strict requirement:** the bot answers only questions in the "Where is my money" section. **Any other question → deflect to a human** (short handoff line, then cut the call).

> **KB engineering:** Q→A routing — embed **questions only**, store one spoken answer payload per intent. See `docs/kb-scope.md` and hard-negative fixtures in `server/app/kb/eval_queries_hard_negatives.yaml`.

### M4B — Knowledge base and scope

| ID | Step | Done when |
|----|------|-----------|
| **M4B-01** | Define the **in-scope boundary**: enumerate the subtopics/questions under the Wise "Where is my money" section. Write `docs/kb-scope.md` listing in-scope intents **and** explicit out-of-scope examples. | A reviewer can classify any question as in/out of scope from the doc alone. |
| **M4B-02** | Curate KB into `server/app/kb/faqs.yaml`: per intent `id`, `question`, **`embedded_questions`** (5+ variants), voice `answer`, `tags`/`category`. | File parses; entries cover the section; loader supports variants. |
| **M4B-03** | Pick + **pin** an embedding model/provider; add its var(s) (e.g. `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, key) to `config/.env.example`. | One-line script embeds a string and prints the vector dim. |

### M4B — Layer 1: Redis semantic router

| ID | Step | Done when |
|----|------|-----------|
| **M4B-04** | Add **Redis Stack** (docker-compose service or local) + pinned client dep. | `PING` → `PONG`; RediSearch module present. |
| **M4B-05** | `scripts/build_redis_index.py`: `PING` + RediSearch module check; `FT.CREATE` vector index; embed each **question variant**; store vector + metadata (`faq_id`, answer payload). | Index populated; row count = total `embedded_questions`; `FT.INFO` ok. |
| **M4B-06** | Router lookup: embed query → **Redis `FT.SEARCH` KNN** (not in-process matrix when Redis is configured) → best match + similarity. | Unit/integration test: canonical + variant queries return expected `faq_id`. |
| **M4B-07** | Threshold gate: sim **≥ `BRAIN_L1_THRESHOLD`** (default **0.95**) → stored answer on **straight-to-TTS** path (no LLM). Tune with `scripts/eval_l1_threshold.py` (+ hard-negative YAML). | Paraphrase above threshold → stored answer; hard negative below → deflect path. |

### Layer 2: Qdrant retrieval + local LLM *(implemented; enable with `BRAIN_ENABLE_L2=true`)*

L1 misses go to L2: retrieve the top 3 FAQ chunks from Qdrant, then a **local Ollama model** answers only from those chunks or replies `NOT_COVERED` (→ deflect). Code: `server/app/brain/l2.py`, `qdrant_store.py`, `llm.py`, `decision.py`. Evaluate end to end with `python scripts/eval_brain_routes.py`.

| ID | Step | Done when |
|----|------|-----------|
| **M4B-08** | Add **Qdrant** (docker-compose) + pinned client dep. | Collection API reachable; health ok. *(Done: compose service `qdrant/qdrant:v1.12.5`, `qdrant-client==1.12.1` in `server[brain]`. Falls back to in-memory with a logged warning when Qdrant is down.)* |
| **M4B-09** | Chunk + embed FAQ content into a Qdrant collection with **metadata payload** (category, subtopic, source `id`). | Collection count > 0; a filtered search returns the expected chunk. *(Done: one chunk per intent = all `embedded_questions` + answer; payload `faq_id`, `category`, `tags`, `question`, `answer`. Upserted on startup by `faq_id`; dropped FAQs are deleted. Test: `tests/test_qdrant_store.py`.)* |
| **M4B-10** | Retrieval fn (top-k + metadata filter + score), invoked only when L1 sim < threshold. | A combined in-scope question returns relevant chunks. *(Done: top-3 by cosine, reusing the L1 query embedding. No metadata filter — there is no per-query signal to filter on with 10 intents.)* |
| **M4B-11** | Pick + **pin** an LLM provider; stream synthesis from retrieved context with a guardrail prompt ("answer **only** from context; if not covered, say out of scope"). | Streams tokens; answer is grounded in the retrieved context. *(Done: Ollama `qwen2.5:3b` (`OLLAMA_MODEL`), temperature 0. Chosen over 7b (≈2× slower first token, 1 out-of-scope accepted) and 1.5b (8/20 out-of-scope accepted, invented details). Streamed to TTS sentence by sentence.)* |
| **M4B-12** | L2 relevance floor: top Qdrant score below threshold **or** LLM signals "not covered" → mark **out-of-scope**. | A clearly unrelated question is flagged out-of-scope. *(Done: `BRAIN_L2_RELEVANCE_FLOOR=0.60` skips the LLM for obvious misses; `NOT_COVERED` or an LLM error → deflect.)* |

**L2 eval (2026-11-02, `eval_brain_routes.py`, both fixture files, L1 in-memory, L2 in-memory retriever):**

| L1 threshold | L2 | In-scope answered (of 22) | Out-of-scope answered (of 20) | L2 first token p50 |
|---|---|---|---|---|
| 0.90 | qwen2.5:3b | 21 | **0** | 412 ms |
| 0.85 | qwen2.5:3b | 22 | 3 (answered by L1 before L2 runs) | 426 ms |

### M4B — Scope gate and human deflection

| ID | Step | Done when |
|----|------|-----------|
| **M4B-13** | Combine gates: L1 hit → stored answer; else (L2 off) → deflect. With L2 on later: L2 in-scope → synthesized answer. | **L1 ship:** two paths (`l1_hit`, `deflect`) on fixtures; L2 path when deferred steps done. |
| **M4B-14** | **Deflection**: on out-of-scope, speak one fixed handoff line (e.g. *"I can only help with questions about where your money is — let me connect you to a human. Goodbye."*) via TTS, then **end the session / close the WS (cut the call)**. | Out-of-scope question → handoff line played → session closes cleanly. |

### M4B — Pipeline integration

| ID | Step | Depends on |
|----|------|------------|
| **M4B-15** | Implement `KnowledgeProcessor` (Pipecat processor) wrapping the decision logic; swap it for `EchoProcessor` in `build_pipeline(...)` behind a config flag (`agent=echo\|brain`). | Pipeline builds with the brain agent; flag switches back to echo. |
| **M4B-16** | Route L1 hits **straight to TTS** (skip LLM). *(L2: stream synthesized answers when M4B-11 done.)* | L1 turns use fixed answer text only; no LLM frames on L1 path. |
| **M4B-17** | **L1 E2E** over WebSocket (`AGENT_MODE=brain`, `BRAIN_ENABLE_L2=false`): in-scope paraphrase → spoken stored answer; out-of-scope → handoff + WS closes. *(Later: combined in-scope → L2.)* | Two paths verified in browser; notes in `docs/latency-log.md`. |

### M4B — Brain query performance metrics

Per-turn and offline baselines for the dual-layer stack. Reuse the M1 latency observer: keep `t0`–`t4` / `t5` for pipeline latency; add a **`brain`** block on the same `metrics` JSON line and WS event.

| Field | When set | Meaning |
|-------|----------|---------|
| `route` | Every brain turn | `l1_hit` \| `l2_rag` \| `deflect` |
| `embed_ms` | L1 or L2 | Query embedding latency (provider or local model) |
| `redis_knn_ms` | L1 hit (always attempted before L2) | Redis vector KNN only (target ~1–2 ms local, excluding embed) |
| `redis_similarity` | After Redis KNN | Best-match cosine similarity |
| `qdrant_search_ms` | L2 only | Qdrant filtered vector search only |
| `llm_first_token_ms` | L2 only | Time from LLM request to first token |
| `brain_ms` | Every brain turn | Final transcript received → agent answer text ready (replaces echo “logic” slice for `agent=brain`) |

| ID | Step | Done when |
|----|------|-----------|
| **M4B-18** | Extend server `MetricsMessage` / `metrics_payload` and client types: optional `brain` object with fields above; echo turns omit `brain`. | Types compile; documented next to `LatencyStages`. |
| **M4B-19** | Instrument L1: time `embed_ms` + `redis_knn_ms` around the router; set `route=l1_hit` when threshold passes. | Unit test: mock Redis client → non-null timings on fixture query. |
| **M4B-20** | **L1 ship:** deflect metrics (`route=deflect`, L2 fields null). *(Deferred:* L2 shape with `qdrant_search_ms` + `llm_first_token_ms`.) | Fixture deflect + L1 hit produce distinct `route` + fields. |
| **M4B-21** | `KnowledgeProcessor` attaches `brain` to WS `metrics`; client panel shows last turn `brain` fields. *(Optional polish:* merge `brain` into stdout turn JSON.) | Speak one L1 question → panel shows `route=l1_hit`, `redis_knn_ms`, `redis_similarity`. |
| **M4B-22** | **L1 ship:** `scripts/bench_brain_queries.py` (or extend): warm Redis; run L1 + deflect fixtures **without** STT/TTS; print p50/p95 for `embed_ms`, `redis_knn_ms`, `brain_ms`. | Script exits 0; baseline row in `docs/latency-log.md` (Qdrant column n/a). |

### M4B — L1-only acceptance checklist *(pass/fail before closing 4B)*

Run with `AGENT_MODE=brain`, `BRAIN_ENABLE_L2=false`, Redis Stack up, index built (`python scripts/build_redis_index.py`).

| # | Check | Pass when |
|---|--------|-----------|
| 1 | **Index health** | `build_redis_index.py` exits 0; RediSearch module present; indexed rows = count of all `embedded_questions`. |
| 2 | **Offline routing** | `eval_l1_threshold.py` on standard + hard-negative YAML: chosen threshold gives **100% precision** on out-of-scope fixtures (no false accepts). |
| 3 | **In-scope E2E** | Browser: paraphrase of a KB intent → spoken stored answer; WS `metrics.extra.brain.route` = `l1_hit`; similarity ≥ threshold. |
| 4 | **Deflect E2E** | Browser: clearly out-of-scope question → handoff line spoken → session closes within ~8s (WS disconnect). `route=deflect`. |
| 5 | **No LLM on L1 path** | L1 turn completes with fixed FAQ text only (no streamed LLM tokens); `llm_first_token_ms` absent/null. |
| 6 | **Latency sanity** | One L1 turn: `redis_knn_ms` present; offline bench p50 `redis_knn_ms` documented (target ~1–5 ms local excluding embed). |
| 7 | **Flag rollback** | `AGENT_MODE=echo` restores echo agent without code changes. |

**Milestone 4B acceptance (L1 ship):** checklist **1–7** pass + **M4B-01–M4B-07**, **M4B-13–M4B-17** (two-path E2E), **M4B-14**, **M4B-21** (WS brain metrics). **Not required for L1 close:** M4B-08–M4B-12, M4B-11, full three-path E2E, Qdrant columns in latency-log.

---

## Milestone 5 — Latency tuning and benchmark

### M5 — Measurement harness

| ID | Step | Done when |
|----|------|-----------|
| **M5-01** | Script or checklist: **30 utterances** (mix 3 / 10 / 25 words). | List stored in `docs/latency-log.md`. |
| **M5-02** | Record p50 / p95 **perceived latency** (plan §2). | Table filled. |
| **M5-03** | Verify criteria 3–7 (glitches, 10 min session, logging completeness). With `agent=brain`, every turn log includes `brain.route` and path-relevant DB timings. | Checklist in latency-log. |

### M5 — Tuning (one knob per step)

| ID | Step | Done when |
|----|------|-----------|
| **M5-04** | Tune VAD silence timeout; re-run 30 utterances; log before/after. | Row in latency-log. |
| **M5-05** | Tune Deepgram endpointing; re-run; log. | Row in latency-log. |
| **M5-06** | Tune playback buffer depth; re-run; log. | Row in latency-log. |
| **M5-07** | Compare 20 ms vs 40 ms uplink frames; re-run; log. | Row in latency-log. |
| **M5-08** | Ensure TTS request fires immediately on final transcript; re-run; log. | Row in latency-log. |
| **M5-09** | Confirm server region + connection reuse; re-run; log. | Row in latency-log. |
| **M5-10** | *(Optional Phase 1b)* Swap in WebRTC transport; compare p50/p95 to WebSocket. | Note in latency-log. |

### M5 — Brain / DB query performance

| ID | Step | Done when |
|----|------|-----------|
| **M5-11** | **L1 ship:** 30-utterance E2E (L1 paraphrases + out-of-scope deflects); aggregate p50/p95 for `embed_ms`, `redis_knn_ms`, `brain_ms` by `route`. *(Deferred:* L2 routes + `qdrant_search_ms` / `llm_first_token_ms`.) | Table in `docs/latency-log.md`. |
| **M5-12** | **L1 ship:** isolated Redis baseline from M4B-22; note docker vs host, variant count, embedding provider. Target: `redis_knn_ms` p95 **≤ 5 ms** local (excluding embed). *(Deferred:* Qdrant SLO.) | SLO row in latency-log. |
| **M5-13** | Confirm L1 turns omit LLM (`llm_first_token_ms` absent); tie `brain_ms` + pipeline stages to perceived latency. *(Deferred:* L1 vs L2 comparison.) | Short note in latency-log. |

**Milestone 5 acceptance:** Plan §2 success table targets met or documented; `docs/latency-log.md` complete for **L1 brain metrics (M5-11–M5-13 as scoped above)**. Full dual-layer tables when L2 is implemented.

---

## Milestone 6 — Definition of done (wrap-up)

| ID | Step | Done when |
|----|------|-----------|
| **M6-01** | README: run client + server in **≤ 5 commands** (include env setup pointer). | Another person can follow it. |
| **M6-02** | Pin all dependency versions (client + server). | Lockfiles / pyproject pins committed. |
| **M6-03** | Known limitations section (headphones, browsers, network). | Written in README. |
| **M6-04** | Check off plan §10 definition of done. | All boxes ticked. |

---

## Suggested “next step” right now

If the repo still has the **old** layout from the first scaffolding pass, start with **M0-01 → M0-02**.  
If layout is already aligned, start with **M0-04** (Vite client) or **M0-07** (Python server) — whichever side you prefer; finish all of M0 before M1.

---

## Quick index (IDs only)

```
M0-01 … M0-17   setup, providers
M1-01 … M1-17   server pipeline + bench
M2-01 … M2-14   client loopback
M3-01 … M3-19   WebSocket E2E
M4-01 … M4-11   barge-in + robustness
M4B-01 … M4B-22 knowledge brain (L1 Redis now; M4B-08–12 L2 deferred)
M5-01 … M5-13   benchmark + tuning (+ DB query performance)
M6-01 … M6-04   docs + DoD
```

**Total:** 94 micro-steps (implement **one ID at a time**).
