#!/bin/bash
# DEEPUTIN Auto-sync script
# This script commits all changes and pushes them to GitHub.

cd "$(dirname "$0")"

# Check for changes
if [[ -n $(git status -s) ]]; then
    echo "Found changes, syncing to GitHub..."
    git add .
    git commit -m "Auto-sync: $(date +'%Y-%m-%d %H:%M:%S')"
    git push origin main
    echo "Sync complete."
else
    echo "No changes detected."
fi
