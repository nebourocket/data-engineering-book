echo 'print("おはよう、ねぼすけ商店")' > hello.py
docker run --rm -v "$PWD":/w -w /w de-book-dev python hello.py
