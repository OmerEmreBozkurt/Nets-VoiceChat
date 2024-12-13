# Voice Chat Server
import socket
import threading
import struct

port = 5000
host = "0.0.0.0"

server = socket.socket()
server.bind((host, port))
server.listen(5)

rooms = {}
room_id_counters = {}

def start():
    print("Server started, waiting for connections...")
    while True:
        conn, addr = server.accept()
        print(f"Client connected from {addr}")
        t = threading.Thread(target=handle_new_connection, args=(conn,))
        t.start()

def handle_new_connection(conn):
    try:
        room_list = "\n".join(rooms.keys()) if rooms else "No rooms available."
        welcome_msg = (
            "Available rooms:\n" +
            room_list +
            "\n\nType an existing room name to join it, or type 'NEW:<RoomName>' to create a new room:\n"
        )
        conn.send(welcome_msg.encode('utf-8'))

        room_choice = conn.recv(1024)
        if not room_choice:
            conn.close()
            return
        room_choice = room_choice.decode('utf-8').strip()

        if room_choice.startswith("NEW:"):
            new_room_name = room_choice.split("NEW:")[-1].strip()
            if not new_room_name:
                conn.send(b"Invalid room name. Disconnecting.\n")
                conn.close()
                return

            if new_room_name not in rooms:
                rooms[new_room_name] = []
                room_id_counters[new_room_name] = 1
            room_choice = new_room_name

        if room_choice not in rooms:
            if room_choice == "":
                conn.send(b"No room chosen. Disconnecting.\n")
            else:
                conn.send(f"Room '{room_choice}' does not exist. Disconnecting.\n".encode('utf-8'))
            conn.close()
            return

        client_id = room_id_counters[room_choice]
        room_id_counters[room_choice] += 1

        rooms[room_choice].append((conn, client_id))
        conn.send(f"Joined room: {room_choice}\n".encode('utf-8'))

        handle_client(conn, room_choice, client_id)

    except Exception as e:
        print("Error in handle_new_connection:", e)
        conn.close()

def handle_client(conn, room_name, client_id):
    try:
        while True:
            data = conn.recv(4096)
            if not data:
                break

            id_bytes = struct.pack('>H', client_id)
            packet = id_bytes + data

            for (cl, cid) in rooms[room_name]:
                if cl != conn:
                    try:
                        cl.send(packet)
                    except:
                        pass
    except Exception as e:
        print("Error or disconnection:", e)
    finally:
        if (conn, client_id) in rooms[room_name]:
            rooms[room_name].remove((conn, client_id))
        conn.close()
        if len(rooms[room_name]) == 0:
            del rooms[room_name]
            del room_id_counters[room_name]
        print(f"Client disconnected from room {room_name}")

start()