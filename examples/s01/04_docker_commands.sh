docker --version
docker run --rm hello-world
git clone https://github.com/nebourocket/data-engineering-book.git
cd data-engineering-book
docker build -t de-book-dev .
docker run --rm de-book-dev python --version
