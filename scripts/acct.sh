#!/usr/bin/env bash
# Chọn Python 3 có sẵn (macOS/Linux: python3; Windows Git Bash: python hoặc py -3) rồi chạy claude_acct.py.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
for cand in "python3" "python" "py -3"; do
  if $cand -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' >/dev/null 2>&1; then
    PYTHONIOENCODING=utf-8 exec $cand -I "$DIR/claude_acct.py" "$@"
  fi
done
echo "Lỗi: không tìm thấy Python 3.8+ (python3 / python / py)." >&2
exit 1
