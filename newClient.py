import socket
import threading
import pyaudio
import sys
from collections import deque
import time

import tkinter as tk
from tkinter import ttk
from tkinter import messagebox

########################################################################
#                       AUDIO / NETWORK CONFIG                         #
########################################################################

host = "3.121.224.209"
port = 5000

Format = pyaudio.paInt16
Chunks = 4096
Channels = 1
Rate = 44100

output_streams = {}  # user_id -> (pyaudio_instance, output_stream)
my_client_id = None
stop_audio_threads = False

# Jitter buffers: user_id -> deque of audio chunks
jitter_buffers = {}
# Playback threads: user_id -> thread
playback_threads = {}

# Jitter Buffer Configuration
BUFFER_FILL_THRESHOLD = 2  # Start with fewer chunks to reduce initial delay


########################################################################
#                           NETWORK FUNCTIONS                          #
########################################################################

def connect_to_server():
    """
    Connects to the server and returns (socket, welcome_message).
    """
    client = socket.socket()
    client.connect((host, port))
    welcome_message = client.recv(4096).decode('utf-8')
    return client, welcome_message


def send_text_command(client, command_str):
    """
    Sends a text command to the server (like 'NEW:XYZ', 'myRoom', 'leave', or 'REQ:ROOM_LIST').
    """
    if not command_str:
        return
    client.send(command_str.encode('utf-8'))


def parse_server_messages(client, gui):
    """
    Runs in a background thread. Reads messages from server:
      - 'DATA:<sender_id>:<length>' -> next <length> bytes are audio
      - 'ID:<client_id>'
      - 'ROOM_LIST:...' (if the server is updated to handle REQ:ROOM_LIST)
      - other control lines
    Then updates the GUI or plays audio as needed.
    """
    global stop_audio_threads, my_client_id
    f = client.makefile('rb')

    while not stop_audio_threads:
        try:
            header_line = f.readline()
            if not header_line:
                break
            header_line = header_line.strip()

            # AUDIO DATA
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

            # CLIENT ID
            elif header_line.startswith(b"ID:"):
                line_str = header_line.decode('utf-8')
                my_client_id = int(line_str.split("ID:")[-1])
                print(f"Assigned Client ID: {my_client_id}")
                # We can also show on GUI if we want:
                gui.append_log(f"Assigned Client ID: {my_client_id}")

            # ROOM LIST (if server is updated to send "ROOM_LIST:roomA,roomB...")
            elif header_line.startswith(b"ROOM_LIST:"):
                # For example, if server responds with: "ROOM_LIST:No rooms available." or "ROOM_LIST:room1,room2"
                line_str = header_line.decode('utf-8')
                rooms_str = line_str.split("ROOM_LIST:")[-1].strip()
                # Update the GUI's room list display
                gui.update_room_list(rooms_str)

            else:
                # CONTROL MESSAGE or welcome text
                line_str = header_line.decode('utf-8')
                if line_str:
                    print(line_str)
                    gui.append_log(line_str)

        except Exception as e:
            print("Error receiving server messages:", e)
            break


def audio_sender(client, input_stream):
    """
    Continuously read mic data and send to server as raw audio.
    """
    global stop_audio_threads
    while not stop_audio_threads:
        try:
            data = input_stream.read(Chunks, exception_on_overflow=False)
            if data:
                client.send(data)
        except:
            break


########################################################################
#                          AUDIO PLAYBACK CODE                         #
########################################################################

