# Aura Assistant - Business Requirements Document (BRD v3.5)

## 1. System Architecture Diagram

```text
+----------------------------------------------------------------------------------------------------+
|                                      FRONTEND / PERIPHERAL LAYER                                   |
|  React 18 + Vite HUD (Monaco Editor, Visualizer Canvas, SplitPane) | Microphone Array | Speakers   |
+-------------------------------------------------+--------------------------------------------------+
                                                  |
                    +-----------------------------+-----------------------------+
                    | Host Audio Device Loop                                    | Authenticated WebSockets
                    v                                                           v
+-----------------------------------------------+   Unix IPC Socket   +------------------------------+
|             HOST VOICE DAEMON                 | ------------------> |      FASTAPI CORE API        |
|  - openWakeWord ("Hey Aura" Engine)           |  Transcripts +      |  - Intent Routing & Memory   |
|  - Silero VAD (Dynamic Endpointing)           |  Biometric Scores   |  - RAG & Knowledge Pipeline  |
|  - Pyannote (x-vector Speaker Verification)   |  (Zero Raw Audio)   |  - Tool Registry & Approvals |
|  - Faster-Whisper (int8 ASR Engine)           | <------------------ |  - Git Checkpoint Engine     |
|  - Piper Neural TTS (Sentence Streaming)      |  Text Stream Out    |  - Session Context Broker    |
+-----------------------------------------------+                     +--------------+---------------+
                                                                                     |
                    +----------------------------------------------------------------+
                    |
                    +------------------------------------+
                    | Localhost (127.0.0.1:11434)        | Unix Socket (/run/aura/sandbox.sock)
                    v                                    v
+-----------------------------------------------+   +------------------------------------------------+
|             OLLAMA MODEL ENGINE               |   |            HOST SANDBOX BROKER                 |
|  - Pinned: qwen3.5:4b (Voice/Router) ~3.2 GB  |   |  - Independent Host Daemon (API has no docker) |
|  - Pinned: nomic-embed-text (RAG) ~0.5 GB     |   |  - Spawns Ephemeral python:3.12-slim / node    |
|  - Swapped: qwen3-coder:30b (Coding) ~18.8 GB |   |  - cgroup Enforcement: 1 CPU, 512MB, 128 PIDs  |
|  - VRAM Arbiter prevents Voice Model Eviction |   |  - Network Profiles: none | registry-proxy     |
+-----------------------------------------------+   +------------------------------------------------+
```

---

## 2. Scope & Traceability Matrix

| Epic ID | Domain | MoSCoW | Objective & Functional Scope |
| :--- | :--- | :--- | :--- |
| **E-01** | Acoustic Core | Must | Low-power wake word ("Hey Aura"), Silero VAD, Pyannote x-vector speaker identification, Faster-Whisper ASR, Piper neural TTS. |
| **E-02** | Multi-Model Routing | Must | Intent classification routing voice queries to fast models (`qwen3.5:4b`), coding tasks to `qwen3-coder:30b`, and architecture/debugging to `deepseek-r1:14b`. |
| **E-03** | Sandboxed Workspace | Must | Host sandbox broker for ephemeral code execution, network isolation profiles (`none`, `registry`), and Git-backed diff application. |
| **E-04** | Knowledge Engine | Must | Document RAG (PDF/DOCX/code), semantic chunking, ChromaDB integration, `nomic-embed-text` embeddings, and strict attribution citations. |
| **E-05** | Episodic Memory | Should | Asynchronous background extraction of personal facts and preferences into semantic vectors, injected contextually on subsequent queries. |
| **E-06** | Glassmorphism HUD | Must | React 18, Vite, Tailwind CSS, Monaco Editor split-pane, Framer Motion telemetry HUD, and bidirectional WebSocket/SSE streaming. |
| **E-07** | Enterprise Hardening | Must | Scoped API keys, Argon2id passwords, append-only immutable audit logging, and zero outbound network calls by default. |

---

## 3. Functional Requirements

