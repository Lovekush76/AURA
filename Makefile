.PHONY: all setup run-ollama build-sandbox run-broker run-api run-voice run-frontend test test-security test-residency test-patch-engine

# Complete Orchestration for Aura Assistant

setup:
	@echo "Setting up Aura environment..."
	pip install -e .
	cd frontend && npm install

run-ollama:
	@echo "Starting Ollama server & pulling models..."
	ollama serve > /dev/null 2>&1 &
	ollama pull qwen3.5:4b
	ollama pull nomic-embed-text
	ollama pull qwen3-coder:30b

build-sandbox:
	@echo "Building local hardened sandbox runner images..."
	bash ./sandbox/build.sh

run-broker:
	@echo "Launching Host Sandbox Broker..."
	sudo python3 daemons/sandbox/broker.py &

migrate:
	@echo "Running database migrations..."
	alembic upgrade head

run-api:
	@echo "Booting FastAPI Application Core..."
	uvicorn aura_assistant.api.app:app --host 127.0.0.1 --port 8000 --workers 1

run-voice:
	@echo "Launching Native Host Voice Daemon..."
	python3 daemons/voice/daemon.py

run-frontend:
	@echo "Starting Frontend HUD..."
	cd frontend && npm run dev

test: test-security test-residency test-patch-engine

test-security:
	pytest tests/security/test_sandbox.py -v

test-residency:
	pytest tests/unit/llm/test_residency.py -v

test-patch-engine:
	pytest tests/security/test_patch_engine.py -v
