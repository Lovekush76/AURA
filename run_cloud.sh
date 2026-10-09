#!/bin/bash
echo "Starting Ollama daemon in background..."
ollama serve > /tmp/ollama.log 2>&1 &
sleep 2

echo "Pulling high-speed model qwen2.5:0.5b..."
ollama pull qwen2.5:0.5b || true

echo "Starting Aura FastAPI Core on port 8000..."
export PYTHONPATH="src:."
python -m uvicorn aura_assistant.api.app:app --host 0.0.0.0 --port 8000 &

echo "Starting Aura HUD Frontend on port 5173..."
cd frontend
npm run dev -- --host 0.0.0.0 --port 5173
