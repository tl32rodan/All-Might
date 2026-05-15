#!/bin/bash
set -euo pipefail

# SessionStart hook for Claude Code on the web. Installs the dev deps the
# All-Might test suite needs. Skips when running outside a remote container.

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

# The test suite is invoked as `PYTHONPATH=src python -m pytest tests/` per
# CLAUDE.md. Persist the path for every command in this session.
echo 'export PYTHONPATH="$CLAUDE_PROJECT_DIR/src"' >> "$CLAUDE_ENV_FILE"

# pyproject.toml lists `smak` as a runtime dep, but smak is invoked as a
# subprocess (see src/allmight/bridge/smak_bridge.py) and is not published
# to PyPI, so `pip install -e .[dev]` cannot resolve it. Install the
# packages the suite actually imports instead.
pip install --quiet \
  pytest \
  pytest-cov \
  click \
  jinja2 \
  pyyaml \
  rich
