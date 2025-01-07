import socket
import threading
import pyaudio
import sys
import time

import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
from collections import deque

########################################################################
#                       AUDIO / NETWORK CONFIG                         #
########################################################################

host = "16.170.201.66"  # <-- Put your server's public IP
port = 5000

Format = pyaudio.paInt16
Chunks = 4096
Channels = 1
Rate = 44100

stop_audio_threads = False       # Controls mic & playback
stop_parsing_messages = False    # Controls parse_server_messages

output_streams = {}   # user_id -> (pyaudio_instance, output_stream)
jitter_buffers = {}   # user_id -> deque()
playback_threads = {} # user_id -> thread

my_client_id = None

BUFFER_FILL_THRESHOLD = 2


########################################################################
#                           CLIENT FUNCTIONS                           #
########################################################################

def send_text_command(client_socket, cmd_str):
    """ Sends a command to server if not empty. """
    if cmd_str:
        client_socket.send(cmd_str.encode('utf-8'))

def parse_server_messages(client_socket, gui):
    """
    Reads lines from server in a loop:
      - ID:<id>
      - ROOM_LIST:...
      - DATA:<client_id>:<length>
      - "Joined room:"
      - ...
    """
    global stop_parsing_messages, my_client_id
    f = client_socket.makefile('rb')

    while True:
        if stop_parsing_messages:
            break
        try:
            line = f.readline()
            if not line:
                break
            line = line.strip()

            if line.startswith(b"DATA:"):
                # parse audio
                parts = line.decode('utf-8').split(':')
                if len(parts) == 3:
                    _, sid_str, length_str = parts
                    sid = int(sid_str)
                    length = int(length_str)
                    audio_data = f.read(length)
                    if not audio_data or len(audio_data) < length:
                        break
                    play_audio_data_for_user(sid, audio_data)

            elif line.startswith(b"ID:"):
                my_client_id = int(line.decode('utf-8').split("ID:")[-1])
                gui.append_log(f"Assigned Client ID: {my_client_id}")

            elif line.startswith(b"ROOM_LIST:"):
                line_str = line.decode('utf-8')
                rooms_str = line_str.split("ROOM_LIST:", 1)[1].strip()
                gui.update_room_list(rooms_str)

            else:
                # Some text
                text = line.decode('utf-8')
                gui.append_log(text)

                # If we see "Joined room:", auto-start mic
                if text.startswith("Joined room:"):
                    gui.start_mic_stream()

        except Exception as e:
            print("Error in parse_server_messages:", e)
            break

    print("[parse_server_messages] ended.")


########################################################################
#                         AUDIO SENDER / PLAYBACK                      #
########################################################################

def audio_sender(client_socket, mic_stream):
    global stop_audio_threads
    while True:
        if stop_audio_threads:
            break
        try:
            data = mic_stream.read(Chunks, exception_on_overflow=False)
            if data:
                client_socket.send(data)
        except:
            break
    print("[audio_sender] ended.")

def play_audio_data_for_user(user_id, audio_data):
    if stop_audio_threads:
        return
    ensure_output_stream(user_id)
    jitter_buffers[user_id].append(audio_data)

def ensure_output_stream(user_id):
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
        t = threading.Thread(target=playback_thread_func, args=(user_id,))
        t.daemon = True
        t.start()
        playback_threads[user_id] = t

def playback_thread_func(user_id):
    global stop_audio_threads
    _, out_stream = output_streams[user_id]
    buf = jitter_buffers[user_id]

    while not stop_audio_threads and len(buf) < BUFFER_FILL_THRESHOLD:
        time.sleep(0.01)

    while True:
        if stop_audio_threads:
            break
        if len(buf) > 0:
            chunk = buf.popleft()
            out_stream.write(chunk)
        else:
            out_stream.write(b'\x00' * (Chunks * 2))
            time.sleep(0.01)
    print(f"[playback_thread_func] user {user_id} ended.")

def start_mic_and_playback(client_socket, gui):
    global stop_audio_threads
    stop_audio_threads = False
    p = pyaudio.PyAudio()
    gui.mic_stream = p.open(format=Format,
                            channels=Channels,
                            rate=Rate,
                            input=True,
                            frames_per_buffer=Chunks)

    gui.mic_thread = threading.Thread(target=audio_sender, args=(client_socket, gui.mic_stream))
    gui.mic_thread.daemon = True
    gui.mic_thread.start()

def stop_mic_and_playback():
    global stop_audio_threads
    stop_audio_threads = True
    time.sleep(0.3)

    # close all playback streams
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
    print("[stop_mic_and_playback] closed playback.")


########################################################################
#                           THE GUI CLASS                              #
########################################################################

class VoiceChatGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Voice Chat Client")

        self.client_socket = None
        self.parse_thread = None

        self.mic_stream = None
        self.mic_thread = None

        self.build_gui()
        self.connect_to_server()

    def build_gui(self):
        frame_rooms = ttk.LabelFrame(self.root, text="Available Rooms")
        frame_rooms.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")

        self.room_listbox = tk.Listbox(frame_rooms, height=8, width=50)
        self.room_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollb = ttk.Scrollbar(frame_rooms, orient="vertical", command=self.room_listbox.yview)
        scrollb.pack(side=tk.RIGHT, fill=tk.Y)
        self.room_listbox.config(yscrollcommand=scrollb.set)

        btn_refresh = ttk.Button(frame_rooms, text="Refresh", command=self.on_refresh_rooms)
        btn_refresh.pack(side=tk.BOTTOM, fill=tk.X, padx=2, pady=2)

        frame_cmd = ttk.LabelFrame(self.root, text="Command Input")
        frame_cmd.grid(row=1, column=0, padx=5, pady=5, sticky="nsew")

        self.cmd_entry = ttk.Entry(frame_cmd, width=40)
        self.cmd_entry.pack(side=tk.LEFT, padx=5, pady=5, fill=tk.X, expand=True)
        self.cmd_entry.bind("<Return>", lambda e: self.on_enter_command())

        btn_enter = ttk.Button(frame_cmd, text="Enter", command=self.on_enter_command)
        btn_enter.pack(side=tk.LEFT, padx=5, pady=5)

        frame_log = ttk.LabelFrame(self.root, text="Log / Messages")
        frame_log.grid(row=2, column=0, padx=5, pady=5, sticky="nsew")

        self.log_text = tk.Text(frame_log, height=10, width=60, state='disabled')
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        log_scroll = ttk.Scrollbar(frame_log, orient="vertical", command=self.log_text.yview)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=log_scroll.set)

        self.root.rowconfigure(2, weight=1)
        self.root.columnconfigure(0, weight=1)

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def connect_to_server(self):
        global stop_parsing_messages
        stop_parsing_messages = False

        try:
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.connect((host, port))
            welcome_msg = self.client_socket.recv(4096).decode('utf-8')
            self.append_log(welcome_msg)
            self.parse_welcome_rooms(welcome_msg)
        except Exception as e:
            messagebox.showerror("Connection Error", str(e))
            self.append_log("Could not connect to server.")
            return

        self.parse_thread = threading.Thread(target=parse_server_messages, args=(self.client_socket, self))
        self.parse_thread.daemon = True
        self.parse_thread.start()

    def parse_welcome_rooms(self, text):
        if "Available rooms:\n" in text:
            block = text.split("Available rooms:\n", 1)[1]
            lines = block.split("\n")
            rooms_collect = []
            for line in lines:
                if line.strip().startswith("Type ") or not line.strip():
                    break
                rooms_collect.append(line.strip())
            if rooms_collect:
                self.update_room_list("\n".join(rooms_collect))

    ####################################################################
    #                          EVENT HANDLERS                           #
    ####################################################################

    def on_refresh_rooms(self):
        if self.client_socket:
            send_text_command(self.client_socket, "REQ:ROOM_LIST")

    def on_enter_command(self):
        cmd = self.cmd_entry.get().strip()
        self.cmd_entry.delete(0, tk.END)
        if not cmd:
            return
        self.append_log(f">>> {cmd}")

        if cmd.lower() == "leave":
            self.leave_and_reconnect()
            return
        if cmd.lower() == "q":
            self.on_close()
            return

        if self.client_socket:
            send_text_command(self.client_socket, cmd)

    def leave_and_reconnect(self):
        """
        1) Stop mic & playback
        2) Stop parse thread
        3) Close socket
        4) Clear GUI
        5) Reconnect
        """
        self.stop_mic_stream()
        self.stop_parse_thread()
        if self.client_socket:
            try:
                self.client.shutdown(socket.SHUT_RDWR)
                self.client.close()

            except:
                pass
        self.client_socket = None

        # Clear log & rooms
        self.log_text.config(state='normal')
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state='disabled')
        self.update_room_list("")


        self.connect_to_server()

    ####################################################################
    #                      START/STOP MIC STREAM                        #
    ####################################################################

    def start_mic_stream(self):
        self.append_log("[Audio] Starting mic + playback.")
        start_mic_and_playback(self.client_socket, self)

    def stop_mic_stream(self):
        self.append_log("[Audio] Stopping mic + playback.")
        stop_mic_and_playback()
        if self.mic_stream:
            try:
                self.mic_stream.stop_stream()
                self.mic_stream.close()
            except:
                pass
        self.mic_stream = None
        self.mic_thread = None

    ####################################################################
    #                          ROOM LIST, LOG                           #
    ####################################################################

    def update_room_list(self, rooms_str):
        self.room_listbox.delete(0, tk.END)
        lines = rooms_str.strip().split("\n")
        for line in lines:
            line = line.strip()
            if line:
                self.room_listbox.insert(tk.END, line)

    def append_log(self, text):
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, text + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')

    def stop_parse_thread(self):
        global stop_parsing_messages
        stop_parsing_messages = True
        if self.parse_thread and self.parse_thread.is_alive():
            self.parse_thread.join(timeout=1)
        self.parse_thread = None

    def on_close(self):
        self.stop_mic_stream()
        self.stop_parse_thread()
        if self.client_socket:
            try:
                self.client_socket.close()
            except:
                pass
        self.client_socket = None
        self.root.destroy()


########################################################################
#                                MAIN                                  #
########################################################################

def main():
    root = tk.Tk()
    root.title("Voice Chat Client")
    app = VoiceChatGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()