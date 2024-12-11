import socket
import threading

port = 5000
host = "0.0.0.0"

server = socket.socket()

socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

server.bind((host, port))

server.listen(5)

client = []

def start():
    while True:
        conn, addr = server.accept()
        print("Client connected from:", addr)  # Add this line
        client.append(conn)
        t = threading.Thread(target=send, args=(conn,))
        t.start()

def send(fromConnection):
    try:
        while True:
            data = fromConnection.recv(4096)
            if data:
                print("Received data from a client.")  # Add this line
                for cl in client:
                    if cl != fromConnection:
                        cl.send(data)
            else:
                break
    except:
        client.clear()
        print("Client Disconnected")

start()