### 3.1 Voice & Acoustic Engine (FR-VCE)
- **FR-VCE-01 (Wake Word):** The host daemon must continuously process 16 kHz mono audio via openWakeWord with $< 300\text{ ms}$ detection latency and a false positive rate $< 1\text{ per }10\text{ hours}$ of ambient sound.
- **FR-VCE-02 (VAD Segmentation):** Silero VAD must compute real-time speech probabilities, cutting audio frames upon detecting $600\text{ ms}$ of trailing silence, prepending a $300\text{ ms}$ pre-roll buffer to preserve initial syllables.
- **FR-VCE-03 (Speaker Verification):** Captured speech must be transformed into a 512-dimensional x-vector via Pyannote.audio and scored via Cosine Similarity against `data/audio_profiles/user.bin`:
  $$\text{Score} = \frac{\mathbf{u} \cdot \mathbf{v}}{\Vert{}\mathbf{u}\Vert{}\Vert{}\mathbf{v}\Vert{}}$$
  If $\text{Score} < 0.85$, sensitive tools are stripped from the invocation context.
- **FR-VCE-04 (Streaming Synthesis):** Responses from the LLM must be tokenized into sentence boundaries via regex/heuristics, rendered into PCM chunks using Piper, and streamed to PortAudio/ALSA before the complete response is generated.

### 3.2 Developer Workspace & Code Execution (FR-DEV)
- **FR-DEV-01 (Sandbox Daemon):** Code execution must occur inside isolated Docker containers managed by `daemons/sandbox/broker.py`. The API container must not possess Docker socket permissions.
- **FR-DEV-02 (cgroup Isolation):** Every execution sandbox must apply:
  - `--network none`
  - `--memory 512m`
  - `--memory-swap 512m`
  - `--cpus 1.0`
  - `--pids-limit 128`
  - `--read-only`
  - `--tmpfs /tmp:rw,size=64m`
  - `--cap-drop ALL`
  - `--security-opt no-new-privileges`
- **FR-DEV-03 (Unified Diff Review):** The system must disallow raw file writes on existing repositories. Proposed modifications must be emitted as unified diffs, validated against the project syntax tree, previewed in the UI, and committed to Git upon approval.

### 3.3 Model Arbitration & Intent Routing (FR-LLM)
- **FR-LLM-01 (Precedence Engine):** The model router must follow a strict resolution ladder:
  1. Explicit User Override (`/model <name>`).
  2. Input Modality Rule (Voice channel strictly selects the pinned voice slot).
  3. Structural Heuristics (Active workspace, fenced code blocks, stack traces select code).
  4. Fast-Model Fallback Classifier (`route_intent.md` via `qwen3.5:4b`, $\le 20\text{ tokens}$).
- **FR-LLM-02 (Residency Control):** When loading heavy models (`qwen3-coder:30b`), the arbiter must enforce serialized loading and verify that `qwen3.5:4b` remains locked in memory (`keep_alive: -1`).

---

## 4. Performance & Security SLA Target Metrics

| Metric | Target Threshold |
| :--- | :--- |
| **Voice Latency** | $\le 1.2\text{ s}$ (VAD end-of-speech to first synthesized audio frame, p95) |
| **Text TTFT** | $\le 800\text{ ms}$ (Warm fast-router model, p95) |
| **Code Iteration** | $\le 3.5\text{ s}$ (Sandbox initialization, execution, stdout capture) |
| **Sandbox Security** | 0 root escalations, 0 unapproved filesystem writes, 0 network leaks |
| **Data Sovereignty** | 0 unauthorized outbound packets (Strict Zero-Egress) |
| **System Memory** | $\le 23.0\text{ GB}$ VRAM consumed during dual-model operation |

---

## 5. Architectural Directory Layout

