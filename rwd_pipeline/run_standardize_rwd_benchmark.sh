#!/usr/bin/env bash
export DEEPSEEK_API_KEY='***'
python -m rwd_pipeline.standardize_rwd_benchmark --use-llm "$@"
