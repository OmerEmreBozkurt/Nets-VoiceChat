import tkinter as tk
from logging import exception
from tkinter import messagebox, ttk
import threading
from voiceChatClient import connect_to_server, audio_streaming, parse_server_messages


class VoiceChatApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Voice Chat App")
        self.root.geometry("600x500")
        self.voiceChatClient = None
        self.username = None
        self.current_room = None
        self.is_room_owner = False

        self.frames = {}  # Initialize the dictionary for frames

        self.setup_pages()
        self.show_page("FirstPage")

    def setup_pages(self):
        """Sayfaları tek seferde oluştur ve sakla."""
        for PageClass in (FirstPage, SecondPage, ThirdPage):
            page_name = PageClass.__name__
            frame = PageClass(self)
            self.frames[page_name] = frame
            frame.grid(row=0, column=0, sticky="nsew")

    def show_page(self, page_name):
        """Belirtilen sayfayı göster."""
        frame = self.frames[page_name]
        frame.tkraise()

class FirstPage(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent.root)
        self.parent = parent  # Save reference to VoiceChatApp

        frame = tk.Frame(self, padx=20, pady=20)
        frame.pack(expand=True)

        tk.Label(frame, text="Welcome to Voice Chat", font=("Arial", 20, "bold")).pack(pady=10)
        tk.Label(frame, text="Enter Your Username:", font=("Arial", 14)).pack(pady=5)

        self.username_entry = tk.Entry(frame, font=("Arial", 14), width=25)
        self.username_entry.pack(pady=10)

        tk.Button(frame, text="Continue", command=self.go_to_second_page, font=("Arial", 12), bg="#4CAF50",
                  fg="white").pack(pady=20)

    def go_to_second_page(self):
        username = self.username_entry.get()
        if not username:
            messagebox.showerror("Error", "Username cannot be empty!")
            return

        self.parent.username = username
        try:
            self.parent.voiceChatClient, welcome_message = connect_to_server()
            if self.parent.voiceChatClient is None:
                raise ConnectionError("Unable to establish a connection to the server.")

            print(welcome_message)

            # Start the parsing thread only if client is valid
            threading.Thread(
                target=parse_server_messages,
                args=(self.parent.voiceChatClient,),
                daemon=True
            ).start()

            self.parent.show_page("SecondPage")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to connect to server: {e}")


