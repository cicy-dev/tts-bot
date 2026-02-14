#!/bin/bash
export PATH="/usr/bin:/usr/local/bin:$PATH"
LAST=""
while true; do
  LEN=$(curl-rpc exec_js 'win_id=1' 'code=document.querySelectorAll(".bubbles-inner .bubble").length' 2>/dev/null | grep -v "^-" | tr -d ' \n')
  if [ -n "$LEN" ] && [ "$LEN" -gt 0 ] 2>/dev/null; then
    IDX=$((LEN-1))
    NOW=$(curl-rpc exec_js 'win_id=1' "code=document.querySelectorAll('.bubbles-inner .bubble')[$IDX].innerText.substring(0,300)" 2>/dev/null | grep -v "^-" | tr -s '\n' ' ')
    if [ -n "$NOW" ] && [ "$NOW" != "$LAST" ]; then
      LAST="$NOW"
      echo "[$(date '+%H:%M:%S')] $NOW" >> /tmp/chat_latest.txt
    fi
  fi
  sleep 10
done
