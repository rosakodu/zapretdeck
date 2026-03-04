#!/bin/bash
# Script to compile Qt translation files

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
I18N_DIR="$BASE_DIR/i18n"

if [ ! -d "$I18N_DIR" ]; then
    echo "Error: i18n directory not found: $I18N_DIR"
    exit 1
fi

# Find lrelease command
if command -v lrelease-qt6 >/dev/null 2>&1; then
    LRELEASE_CMD="lrelease-qt6"
elif command -v lrelease >/dev/null 2>&1; then
    LRELEASE_CMD="lrelease"
else
    echo "Error: lrelease not found. Install qt6-tools or qt5-tools"
    exit 1
fi

echo "Compiling translation files..."
for ts_file in "$I18N_DIR"/*.ts; do
    if [ -f "$ts_file" ]; then
        qm_file="${ts_file%.ts}.qm"
        echo "  Compiling $(basename "$ts_file") -> $(basename "$qm_file")"
        $LRELEASE_CMD "$ts_file" -qm "$qm_file" || {
            echo "  Error: Failed to compile $ts_file"
            exit 1
        }
    fi
done

echo "Translation files compiled successfully!"