class SecondPage(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent.root)
        self.parent = parent

        left_frame = tk.Frame(self, width=300, padx=10, pady=10)
        left_frame.pack(side="left", fill="y")

        right_frame = tk.Frame(self, padx=10, pady=10)
        right_frame.pack(side="right", expand=True, fill="both")

        tk.Label(left_frame, text="Available Rooms", font=("Arial", 14, "bold")).pack(pady=5)
        self.rooms_listbox = tk.Listbox(left_frame, font=("Arial", 12), height=15, width=30)
        self.rooms_listbox.pack(pady=5)
        tk.Button(left_frame, text="Refresh Rooms", command=self.refresh_rooms, font=("Arial", 12)).pack(pady=5)

        tk.Label(right_frame, text=f"Hello, {self.parent.username}", font=("Arial", 14)).pack(pady=5)
        tk.Label(right_frame, text="Room Actions", font=("Arial", 12, "bold")).pack(pady=5)

        self.room_name_entry = tk.Entry(right_frame, font=("Arial", 12), width=30)
        self.room_name_entry.pack(pady=5)

        tk.Button(right_frame, text="Create Room", command=self.create_room, font=("Arial", 12), bg="#2196F3",
                  fg="white").pack(pady=5)
        tk.Button(right_frame, text="Attend Room", command=self.attend_room, font=("Arial", 12), bg="#FF9800",
                  fg="white").pack(pady=5)
        tk.Button(right_frame, text="Back", command=lambda: self.parent.show_page("FirstPage"), font=("Arial", 12),
                  bg="#F44336", fg="white").pack(pady=20)

    def create_room(self):
        room_name = self.room_name_entry.get()
        if not room_name:
            messagebox.showerror("Error", "Room name cannot be empty!")
            return

        try:
            if self.parent.voiceChatClient is None:
                raise ConnectionError("Not connected to the server. Please reconnect.")

            self.parent.voiceChatClient.send(f"NEW:{room_name}".encode('utf-8'))
            response = self.parent.voiceChatClient.recv(4096).decode('utf-8')
            if "Joined room:" in response:
                self.parent.current_room = room_name
                self.parent.is_room_owner = True
                self.parent.show_page("ThirdPage")
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
            if self.parent.voiceChatClient is None:
                raise ConnectionError("Not connected to the server. Please reconnect.")

            self.parent.voiceChatClient.send(room_name.encode('utf-8'))
            response = self.parent.voiceChatClient.recv(4096).decode('utf-8')
            if "Joined room:" in response:
                self.parent.current_room = room_name
                self.parent.is_room_owner = False
                self.parent.show_page("ThirdPage")
            else:
                messagebox.showerror("Error", response)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to attend room: {e}")

    def refresh_rooms(self):
        try:
            if self.parent.voiceChatClient is None:
                print(1)
                raise ConnectionError("Not connected to the server. Please reconnect.")
            print(2)

            self.parent.voiceChatClient.send(b"LIST")
            print(3)

            response = self.parent.voiceChatClient.recv(4096).decode('utf-8')
            print(4)

            self.rooms_listbox.delete(0, tk.END)
            print(5)

            for room in response.split("\n"):
                if room.strip():
                    print(response[room])
                    self.rooms_listbox.insert(tk.END, room)
        except Exception as e:
            print("e")
            messagebox.showerror("Error", f"Failed to refresh rooms: {e}")


class ThirdPage(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent.root)
        self.parent = parent

        tk.Label(self, text=f"Room: {self.parent.current_room}", font=("Arial", 18, "bold")).pack(pady=10)

        users_frame = tk.Frame(self)
        users_frame.pack(expand=True, fill="both", padx=20, pady=10)

        tk.Label(users_frame, text="Users in this Room:", font=("Arial", 14)).pack(pady=5)

        self.users_listbox = tk.Listbox(users_frame, font=("Arial", 12), height=15)
        self.users_listbox.pack(expand=True, fill="both", pady=5)

        bottom_frame = tk.Frame(self, pady=10)
        bottom_frame.pack(fill="x")

        tk.Button(bottom_frame, text="Leave Room", command=self.leave_room, font=("Arial", 12), bg="#FF5722",
                  fg="white").pack(side="left", padx=10)

        if self.parent.is_room_owner:
            tk.Button(bottom_frame, text="Close Room", command=self.close_room, font=("Arial", 12), bg="#D32F2F",
                      fg="white").pack(side="right", padx=10)

        threading.Thread(target=audio_streaming, args=(self.parent.voiceChatClient,), daemon=True).start()

    def leave_room(self):
        self.parent.voiceChatClient.send(b"LEAVE")
        self.parent.show_page("SecondPage")

    def close_room(self):
        """
        Closes the current room if the user is the room owner.
        """
        try:
            print("close room pressed")

            if self.is_room_owner:
                self.voiceChatClient.send(b"CLOSE_ROOM")
                response = self.voiceChatClient.recv(4096).decode('utf-8')
                print(response)
                if "Room closed" in response:
                    messagebox.showinfo("Room Closed", "The room was successfully closed.")
                    self.setup_second_page()
                else:
                    messagebox.showerror("Error", response)

                print("room closed")

            else:
                messagebox.showerror("Error", "Only the room owner can close the room.")
        except Exception as e:
            print("exception")
            messagebox.showerror("Error", f"Failed to close room: {e}")

    def clear_frame(self):
        for widget in self.root.winfo_children():
            widget.destroy()


# Start GUI
if __name__ == "__main__":
    root = tk.Tk()
    app = VoiceChatApp(root)
    root.mainloop()
