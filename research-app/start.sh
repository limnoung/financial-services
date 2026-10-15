#!/bin/sh
set -eu
cd -- "$(dirname -- "$0")"
exec python3 -X utf8 start.py "$@"
