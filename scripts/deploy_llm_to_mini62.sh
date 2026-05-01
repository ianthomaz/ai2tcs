#!/usr/bin/env bash
# Legacy filename — deploy is always local Docker on this machine (no SSH/rsync).
exec "$(cd "$(dirname "$0")" && pwd)/deploy_llm.sh"
