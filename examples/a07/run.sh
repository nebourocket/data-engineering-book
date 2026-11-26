docker run --rm \
  -v "$PWD":/w -w /w de-book-advanced pytest -q examples/a07
docker run --rm \
  -v "$PWD":/w -w /w de-book-advanced python examples/a07/demo.py
