import tkinter as tk
from tkinter import messagebox
import threading
from voiceChatClient import connect_to_server, audio_streaming, stop_audio_threads


class VoiceChatApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Voice Chat App")
        self.root.geometry("600x500")
        self.voiceChatClient = None
        self.username = None
        self.current_room = None
        self.is_room_owner = False

        self.frames = {}  # Sayfaları saklamak için sözlük
        self.setup_pages()
        self.show_page("FirstPage")

    def setup_pages(self):
        """Sayfaları tek seferde oluştur ve sakla."""
        self.frames["FirstPage"] = FirstPage(self)
        self.frames["SecondPage"] = SecondPage(self)
        self.frames["ThirdPage"] = ThirdPage(self)

        for frame in self.frames.values():
            frame.grid(row=0, column=0, sticky="nsew")

    def show_page(self, page_name):
        """Belirtilen sayfayı göster."""
        frame = self.frames[page_name]
        frame.tkraise()

    def connect_to_server(self, username):
        try:
            self.username = username
            self.voiceChatClient, welcome_message = connect_to_server()
            print(welcome_message)
            self.show_page("SecondPage")
            self.frames["SecondPage"].update_username(username)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to connect to server: {e}")


class FirstPage(tk.Frame):
    def __init__(self, controller):
        super().__init__(controller.root)
        self.controller = controller
        self.create_widgets()

    def create_widgets(self):
        tk.Label(self, text="Welcome to Voice Chat", font=("Arial", 20, "bold")).pack(pady=10)
        tk.Label(self, text="Enter Your Username:", font=("Arial", 14)).pack(pady=5)

        self.username_entry = tk.Entry(self, font=("Arial", 14), width=25)
        self.username_entry.pack(pady=10)

        tk.Button(self, text="Continue",
                  command=self.go_to_room_selection,
                  font=("Arial", 12), bg="#4CAF50", fg="white").pack(pady=20)

    def go_to_room_selection(self):
        username = self.username_entry.get()
        if not username:
            messagebox.showerror("Error", "Username cannot be empty!")
            return
        self.controller.connect_to_server(username)


class SecondPage(tk.Frame):
    def __init__(self, controller):
        super().__init__(controller.root)
        self.controller = controller
        self.create_widgets()

    def create_widgets(self):
        left_frame = tk.Frame(self, width=300, padx=10, pady=10)
        left_frame.pack(side="left", fill="y")

        right_frame = tk.Frame(self, padx=10, pady=10)
        right_frame.pack(side="right", expand=True, fill="both")

        # Left Panel: Room List
        tk.Label(left_frame, text="Available Rooms", font=("Arial", 14, "bold")).pack(pady=5)
        self.rooms_listbox = tk.Listbox(left_frame, font=("Arial", 12), height=15, width=30)
        self.rooms_listbox.pack(pady=5)
        tk.Button(left_frame, text="Refresh Rooms", command=self.refresh_rooms, font=("Arial", 12)).pack(pady=5)

        # Right Panel: Controls
        self.username_label = tk.Label(right_frame, text="", font=("Arial", 14))
        self.username_label.pack(pady=5)
        tk.Label(right_frame, text="Room Actions", font=("Arial", 12, "bold")).pack(pady=5)

        self.room_name_entry = tk.Entry(right_frame, font=("Arial", 12), width=30)
        self.room_name_entry.pack(pady=5)

        tk.Button(right_frame, text="Create Room", command=self.create_room,
                  font=("Arial", 12), bg="#2196F3", fg="white").pack(pady=5)
        tk.Button(right_frame, text="Attend Room", command=self.attend_room,
                  font=("Arial", 12), bg="#FF9800", fg="white").pack(pady=5)
        tk.Button(right_frame, text="Back", command=lambda: self.controller.show_page("FirstPage"),
                  font=("Arial", 12), bg="#F44336", fg="white").pack(pady=20)

    def update_username(self, username):
        self.username_label.config(text=f"Hello, {username}")

    def refresh_rooms(self):
        try:
            self.controller.voiceChatClient.send(b"LIST")
            response = self.controller.voiceChatClient.recv(4096).decode('utf-8')
            self.rooms_listbox.delete(0, tk.END)
            for room in response.split("\n"):
                if room.strip():
                    self.rooms_listbox.insert(tk.END, room)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to refresh rooms: {e}")

    def create_room(self):
        room_name = self.room_name_entry.get()
        if not room_name:
            messagebox.showerror("Error", "Room name cannot be empty!")
            return

        try:
            self.controller.voiceChatClient.send(f"NEW:{room_name}".encode('utf-8'))
            response = self.controller.voiceChatClient.recv(4096).decode('utf-8')
            if "Joined room:" in response:
                self.controller.current_room = room_name
                self.controller.is_room_owner = True
                self.controller.show_page("ThirdPage")
            else:
                messagebox.showerror("Error", response)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to create room: {e}")

    def attend_room(self):
        """Bir odaya katılmak için sunucuya istek gönderir."""
        room_name = self.room_name_entry.get()
        if not room_name:
            messagebox.showerror("Error", "Please enter a room name to attend!")
            return

        try:
            self.controller.voiceChatClient.send(room_name.encode('utf-8'))
            response = self.controller.voiceChatClient.recv(4096).decode('utf-8')
            if "Joined room:" in response:
                self.controller.current_room = room_name
                self.controller.is_room_owner = False
                self.controller.show_page("ThirdPage")
            else:
                messagebox.showerror("Error", response)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to attend room: {e}")



class ThirdPage(tk.Frame):
    def __init__(self, controller):
        super().__init__(controller.root)
        self.controller = controller
        self.create_widgets()

    def create_widgets(self):
        tk.Label(self, text="Room", font=("Arial", 18, "bold")).pack(pady=10)

        users_frame = tk.Frame(self)
        users_frame.pack(expand=True, fill="both", padx=20, pady=10)

        tk.Label(users_frame, text="Users in this Room:", font=("Arial", 14)).pack(pady=5)

        self.users_listbox = tk.Listbox(users_frame, font=("Arial", 12), height=15)
        self.users_listbox.pack(expand=True, fill="both", pady=5)

        bottom_frame = tk.Frame(self, pady=10)
        bottom_frame.pack(fill="x")

        tk.Button(bottom_frame, text="Leave Room", command=self.leave_room,
                  font=("Arial", 12), bg="#FF5722", fg="white").pack(side="left", padx=10)

    def leave_room(self):
        try:
            self.controller.voiceChatClient.send(b"LEAVE")
        except:
            pass
        self.controller.show_page("SecondPage")


# Start GUI
if __name__ == "__main__":
    root = tk.Tk()
    app = VoiceChatApp(root)
    root.mainloop()
