#!/bin/bash

TARGET_PANE="%35"
LAST_LINE=""
DEBUG=false

# 解析参数
for arg in "$@"; do
    case $arg in
        once)
            CURRENT=$(tmux capture-pane -t cicy:kiro -p 2>/dev/null | tail -1)
            echo "$CURRENT"
            exit 0
            ;;
        --debug)
            DEBUG=true
            ;;
    esac
done

while true; do
    CURRENT=$(tmux capture-pane -t cicy:kiro -p 2>/dev/null | tail -1)
    
    if [[ "$DEBUG" == true ]]; then
        # debug 模式：每次都发送 cap
        tmux send-keys -t "$TARGET_PANE" "cap" C-m 2>/dev/null
        [[ "$DEBUG" == true ]] && echo "[DEBUG $(date '+%H:%M:%S')] Sent cap"
    elif [[ "$CURRENT" != *"Thinking"* ]] && [[ "$CURRENT" != "$LAST_LINE" ]] && [[ -n "$CURRENT" ]]; then
        # 正常模式：只在变化时发送
        tmux send-keys -t "$TARGET_PANE" "cap" C-m 2>/dev/null
        LAST_LINE="$CURRENT"
    fi
    
    sleep 5
done
