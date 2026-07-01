#!/usr/bin/env bash
# Notification hook — fires when Claude is waiting for your input or permission.
# Different from notify-done.sh (Stop event) — this fires MID-task when Claude pauses.
# Perfect for long-running tasks: step away, get notified when action needed.
#
# Wire up in settings.json:
# "Notification": [{ "matcher": "", "hooks": [{ "type": "command", "command": "~/.claude/hooks/notify-attention.sh" }] }]
#
# STDOUT = JSON parsed by Claude. STDERR = debug only. Never plain-echo to stdout.

MESSAGE="Claude needs your attention"
TITLE="Claude Code"

# macOS
if command -v osascript &>/dev/null; then
  osascript -e "display notification \"$MESSAGE\" with title \"$TITLE\"" 2>/dev/null || true
  exit 0
fi

# Linux (requires libnotify-bin: sudo apt install libnotify-bin)
if command -v notify-send &>/dev/null; then
  notify-send "$TITLE" "$MESSAGE" --urgency=normal 2>/dev/null || true
  exit 0
fi

# Windows (Git Bash / WSL)
if command -v powershell.exe &>/dev/null; then
  powershell.exe -Command "
    Add-Type -AssemblyName System.Windows.Forms
    \$notify = New-Object System.Windows.Forms.NotifyIcon
    \$notify.Icon = [System.Drawing.SystemIcons]::Information
    \$notify.Visible = \$true
    \$notify.ShowBalloonTip(3000, '$TITLE', '$MESSAGE', [System.Windows.Forms.ToolTipIcon]::Info)
  " 2>/dev/null || true
  exit 0
fi

exit 0
