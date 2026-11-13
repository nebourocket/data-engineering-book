docker run --rm -it de-book-dev python
docker run --rm -v "$PWD":/w -w /w de-book-dev python 01_hello.py
docker run --rm -it -v "$PWD":/w -w /w de-book-dev python 06_input.py
