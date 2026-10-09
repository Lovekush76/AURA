#!/bin/bash
set -e
echo "=========================================================="
echo "Initializing Aura Assistant Environment on GitHub..."
echo "=========================================================="

python -m pip install --upgrade pip
pip install fastapi uvicorn httpx pydantic websockets sqlalchemy sounddevice numpy rich

echo "Setting up Frontend..."
cd frontend
npm install
npm run build
cd ..

echo "Installing Ollama for sovereign local inference..."
if ! command -v ollama &> /dev/null; then
    curl -fsSL https://ollama.com/install.sh | sh || true
fi

echo "=========================================================="
echo "Aura Assistant is ready! Run: ./run_cloud.sh"
echo "=========================================================="
