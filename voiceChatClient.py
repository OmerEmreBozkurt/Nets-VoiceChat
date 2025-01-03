import socket
import threading
import pyaudio
import sys
from collections import deque
import time

host = "16.171.15.161"
port = 5000

Format = pyaudio.paInt16
Chunks = 4096
Channels = 1
Rate = 44100

output_streams = {}   # user_id -> (pyaudio_instance, output_stream)
my_client_id = None
stop_audio_threads = False

# Jitter buffers: user_id -> deque of audio chunks
jitter_buffers = {}
# Playback threads: user_id -> thread
playback_threads = {}

# Jitter Buffer Configuration
BUFFER_FILL_THRESHOLD = 2  # Start with fewer chunks to reduce initial delay
# We will no longer strictly sleep TIME_PER_CHUNK each iteration, we'll just try to play continuously.

def connect_to_server():
    client = socket.socket()
    client.connect((host, port))
    welcome_message = client.recv(4096).decode('utf-8')
    return client, welcome_message

def choose_room(client):
    while True:
        choice = input("Type an existing room name to join, 'NEW:<RoomName>' to create a new room, or 'q' to quit: ").strip()
        if choice.lower() == 'q':
            client.close()
            sys.exit(0)
        client.send(choice.encode('utf-8'))
        response = client.recv(4096).decode('utf-8')
        print(response)
        if "Joined room:" in response:
            return True
        elif "Disconnecting" in response:
            client.close()
            return False

def ensure_output_stream(user_id):
    """Create output stream and jitter buffer for a user if not already existing."""
    if user_id not in output_streams:
        p = pyaudio.PyAudio()
        out_stream = p.open(format=Format,
                            channels=Channels,
                            rate=Rate,
                            output=True,
                            frames_per_buffer=Chunks)
        output_streams[user_id] = (p, out_stream)
    if user_id not in jitter_buffers:
        jitter_buffers[user_id] = deque()
    if user_id not in playback_threads:
        # Start a playback thread for this user
        t = threading.Thread(target=playback_thread_func, args=(user_id,))
        t.daemon = True
        t.start()
        playback_threads[user_id] = t

def playback_thread_func(user_id):
    """
    Playback thread:
    Wait until jitter buffer has at least a few chunks, then play chunks as they come.
    If buffer empties, play silence briefly until new data arrives, but do not force long waits.
    """
    _, out_stream = output_streams[user_id]
    buffer = jitter_buffers[user_id]

    # Wait for buffer to fill a bit to avoid immediate stutter
    while not stop_audio_threads and len(buffer) < BUFFER_FILL_THRESHOLD:
        time.sleep(0.01)

    # Now play continuously
    while not stop_audio_threads:
        if len(buffer) > 0:
            chunk = buffer.popleft()
            out_stream.write(chunk)
        else:
            # Buffer empty, play a short silence or just wait a bit
            # Play a very small silence just to avoid a big crackle:
            silence = b'\x00' * (Chunks * 2)
            out_stream.write(silence)
            # Sleep a bit to wait for next data
            time.sleep(0.01)

def play_audio_data_for_user(user_id, audio_data):
    """
    Push audio_data into the user's jitter buffer.
    The playback thread plays as soon as data arrives, trying to be continuous.
    """
    ensure_output_stream(user_id)
    jitter_buffers[user_id].append(audio_data)

def parse_server_messages(client):
    global stop_audio_threads, my_client_id
    f = client.makefile('rb')
    while not stop_audio_threads:
        try:
            header_line = f.readline()
            if not header_line:
                break
            header_line = header_line.strip()
            if header_line.startswith(b"DATA:"):
                # Format: DATA:<sender_id>:<length>
                parts = header_line.decode('utf-8').split(':')
                if len(parts) == 3:
                    _, sender_id_str, length_str = parts
                    sender_id = int(sender_id_str)
                    length = int(length_str)
                    audio_data = f.read(length)
                    if not audio_data or len(audio_data) < length:
                        break
                    play_audio_data_for_user(sender_id, audio_data)
            elif header_line.startswith(b"ID:"):
                line_str = header_line.decode('utf-8')
                my_client_id = int(line_str.split("ID:")[-1])
                print(f"Assigned Client ID: {my_client_id}")
            else:
                # Control message
                line_str = header_line.decode('utf-8')
                if line_str:
                    print(line_str)
        except Exception as e:
            print("Error receiving server messages:", e)
            break

def audio_sender(client, input_stream):
    global stop_audio_threads
    while not stop_audio_threads:
        try:
            data = input_stream.read(Chunks, exception_on_overflow=False)
            if data:
                client.send(data)
        except:
            break

def user_input_thread(client):
    global stop_audio_threads
    while not stop_audio_threads:
        command = sys.stdin.readline().strip().lower()
        if command == "leave":
            break
    stop_audio_threads = True
    try:
        client.shutdown(socket.SHUT_RDWR)
    except:
        pass
    client.close()

def audio_streaming(client):
    global stop_audio_threads, output_streams, jitter_buffers
    stop_audio_threads = False
    p = pyaudio.PyAudio()
    input_stream = p.open(format=Format,
                          channels=Channels,
                          rate=Rate,
                          input=True,
                          frames_per_buffer=Chunks)

    t_send = threading.Thread(target=audio_sender, args=(client, input_stream))
    t_recv = threading.Thread(target=parse_server_messages, args=(client,))
    t_input = threading.Thread(target=user_input_thread, args=(client,))

    t_send.start()
    t_recv.start()
    t_input.start()

    t_send.join()
    t_recv.join()

    # Close output streams
    for uid, (pa, out_stream) in output_streams.items():
        out_stream.stop_stream()
        out_stream.close()
        pa.terminate()
    output_streams.clear()
    jitter_buffers.clear()

    input_stream.stop_stream()
    input_stream.close()
    p.terminate()

def main():
    while True:
        client, welcome_message = connect_to_server()
        print(welcome_message)
        joined = choose_room(client)
        if not joined:
            continue
        audio_streaming(client)

if __name__ == "__main__":
    main()