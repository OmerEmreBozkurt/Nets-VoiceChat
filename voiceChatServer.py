import socket
import threading

# Server Configuration
port = 5000
host = "0.0.0.0"

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind((host, port))
server.listen(5)

# Room Management
rooms = {}  # room_name: list of (conn, client_id)
client_id_counter = 0
broadcast_lock = threading.Lock()  # Lock for broadcasting data


def start():
    print("Server started, waiting for connections...")
    while True:
        try:
            conn, addr = server.accept()
            print(f"Client connected from {addr}")
            t = threading.Thread(target=handle_new_connection, args=(conn,))
            t.start()
        except KeyboardInterrupt:
            print("Server shutting down...")
            break
        except Exception as e:
            print("Error accepting new connection:", e)


def handle_new_connection(conn):
    global client_id_counter

    try:
        room_list = "\n".join(rooms.keys()) if rooms else "No rooms available."
        welcome_msg = (
            "Available rooms:\n" +
            room_list +
            "\n\nType an existing room name to join it, "
            "or type 'NEW:<RoomName>' to create a new room:\n"
        )
        conn.send(welcome_msg.encode('utf-8'))

        while True:
            try:
                room_choice = conn.recv(1024).decode('utf-8').strip()
                if not room_choice:
                    continue

                # ✅ Handle LIST Command
                if room_choice.upper() == "LIST":
                    print("Received LIST command from client.")
                    room_list = "\n".join(rooms.keys()) if rooms else "No rooms available."
                    conn.send(room_list.encode('utf-8'))
                    continue

                # ✅ Handle NEW Command
                if room_choice.startswith("NEW:"):
                    new_room_name = room_choice.split("NEW:")[-1].strip()
                    if not new_room_name:
                        conn.send(b"Invalid room name. Please try again.\n")
                        continue
                    if new_room_name not in rooms:
                        rooms[new_room_name] = []
                        print(f"Room '{new_room_name}' created.")
                    room_choice = new_room_name

                # ✅ Handle Joining an Existing Room
                if room_choice in rooms:
                    client_id_counter += 1
                    this_client_id = client_id_counter

                    rooms[room_choice].append((conn, this_client_id))
                    conn.send(f"Joined room: {room_choice}\n".encode('utf-8'))
                    conn.send(f"ID:{this_client_id}\n".encode('utf-8'))

                    handle_client(conn, room_choice, this_client_id)
                    return

                else:
                    conn.send(f"Room '{room_choice}' does not exist. Please try again.\n".encode('utf-8'))

            except ConnectionResetError:
                print("Connection was reset by the client.")
                break
            except Exception as e:
                print("Error in room selection:", e)
                break

    except (ConnectionResetError, BrokenPipeError):
        print("Client disconnected unexpectedly.")
    except Exception as e:
        print("Error in handle_new_connection:", e)
    finally:
        conn.close()



def handle_client(conn, room_name, client_id):
    try:
        while True:
            data = conn.recv(4096)
            if not data:
                break

            # Broadcast this audio data to everyone else in the room
            with broadcast_lock:
                for cl, cl_id in rooms.get(room_name, []):
                    if cl != conn:
                        try:
                            header = f"DATA:{client_id}:{len(data)}\n".encode('utf-8')
                            cl.send(header + data)
                        except Exception as e:
                            print(f"Failed to send data to client {cl_id}: {e}")

    except (ConnectionResetError, BrokenPipeError):
        print(f"Client {client_id} disconnected unexpectedly.")
    except Exception as e:
        print(f"Error in handle_client (Client {client_id}):", e)
    finally:
        remove_client_from_room(conn, room_name, client_id)


def remove_client_from_room(conn, room_name, client_id):
    """Remove a client from the room and clean up resources if the room is empty."""
    try:
        with broadcast_lock:
            if (conn, client_id) in rooms.get(room_name, []):
                rooms[room_name].remove((conn, client_id))
                print(f"Client {client_id} removed from room '{room_name}'.")

            if len(rooms.get(room_name, [])) == 0:
                del rooms[room_name]
                print(f"Room '{room_name}' deleted as it became empty.")
    except Exception as e:
        print(f"Error removing client {client_id} from room {room_name}: {e}")
    finally:
        conn.close()


# Start the server
if __name__ == "__main__":
    try:
        start()
    except KeyboardInterrupt:
        print("Server shutting down gracefully.")
