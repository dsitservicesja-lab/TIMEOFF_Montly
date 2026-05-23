#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/timeoff"

if [[ ! -d "${APP_DIR}/.git" ]]; then
  echo "Error: ${APP_DIR} is not a git repository."
  exit 1
fi

cd "${APP_DIR}"
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
git pull --ff-only origin "${BRANCH}"
