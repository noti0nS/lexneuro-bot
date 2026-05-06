#!/bin/bash
set -e

# Render deploys: config.yaml is passed via CONFIG_YAML_B64 (base64-encoded)
if [ -n "$CONFIG_YAML_B64" ]; then
    echo "$CONFIG_YAML_B64" | base64 -d > /app/config.yaml
    echo "config.yaml written from CONFIG_YAML_B64 env var"
fi

exec python main.py
