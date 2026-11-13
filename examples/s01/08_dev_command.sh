alias DEV='docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD":/w -w /w de-book-dev'
DEV python --version
code ~/.bashrc
source ~/.bashrc
