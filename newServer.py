import socket
import threading

port = 5000
host = "0.0.0.0"

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind((host, port))
server.listen(5)

# rooms: { room_name: [(conn, client_id), ...], ... }
rooms = {}
client_id_counter = 0
broadcast_lock = threading.Lock()

def start():
    print("Server started, listening on port", port)
    while True:
        conn, addr = server.accept()
        print(f"Client connected from {addr}")
        t = threading.Thread(target=handle_new_connection, args=(conn,))
        t.start()

def get_room_list_text():
    """
    Return a newline-separated list of all room names,
    or "No rooms available." if none exist.
    """
    if not rooms:
        return "No rooms available."
    return "\n".join(rooms.keys())

def send_room_list(conn):
    """
    Sends "ROOM_LIST:RoomA\nRoomB\n..."
    """
    list_str = get_room_list_text()
    payload = f"ROOM_LIST:{list_str}\n"
    conn.send(payload.encode('utf-8'))

def handle_new_connection(conn):
    """
    1) Send welcome with current rooms
    2) Repeatedly read a command until the user chooses or creates a room, or disconnects:
       - "REQ:ROOM_LIST" => send room list
       - "NEW:<Name>" => create if needed, then pick that room
       - An existing room name => pick that room
    3) If user picks a valid room => go to handle_client
    """
    global client_id_counter

    welcome = (
        "Available rooms:\n" +
        get_room_list_text() +
        "\n\nType an existing room name to join it, "
        "or type 'NEW:<RoomName>' to create a new room, "
        "or 'REQ:ROOM_LIST' to refresh the room list.\n"
    )
    conn.send(welcome.encode('utf-8'))

    try:
        chosen_room = None

        while True:
            data = conn.recv(1024)
            if not data:
                # user disconnected
                conn.close()
                return

            line = data.decode('utf-8').strip()
            if not line:
                continue

            # Refresh
            if line == "REQ:ROOM_LIST":
                send_room_list(conn)
                continue

            # Create new room
            if line.startswith("NEW:"):
                new_room = line.split("NEW:", 1)[1].strip()
                if not new_room:
                    conn.send(b"Invalid room name.\n")
                    continue
                if new_room not in rooms:
                    rooms[new_room] = []
                chosen_room = new_room
                break

            # Otherwise, try to join an existing room
            if line in rooms:
                chosen_room = line
                break
            else:
                # invalid input
                msg = f"Room '{line}' not found. Type 'NEW:<Name>' or 'REQ:ROOM_LIST'.\n"
                conn.send(msg.encode('utf-8'))

        # If we have a chosen room
        client_id_counter += 1
        this_client_id = client_id_counter
        rooms[chosen_room].append((conn, this_client_id))

        conn.send(f"Joined room: {chosen_room}\n".encode('utf-8'))
        conn.send(f"ID:{this_client_id}\n".encode('utf-8'))

        handle_client(conn, chosen_room, this_client_id)

    except Exception as e:
        print("Error in handle_new_connection:", e)
        conn.close()

def handle_client(conn, room_name, client_id):
    """
    User is now in room_name. We:
      - accept large data as audio and broadcast
      - if it's short text, check for "REQ:ROOM_LIST"
      - on disconnection, remove from room
    """
    try:
        while True:
            data = conn.recv(4096)
            if not data:
                break

            # Distinguish short text from large audio
            if len(data) < 300:
                try:
                    text_cmd = data.decode('utf-8').strip()
                    if text_cmd == "REQ:ROOM_LIST":
                        send_room_list(conn)
                        continue
                    # else not recognized => treat as audio anyway
                except UnicodeDecodeError:
                    pass

            # treat as audio
            with broadcast_lock:
                for cl, cl_id in rooms[room_name]:
                    if cl != conn:
                        header = f"DATA:{client_id}:{len(data)}\n".encode('utf-8')
                        cl.send(header + data)

    except Exception as e:
        print("Error or disconnection:", e)
    finally:
        remove_from_room(conn, room_name, client_id)
        conn.close()
        print(f"Client {client_id} disconnected from room {room_name}")

def remove_from_room(conn, room_name, client_id):
    """
    Remove (conn, client_id) from that room. If empty => del rooms[room_name].
    """
    if room_name in rooms:
        pair = (conn, client_id)
        if pair in rooms[room_name]:
            rooms[room_name].remove(pair)
            if not rooms[room_name]:
                del rooms[room_name]  # auto-close empty room

start()