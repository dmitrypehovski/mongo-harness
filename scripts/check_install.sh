#!/usr/bin/env bash
# Prove the built artefact installs and runs, in an environment this project did not build.
set -euo pipefail
WORK=/root/.hermes/profiles/work2/cache/scratch/piptest2
rm -rf "$WORK"
python3 -m venv "$WORK"
"$WORK/bin/pip" install -q --upgrade pip >/dev/null

echo "=== установка из wheel:"
"$WORK/bin/pip" install -q /root/hack/mongo-harness/dist/mongo_harness-0.1.0-py3-none-any.whl
"$WORK/bin/pip" show mongo-harness | grep -E "^(Name|Version|License|Requires)"

echo "=== команда mh:"
"$WORK/bin/mh" --help 2>&1 | head -3

echo "=== страница продукта внутри установки:"
"$WORK/bin/python" -c "
import pathlib, mh.web.app as app
page = pathlib.Path(app.__file__).parent / 'index.html'
print('index.html:', page.exists(), page.stat().st_size if page.exists() else 0, 'байт')
print('HOST/PORT:', app.HOST, app.PORT)
"

echo "=== тесты из установленного sdist:"
"$WORK/bin/pip" install -q pytest
tmp=$(mktemp -d)
tar -xzf /root/hack/mongo-harness/dist/mongo_harness-0.1.0.tar.gz -C "$tmp"
cd "$tmp/mongo_harness-0.1.0"
"$WORK/bin/python" -m pytest tests/ -q 2>&1 | tail -2
