#!/usr/bin/env bash
set -euo pipefail

DOCKER_FLAG=false
MODEL=""
PORT=11434

while [[ $# -gt 0 ]]; do
    case "$1" in
        --docker) DOCKER_FLAG=true; shift ;;
        --model)  MODEL="$2"; shift 2 ;;
        *)        echo "Unknown arg: $1"; exit 1 ;;
    esac
done

if [[ -z "$MODEL" ]]; then
    echo "--model is required"
    exit 1
fi

CMD=("llama-server" "-hf" "$MODEL" "--port" "$PORT")
$DOCKER_FLAG && CMD+=("--host" "0.0.0.0")

echo "${CMD[@]}"
exec "${CMD[@]}"
