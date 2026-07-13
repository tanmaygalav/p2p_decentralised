import asyncio
import os
import sys
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from stem.control import Controller
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Input, Log

# ---------------------------------------------------------------------------
# 1. CRYPTOGRAPHIC ENGINE
# ---------------------------------------------------------------------------
class CryptoSession:
    def __init__(self):
        self.private_key = ec.generate_private_key(ec.SECP256R1())
        self.public_key = self.private_key.public_key()
        self.shared_secret = None
        self.symmetric_key = None

    def get_public_bytes(self) -> bytes:
        from cryptography.hazmat.primitives import serialization
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

    def compute_shared_key(self, peer_public_bytes: bytes):
        from cryptography.hazmat.primitives import serialization
        peer_public_key = serialization.load_der_public_key(peer_public_bytes)
        self.shared_secret = self.private_key.exchange(ec.ECDH(), peer_public_key)
        self.symmetric_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b'darkchat-e2ee-salt',
        ).derive(self.shared_secret)

    def encrypt(self, plaintext: str) -> bytes:
        aesgcm = AESGCM(self.symmetric_key)
        nonce = os.urandom(12)
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
        return nonce + ciphertext

    def decrypt(self, payload: bytes) -> str:
        nonce = payload[:12]
        ciphertext = payload[12:]
        aesgcm = AESGCM(self.symmetric_key)
        return aesgcm.decrypt(nonce, ciphertext, None).decode()

