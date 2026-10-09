# Aura Assistant - Operations & Runbook Guide

## 1. Prerequisites & Environment Setup

Ensure GPU drivers, Docker daemon, and local microphone/speaker devices are accessible.

### Step 1: Start Ollama and Verify GPU Availability
```bash
ollama serve > /dev/null 2>&1 &
ollama pull qwen3.5:4b
ollama pull nomic-embed-text
ollama pull qwen3-coder:30b
```

### Step 2: Build Local Hardened Sandbox Images
Pre-builds the sandbox runner images to eliminate runtime latency or image-pull delays:
```bash
./sandbox/build.sh
```

### Step 3: Launch the Privileged Host Sandbox Broker
Listens on `/run/aura/sandbox.sock` and manages ephemeral Docker containers:
```bash
sudo python3 daemons/sandbox/broker.py &
```

### Step 4: Initialize Database Migrations
Runs Alembic migrations for Chroma metadata and audit logs:
```bash
alembic upgrade head
```

### Step 5: Boot the FastAPI Application Core
Starts the core server with WebSocket IPC and SSE streaming:
```bash
uvicorn aura_assistant.api.app:app --host 127.0.0.1 --port 8000 --workers 1 &
```

### Step 6: Launch Native Host Voice Daemon
Starts PortAudio capture, openWakeWord, Silero VAD, and Faster-Whisper ASR:
```bash
python3 daemons/voice/daemon.py &
```

### Step 7: Start Frontend Developer Dashboard
```bash
cd frontend && npm run dev
```

---

## 2. Test & Verification Suite

Execute the following commands to validate security constraints and performance SLAs:

```bash
# Verify sandbox isolation: must confirm zero outbound traffic and path containment
pytest tests/security/test_sandbox.py -v

# Verify that model router locks 4B in memory and avoids 30B VRAM overflow
pytest tests/unit/llm/test_residency.py -v

# Test synthetic prompt injection payloads against the AST Patch Engine
pytest tests/security/test_patch_engine.py -v
```
