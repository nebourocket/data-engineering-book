docker run --rm \
  -v "$PWD":/w -w /w de-book-advanced pytest -q examples/a06
docker run --rm \
  -v "$PWD":/w -w /w de-book-advanced python examples/a06/demo.py
