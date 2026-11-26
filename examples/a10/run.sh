set -euo pipefail
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v /etc/passwd:/etc/passwd:ro \
  -v "$PWD":/w -w /w de-book-advanced pytest -q examples/a10
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v /etc/passwd:/etc/passwd:ro \
  -v "$PWD":/w -w /w de-book-advanced python examples/a10/demo.py
