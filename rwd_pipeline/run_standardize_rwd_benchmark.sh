#!/usr/bin/env bash
set -a
source "$(dirname "$0")/../.env"
set +a
python -m rwd_pipeline.standardize_rwd_benchmark --use-llm "$@"
