#!/usr/bin/env bash

HEARTBEAT_FILE=$1
INTERVAL=$2

current_date=$(date +%s)
if [ -f "$HEARTBEAT_FILE" ]; then
  m_time=$(stat --format='%Y' "$HEARTBEAT_FILE")
  if (((current_date - m_time) < INTERVAL)); then
    exit 0
  fi
fi
exit 255