# ---------------------------------------------------------------------------
# 2. TERMINAL UI & ASYNC NETWORKING
# ---------------------------------------------------------------------------
class DarkChatApp(App):
    CSS = """
    #chat-log {
        height: 1fr;
        border: round green;
        padding: 0 1;
    }
    Input {
        dock: bottom;
        margin: 1 0;
    }
    """
    
    BINDINGS = [
        ("ctrl+q", "quit", "Destroy Keys & Exit"),
        ("ctrl+c", "copy_onion", "Copy .onion Address"), # Add this line
    ]

    def __init__(self, local_port):
        super().__init__()
        self.local_port = local_port
        self.crypto = CryptoSession()
        self.reader = None
        self.writer = None
        self.is_connected = False

    def compose(self) -> ComposeResult:
        """Constructs the UI layout."""
        yield Header(show_clock=True)
        yield Log(id="chat-log", highlight=False)
        yield Input(placeholder="Enter Peer's .onion address to connect...", id="message-input")
        yield Footer()

    async def on_mount(self) -> None:
        """Executes the moment the UI paints to the screen."""
        self.title = "DarkChat - Untraceable E2EE"
        self.sub_title = "Booting Tor Node..."
        self.log_widget = self.query_one("#chat-log", Log)
        self.input_widget = self.query_one("#message-input", Input)
        
        # Fire off the Tor initialization in the background
        self.run_worker(self.startup_network_routine())

    # --- UI Formatting Helpers ---
    def write_system(self, text: str):
        self.log_widget.write_line(f"[*] {text}")

    def write_peer(self, text: str):
        self.log_widget.write_line(f"=== [Peer]: {text}")
        
    def write_me(self, text: str):
        self.log_widget.write_line(f">>> [You]: {text}")

    def action_copy_onion(self):
        """Copies the generated onion address to the system clipboard."""
        if self.crypto and hasattr(self, 'onion_address'):
            self.copy_to_clipboard(self.onion_address)
            self.write_system("Address copied to clipboard!")
        else:
            self.write_system("Address not ready yet...")

    # --- Background Network Routines ---
    async def startup_network_routine(self):
        """Authenticates with Tor, registers the node, and starts the TCP listener."""
        self.write_system("Authenticating with local Tor Controller...")
        try:
            # FIX: Instantiate directly and save to self so the connection stays open
            self.tor_controller = Controller.from_port(port=9051)
            self.tor_controller.authenticate()
            self.write_system("Publishing ephemeral Tor Hidden Service (this takes a few seconds)...")
            
            response = self.tor_controller.create_ephemeral_hidden_service({80: self.local_port}, await_publication=True)
            self.onion_address = f"{response.service_id}.onion"
            
            self.sub_title = f"Your Address: {self.onion_address}"
            self.write_system("=========================================")
            self.write_system(f" YOUR ADDRESS: {self.onion_address}")
            self.write_system("=========================================")
        except Exception as e:
            self.write_system(f"Tor setup failed: {e}")
            self.sub_title = f"Offline Mode (Port {self.local_port})"

        self.write_system("Ready. Waiting for inbound connection, or enter a peer's address below.")
        
        # Start background server
        server = await asyncio.start_server(self.handle_incoming_peer, '127.0.0.1', self.local_port)
        async with server:
            await server.serve_forever()

    async def on_input_submitted(self, event: Input.Submitted):
        """Triggers every time the user presses Enter in the Input box."""
        user_text = event.value.strip()
        self.input_widget.value = "" # Instantly clear input bar
        
        if not user_text:
            return
            
        if not self.is_connected:
            # If not connected, assume the input is a target address
            self.write_system(f"Attempting to resolve and connect to {user_text}...")
            self.run_worker(self.connect_to_peer(user_text))
        else:
            # If connected, assume the input is a chat message
            self.write_me(user_text)
            try:
                encrypted_data = self.crypto.encrypt(user_text)
                length_prefix = len(encrypted_data).to_bytes(4, byteorder='big')
                self.writer.write(length_prefix + encrypted_data)
                await self.writer.drain()
            except Exception as e:
                self.write_system(f"Send error: {e}")

    async def handle_incoming_peer(self, reader, writer):
        if self.writer:
            writer.close()
            return
        self.write_system("Incoming peer connected. Performing key exchange...")
        self.reader = reader
        self.writer = writer
        await self.perform_key_exchange(is_host=True)

    async def connect_to_peer(self, peer_onion: str):
        try:
            if ".onion" in peer_onion:
                self.write_system("Routing via Tor SOCKS5 proxy (127.0.0.1:9050)...")
                self.reader, self.writer = await asyncio.open_connection('127.0.0.1', 9050)
                
                # SOCKS5 Handshake
                self.writer.write(b'\x05\x01\x00')
                await self.writer.drain()
                await self.reader.readexactly(2)
                
                req = b'\x05\x01\x00\x03' + len(peer_onion).to_bytes(1, 'big') + peer_onion.encode() + (80).to_bytes(2, 'big')
                self.writer.write(req)
                await self.writer.drain()
                
                resp_header = await self.reader.readexactly(4)
                addr_type = resp_header[3]
                if addr_type == 0x01:
                    await self.reader.readexactly(6)
                elif addr_type == 0x03:
                    domain_len = int.from_bytes(await self.reader.readexactly(1), 'big')
                    await self.reader.readexactly(domain_len + 2)
                    
                self.write_system("Tor circuit established! Initiating key exchange...")
            else:
                host, port = "127.0.0.1", int(peer_onion.split(":")[-1])
                self.reader, self.writer = await asyncio.open_connection(host, port)
                self.write_system("Connected to local peer. Initiating key exchange...")

            await self.perform_key_exchange(is_host=False)
            
        except Exception as e:
            self.write_system(f"Connection failed: {e}")

    async def perform_key_exchange(self, is_host: bool):
        try:
            my_pub_bytes = self.crypto.get_public_bytes()
            if is_host:
                peer_pub_bytes = await self.reader.readexactly(91)
                self.writer.write(my_pub_bytes)
                await self.writer.drain()
            else:
                self.writer.write(my_pub_bytes)
                await self.writer.drain()
                peer_pub_bytes = await self.reader.readexactly(91)

            self.crypto.compute_shared_key(peer_pub_bytes)
            self.write_system("E2EE Handshake complete. Connection is entirely encrypted.")
            self.is_connected = True
            self.input_widget.placeholder = "Type your message and press Enter..."
            
            # Start continuous read loop
            self.run_worker(self.read_loop())

        except Exception as e:
            self.write_system(f"Handshake failed: {e}")

    async def read_loop(self):
        try:
            while True:
                length_bytes = await self.reader.readexactly(4)
                length = int.from_bytes(length_bytes, byteorder='big')
                encrypted_payload = await self.reader.readexactly(length)
                decrypted_message = self.crypto.decrypt(encrypted_payload)
                self.write_peer(decrypted_message)
        except (asyncio.IncompleteReadError, ConnectionResetError):
            self.write_system("Peer disconnected.")
            self.is_connected = False
            self.input_widget.placeholder = "Enter Peer's .onion address to connect..."

# ---------------------------------------------------------------------------
# 3. INITIALIZATION
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8888
    app = DarkChatApp(local_port=port)
    app.run()