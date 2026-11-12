#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SITE_DIR="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
export PATH="/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin"
PYTHON_BIN="/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"
mkdir -p "$SITE_DIR/.publication-sync"
LOG_FILE="$SITE_DIR/.publication-sync/latest-render.log"
exec > "$LOG_FILE" 2>&1
trap 'status=$?; if [ "$status" -ne 0 ]; then /usr/bin/osascript -e '\''display alert "Website update stopped" message "Check .publication-sync/latest-render.log in your website folder. Your existing research page was not published." as warning'\'' || true; fi' EXIT
cd "$SITE_DIR"
"$PYTHON_BIN" "$SCRIPT_DIR/refresh_publications.py" --site "$SITE_DIR"
/usr/local/bin/quarto render
/usr/bin/osascript -e 'display notification "Publication data refreshed and website rendered. Ready to review before your normal GitHub push." with title "Website ready"' || true