```
aura/
├── Makefile                                   # Complete orchestration: setup, run, test, listen
├── pyproject.toml                             # Strict dependencies, tool configs (ruff, mypy, pytest)
├── docker-compose.yml                         # Containerized API, ChromaDB, Squid Proxy
├── .env.example                               # Production configuration baseline
├── sandbox/
│   ├── build.sh                               # Pre-builds sandbox runner images
│   ├── python/Dockerfile                      # Hardened python:3.12-slim non-root runtime
│   ├── node/Dockerfile                        # Hardened node:20-slim non-root runtime
│   └── egress/
│       ├── squid.conf                         # Allow-list proxy for registry network mode
│       └── allowlist.txt                      # Explicit package registries (pypi.org, npmjs.org)
├── configs/
│   ├── models.yaml                            # VRAM residency limits, model slots, fallback ladder
│   ├── tools.yaml                             # Sensitivity classes (public/personal/critical)
│   ├── voice.yaml                             # ASR, TTS, VAD, WakeWord configuration
│   └── prompts/
│       ├── system/
│       │   ├── voice.md                       # High-density spoken-output persona
│       │   └── coder.md                       # Agentic planning, patch-generation instructions
│       └── tasks/
│           ├── route_intent.md                # Fast classification prompt
│           └── memory_extract.md              # Episodic fact extraction schema
├── daemons/                                   # HOST-NATIVE PRIVILEGED PROCESSES
│   ├── voice/
│   │   ├── daemon.py                          # Supervised mic listener, VAD, wake word
│   │   ├── biometrics.py                      # Pyannote extraction & cosine comparator
│   │   ├── audio_io.py                        # PortAudio ring buffer & hardware mute control
│   │   └── ipc_client.py                      # Authenticated client streaming to API socket
│   └── sandbox/
│       ├── broker.py                          # Privileged host server listening on Unix socket
│       └── cgroups.py                         # Linux cgroup v2 & Docker capability constraints
├── src/
│   └── aura_assistant/
│       ├── __init__.py
│       ├── container.py                       # Dependency Injection Composition Root
│       ├── core/
│       │   ├── llm/
│       │   │   ├── provider.py                # Ollama API asynchronous client
│       │   │   ├── router.py                  # Intent parsing & slot selection
│       │   │   └── residency.py               # VRAM monitoring and keep-alive arbiter
│       │   ├── voice/
│       │   │   ├── gating.py                  # Sensitivity checking against biometric match
│       │   │   └── formatter.py               # Cleans Markdown, URLs, code for speech
│       │   ├── workspace/
│       │   │   ├── patch_engine.py            # Unified diff parser & AST syntax validator
│       │   │   ├── checkpoints.py             # Git-backed rollback manager
│       │   │   └── indexer.py                 # Tree-sitter AST code chunker for RAG
│       │   ├── memory/
│       │   │   └── episodic.py                # Asynchronous fact extractor & Chroma writer
│       │   └── tools/
│       │       ├── base.py                    # Tool abstract class, Pydantic metadata
│       │       ├── registry.py                # Dynamic discovery & permission validation
│       │       └── builtin/
│       │           ├── code_exec.py           # Dispatches run specs to Sandbox Broker
│       │           ├── filesystem.py          # Jailed project file operations
│       │           └── home_assistant.py      # Local IoT device controllers
│       ├── services/
│       │   ├── chat_service.py                # Chat orchestration, event streams
│       │   └── workspace_service.py           # Workspace synchronization
│       └── api/
│           ├── app.py                         # FastAPI initialization, CORS, Lifespan
│           ├── routers/
│           │   ├── chat.py                    # SSE streaming endpoint (/api/v1/chat/stream)
│           │   ├── voice_ipc.py               # Authenticated WebSocket (/api/v1/voice/ipc)
│           │   └── workspace.py               # File tree, patch application, run logs
│           └── middleware/
│               └── auth.py                    # Scoped API tokens & security boundaries
└── frontend/                                  # REACT 18 + VITE INTERFACE
    ├── package.json
    ├── vite.config.ts
    └── src/
        ├── App.tsx                            # SplitPane layout, Telemetry HUD integration
        ├── components/
        │   ├── HUD/
        │   │   ├── Visualizer.tsx             # Canvas-based circular audio reactor
        │   │   └── StatusIndicator.tsx        # VRAM status & model residency badge
        │   ├── Workspace/
        │   │   ├── MonacoViewer.tsx           # Monaco editor instance
        │   │   └── DiffReview.tsx             # Hunk-by-hunk acceptance panel
        │   └── Chat/
        │       └── Terminal.tsx               # Monospace streaming output pane
        └── store/
            ├── chatStore.ts                   # Zustand conversation state
            ├── workspaceStore.ts              # Zustand Monaco buffers & diff proposals
            └── voiceStore.ts                  # Real-time telemetry & VAD status
```
