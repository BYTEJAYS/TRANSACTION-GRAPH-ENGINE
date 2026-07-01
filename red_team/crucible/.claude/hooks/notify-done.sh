#!/usr/bin/env bash
# Stop hook — fires when Claude finishes its response.
# Sends a desktop notification so you don't have to watch the terminal.
# Works on macOS and Linux (with notify-send).
# Silent failure — if notifications don't work, nothing breaks.
# IMPORTANT: Only stdout goes to Claude. Use stderr for debug. Never echo to stdout.

MESSAGE="${1:-Claude finished}"

# macOS
if command -v osascript &>/dev/null; then
  osascript -e "display notification \"$MESSAGE\" with title \"Claude Code\"" 2>/dev/null || true
  exit 0
fi

# Linux (requires libnotify-bin)
if command -v notify-send &>/dev/null; then
  notify-send "Claude Code" "$MESSAGE" 2>/dev/null || true
  exit 0
fi

# Windows (Git Bash / WSL)
if command -v powershell.exe &>/dev/null; then
  powershell.exe -Command "
    [Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,ContentType=WindowsRuntime] | Out-Null
    \$xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent('ToastText01')
    \$xml.GetElementsByTagName('text')[0].AppendChild(\$xml.CreateTextNode('Claude Code: $MESSAGE')) | Out-Null
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Claude Code').Show(\$xml)
  " 2>/dev/null || true
  exit 0
fi

exit 0