def ensure_output_stream(user_id):
    """
    Create output stream and jitter buffer for a user if not already existing.
    """
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
    If buffer empties, play silence briefly until new data arrives.
    """
    global stop_audio_threads
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
            # Buffer empty, play short silence
            silence = b'\x00' * (Chunks * 2)
            out_stream.write(silence)
            time.sleep(0.01)


def play_audio_data_for_user(user_id, audio_data):
    """
    Push audio_data into the user's jitter buffer.
    Playback thread will handle it at a steady rate.
    """
    ensure_output_stream(user_id)
    jitter_buffers[user_id].append(audio_data)


########################################################################
#                          TKINTER GUI CODE                            #
########################################################################

class VoiceChatGUI:
    def __init__(self, root):
        """
        Main GUI initialization.
        """
        self.root = root
        self.root.title("Voice Chat Client")

        self.client_socket = None  # Will hold our connection to server
        self.audio_threads_started = False

        # Frame for Room List
        room_list_frame = ttk.LabelFrame(root, text="Available Rooms")
        room_list_frame.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")

        # A simple listbox to show rooms
        self.room_listbox = tk.Listbox(room_list_frame, height=8, width=50)
        self.room_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Scrollbar (optional)
        scrollbar = ttk.Scrollbar(room_list_frame, orient="vertical", command=self.room_listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.room_listbox.config(yscrollcommand=scrollbar.set)

        # Frame for refresh button
        refresh_btn = ttk.Button(room_list_frame, text="Refresh", command=self.on_refresh_rooms)
        refresh_btn.pack(side=tk.BOTTOM, fill=tk.X, padx=2, pady=2)

        # Frame for user input
        input_frame = ttk.LabelFrame(root, text="Command Input")
        input_frame.grid(row=1, column=0, padx=5, pady=5, sticky="nsew")

        self.command_entry = ttk.Entry(input_frame, width=40)
        self.command_entry.pack(side=tk.LEFT, padx=5, pady=5, fill=tk.X, expand=True)
        self.command_entry.bind("<Return>", lambda e: self.on_enter_command())  # Enter key

        enter_button = ttk.Button(input_frame, text="Enter", command=self.on_enter_command)
        enter_button.pack(side=tk.LEFT, padx=5, pady=5)

        # Frame for logging / messages
        log_frame = ttk.LabelFrame(root, text="Log / Messages")
        log_frame.grid(row=2, column=0, padx=5, pady=5, sticky="nsew")

        self.log_text = tk.Text(log_frame, height=10, width=60, state='disabled')
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        log_scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=log_scrollbar.set)

        # Make rows/columns expandable
        root.rowconfigure(0, weight=0)
        root.rowconfigure(1, weight=0)
        root.rowconfigure(2, weight=1)
        root.columnconfigure(0, weight=1)

        # Connect to server automatically and show welcome message
        self.connect_and_get_welcome()

    ####################################################################
    #                       GUI EVENT HANDLERS                         #
    ####################################################################

    def connect_and_get_welcome(self):
        """
        Connects to the server and retrieves the initial welcome message.
        Displays available rooms in the listbox if the text can be parsed.
        """
        global stop_audio_threads
        stop_audio_threads = False  # reset any previous runs

        try:
            self.client_socket, welcome_message = connect_to_server()
        except Exception as e:
            messagebox.showerror("Connection Error", f"Could not connect to server:\n{e}")
            self.append_log("Failed to connect to server.")
            return

        self.append_log(welcome_message)
        # The welcome message typically starts with:
        # "Available rooms:\nroom1\nroom2\n\nType an existing room..."
        # Let's parse the portion after "Available rooms:\n", if present
        rooms_block = None
        if "Available rooms:\n" in welcome_message:
            rooms_block = welcome_message.split("Available rooms:\n", 1)[1]

        if rooms_block:
            # Typically the server sends them line by line until the blank line
            # e.g. "roomA\nroomB\n\nType an existing room..."
            lines = rooms_block.split("\n")
            display_rooms = []
            for line in lines:
                # stop once we see something like "Type an existing room..."
                if line.strip().startswith("Type ") or not line.strip():
                    break
                display_rooms.append(line.strip())
            # Now display these in the listbox
            self.update_room_list("\n".join(display_rooms))

    def on_refresh_rooms(self):
        """
        Called when user clicks 'Refresh' button.
        Sends a request to server for updated room list (REQ:ROOM_LIST).
        The server must be updated to handle this new command and respond with "ROOM_LIST:..."
        """
        if self.client_socket:
            send_text_command(self.client_socket, "REQ:ROOM_LIST")

    def on_enter_command(self):
        """
        Called when user clicks 'Enter' or hits <Enter> in the entry.
        The command can be things like:
          - "NEW:<RoomName>"
          - "RoomName"
          - "leave"
          - "q" (quit)
        """
        cmd = self.command_entry.get().strip()
        self.command_entry.delete(0, tk.END)
        if not cmd:
            return
        self.append_log(f">>> {cmd}")

        # If user typed 'q', we exit the entire app
        if cmd.lower() == 'q':
            self.stop_and_close()
            return

        # Send this command to server
        send_text_command(self.client_socket, cmd)

        # If user typed "leave", we also want to end audio streaming
        if cmd.lower() == "leave":
            # We'll set stop_audio_threads to True, that eventually stops threads
            self.stop_audio_streaming()

        # If user typed a room name or NEW:<RoomName> and joined successfully,
        # we should start the audio streaming if not started yet.
        # We'll rely on the server's response to confirm we joined a room.
        # So let's just check if we already started audio threads. If not, start them.
        if not self.audio_threads_started and cmd.lower() != "leave":
            # Possibly user is joining/creating a room. Start audio streaming threads.
            self.start_audio_streaming()

    ####################################################################
    #                     AUDIO STREAMING CONTROL                      #
    ####################################################################

    def start_audio_streaming(self):
        """
        Launches threads for sending microphone audio and receiving server messages.
        """
        global stop_audio_threads
        if self.audio_threads_started:
            return  # already started

        self.audio_threads_started = True

        # Start parse_server_messages in background
        t_recv = threading.Thread(target=parse_server_messages, args=(self.client_socket, self))
        t_recv.daemon = True
        t_recv.start()

        # Start the audio streaming threads
        p = pyaudio.PyAudio()
        self.input_stream = p.open(format=Format,
                                   channels=Channels,
                                   rate=Rate,
                                   input=True,
                                   frames_per_buffer=Chunks)

        t_send = threading.Thread(target=audio_sender, args=(self.client_socket, self.input_stream))
        t_send.daemon = True
        t_send.start()

        # We do NOT do user_input_thread anymore, because the GUI handles user input.

    def stop_audio_streaming(self):
        """
        Instructs all audio threads to stop.
        """
        global stop_audio_threads
        stop_audio_threads = True

        # Give them time to shut down
        time.sleep(0.5)

        # Close streams
        for uid, (pa, out_stream) in output_streams.items():
            try:
                out_stream.stop_stream()
                out_stream.close()
                pa.terminate()
            except:
                pass
        output_streams.clear()
        jitter_buffers.clear()
        playback_threads.clear()

        # Also close mic input if it exists
        if hasattr(self, 'input_stream') and self.input_stream is not None:
            try:
                self.input_stream.stop_stream()
                self.input_stream.close()
            except:
                pass
        self.input_stream = None
        self.audio_threads_started = False

    ####################################################################
    #                       HELPER / UTILITY                            #
    ####################################################################

    def update_room_list(self, rooms_str):
        """
        Clears and repopulates the room_listbox with rooms_str,
        which may be something like:
          'No rooms available.'
        or
          'roomA\nroomB\nroomC'
        """
        self.room_listbox.delete(0, tk.END)
        lines = rooms_str.strip().split("\n")
        for line in lines:
            if line.strip():
                self.room_listbox.insert(tk.END, line.strip())

    def append_log(self, text):
        """
        Appends text to the log Text widget.
        """
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, text + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')

    def stop_and_close(self):
        """
        Called when user wants to quit the entire app.
        """
        self.stop_audio_streaming()
        try:
            if self.client_socket:
                self.client_socket.close()
        except:
            pass
        self.root.destroy()


########################################################################
#                           MAIN ENTRY POINT                           #
########################################################################

def main():
    """
    Instead of a console-based interface, we start a Tkinter GUI.
    """
    root = tk.Tk()
    app = VoiceChatGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.stop_and_close)  # handle window close
    root.mainloop()


if __name__ == "__main__":
    main()