import tkinter as tk
from tkinter import messagebox, ttk
import threading
from voiceChatClient import connect_to_server, audio_streaming, stop_audio_threads


class VoiceChatApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Voice Chat App")
        self.root.geometry("600x400")
        self.voiceChatClient = None
        self.username = None
        self.current_room = None
        self.is_room_owner = False

        self.setup_first_page()

    # Page 1: Username Entry
    def setup_first_page(self):
        self.clear_frame()
        
        frame = tk.Frame(self.root, padx=20, pady=20)
        frame.pack(expand=True)

        tk.Label(frame, text="Welcome to Voice Chat", font=("Arial", 20, "bold")).pack(pady=10)
        tk.Label(frame, text="Enter Your Username:", font=("Arial", 14)).pack(pady=5)

        self.username_entry = tk.Entry(frame, font=("Arial", 14), width=25)
        self.username_entry.pack(pady=10)

        tk.Button(frame, text="Continue", command=self.go_to_room_selection, font=("Arial", 12), bg="#4CAF50", fg="white").pack(pady=20)

    # Page 2: Room Management
    def setup_second_page(self):
        self.clear_frame()
        
        left_frame = tk.Frame(self.root, width=300, padx=10, pady=10)
        left_frame.pack(side="left", fill="y")
        
        right_frame = tk.Frame(self.root, padx=10, pady=10)
        right_frame.pack(side="right", expand=True, fill="both")

        # Left Panel: Room List
        tk.Label(left_frame, text="Available Rooms", font=("Arial", 14, "bold")).pack(pady=5)
        self.rooms_listbox = tk.Listbox(left_frame, font=("Arial", 12), height=15, width=30)
        self.rooms_listbox.pack(pady=5)
        tk.Button(left_frame, text="Refresh Rooms", command=self.refresh_rooms, font=("Arial", 12)).pack(pady=5)

        # Right Panel: Controls
        tk.Label(right_frame, text=f"Hello, {self.username}", font=("Arial", 14)).pack(pady=5)
        tk.Label(right_frame, text="Room Actions", font=("Arial", 12, "bold")).pack(pady=5)

        self.room_name_entry = tk.Entry(right_frame, font=("Arial", 12), width=30)
        self.room_name_entry.pack(pady=5)

        tk.Button(right_frame, text="Create Room", command=self.create_room, font=("Arial", 12), bg="#2196F3", fg="white").pack(pady=5)
        tk.Button(right_frame, text="Attend Room", command=self.attend_room, font=("Arial", 12), bg="#FF9800", fg="white").pack(pady=5)
        tk.Button(right_frame, text="Back", command=self.setup_first_page, font=("Arial", 12), bg="#F44336", fg="white").pack(pady=20)

        self.refresh_rooms()

    # Page 3: Inside Room
    def setup_third_page(self):
        self.clear_frame()

        tk.Label(self.root, text=f"Room: {self.current_room}", font=("Arial", 18, "bold")).pack(pady=10)

        users_frame = tk.Frame(self.root)
        users_frame.pack(expand=True, fill="both", padx=20, pady=10)

        tk.Label(users_frame, text="Users in this Room:", font=("Arial", 14)).pack(pady=5)

        self.users_listbox = tk.Listbox(users_frame, font=("Arial", 12), height=15)
        self.users_listbox.pack(expand=True, fill="both", pady=5)

        bottom_frame = tk.Frame(self.root, pady=10)
        bottom_frame.pack(fill="x")

        tk.Button(bottom_frame, text="Leave Room", command=self.leave_room, font=("Arial", 12), bg="#FF5722", fg="white").pack(side="left", padx=10)

        if self.is_room_owner:
            tk.Button(bottom_frame, text="Close Room", command=self.close_room, font=("Arial", 12), bg="#D32F2F", fg="white").pack(side="right", padx=10)

        # Start audio streaming
        threading.Thread(target=audio_streaming, args=(self.voiceChatClient,), daemon=True).start()

    # Navigation Functions
    def go_to_room_selection(self):
        username = self.username_entry.get()
        if not username:
            messagebox.showerror("Error", "Username cannot be empty!")
            return

        self.username = username
        try:
            self.voiceChatClient, welcome_message = connect_to_server()
            print(welcome_message)
            self.setup_second_page()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to connect to server: {e}")

    def create_room(self):
        room_name = self.room_name_entry.get()
        if not room_name:
            messagebox.showerror("Error", "Room name cannot be empty!")
            return

        try:
            self.voiceChatClient.send(f"NEW:{room_name}".encode('utf-8'))
            response = self.voiceChatClient.recv(4096).decode('utf-8')
            if "Joined room:" in response:
                self.current_room = room_name
                self.is_room_owner = True
                self.setup_third_page()
            else:
                messagebox.showerror("Error", response)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to create room: {e}")

    def attend_room(self):
        room_name = self.room_name_entry.get()
        if not room_name:
            messagebox.showerror("Error", "Please enter a room name to attend!")
            return

        try:
            self.voiceChatClient.send(room_name.encode('utf-8'))
            response = self.voiceChatClient.recv(4096).decode('utf-8')
            print("Server response (attend room):", response)

            if "Joined room:" in response:
                self.current_room = room_name
                self.is_room_owner = False
                self.setup_third_page()
            else:
                messagebox.showerror("Error", response)
        except ConnectionResetError:
            messagebox.showerror("Error", "Connection reset by the server. Please try again.")
            self.voiceChatClient.close()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to attend room: {e}")


    def refresh_rooms(self):
        try:
            self.voiceChatClient.send(b"LIST")
            response = self.voiceChatClient.recv(4096).decode('utf-8')
            self.rooms_listbox.delete(0, tk.END)
            rooms = response.split("\n")
            for room in rooms:
                if room.strip():
                    self.rooms_listbox.insert(tk.END, room)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to refresh rooms: {e}")

    def leave_room(self):
        self.voiceChatClient.send(b"LEAVE")
        self.setup_second_page()

    def close_room(self):
        self.voiceChatClient.send(b"CLOSE_ROOM")
        self.setup_second_page()

    def clear_frame(self):
        for widget in self.root.winfo_children():
            widget.destroy()


# Start GUI
if __name__ == "__main__":
    root = tk.Tk()
    app = VoiceChatApp(root)
    root.mainloop()
