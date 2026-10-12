#!/usr/bin/env bash
# Build the distributions and check what actually landed inside them.
set -euo pipefail
cd /root/hack/mongo-harness
rm -rf dist build ./*.egg-info

.venv/bin/python -m build >/dev/null 2>&1
echo "=== собрано:"
ls -1 dist/

tar -tzf dist/mongo_harness-0.1.0.tar.gz > /tmp/sdist-files.txt
echo "=== файлов в sdist:"
wc -l < /tmp/sdist-files.txt

echo "=== нужное на месте:"
for f in LICENSE pyproject.toml MANIFEST.in README.md DATASETS.md mh/cli.py mh/web/index.html \
         tests/test_core.py datasets/theaters.json examples/foreign_harness.py \
         scripts/export_video_data.py; do
  if grep -qx "mongo_harness-0.1.0/$f" /tmp/sdist-files.txt; then
    echo "  есть: $f"
  else
    echo "  НЕТ:  $f"
  fi
done

echo "=== лишнее (ожидается 0 строк):"
grep -E 'node_modules|\.mp4|\.archive|__pycache__' /tmp/sdist-files.txt | wc -l

echo "=== проверка метаданных:"
.venv/bin/twine check dist/* 2>&1 | tail -3
