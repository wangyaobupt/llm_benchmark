#!/usr/bin/env bash
export DEEPSEEK_API_KEY='***'
python -m rwd_pipeline.clean_rwd_benchmark "$@"
