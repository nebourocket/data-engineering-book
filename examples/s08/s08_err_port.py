import socket

first = socket.socket()
first.bind(("127.0.0.1", 18080))
first.listen()

second = socket.socket()
second.bind(("127.0.0.1", 18080))
