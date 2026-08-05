#!/usr/bin/env bash
export DEEPSEEK_API_KEY='***'
python standardize_rwd_benchmark.py --use-llm "$@"
