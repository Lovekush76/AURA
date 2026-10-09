#!/usr/bin/env bash
set -e

echo "Building Aura hardened sandbox images..."
docker build -t aura-sandbox-python:latest ./sandbox/python
docker build -t aura-sandbox-node:latest ./sandbox/node

echo "Sandbox images built successfully."
