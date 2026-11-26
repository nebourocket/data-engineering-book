docker run --rm \
  -v "$PWD":/w -w /w de-book-advanced pytest -q examples/a08
docker run --rm \
  -v "$PWD":/w -w /w de-book-advanced python examples/a08/demo.py
docker run --rm \
  -v "$PWD":/w -w /w de-book-advanced python examples/a08/official_check.py
