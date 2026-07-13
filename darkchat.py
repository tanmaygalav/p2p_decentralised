import asyncio
import os
import sys
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from stem.control import Controller

# ---------------------------------------------------------------------------
# 1. CRYPTOGRAPHIC ENGINE
# ---------------------------------------------------------------------------
class CryptoSession:
    def __init__(self):
        # Generate ephemeral ECC Private/Public Keypair for this session
        self.private_key = ec.generate_private_key(ec.SECP256R1())
        self.public_key = self.private_key.public_key()
        self.shared_secret = None
        self.symmetric_key = None

    def get_public_bytes(self) -> bytes:
        """Serializes the public key to send across the wire."""
        from cryptography.hazmat.primitives import serialization
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

    def compute_shared_key(self, peer_public_bytes: bytes):
        """Performs ECDH and derives a 256-bit symmetric key via HKDF."""
        from cryptography.hazmat.primitives import serialization
        peer_public_key = serialization.load_der_public_key(peer_public_bytes)
        
        # Calculate raw shared secret
        self.shared_secret = self.private_key.exchange(ec.ECDH(), peer_public_key)
        
        # Derive symmetric key
        self.symmetric_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b'darkchat-e2ee-salt',
        ).derive(self.shared_secret)

    def encrypt(self, plaintext: str) -> bytes:
        """Encrypts data using AES-GCM."""
        if not self.symmetric_key:
            raise ValueError("Symmetric key not derived yet.")
        aesgcm = AESGCM(self.symmetric_key)
        nonce = os.urandom(12)  # 96-bit unique nonce per message
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
        return nonce + ciphertext

    def decrypt(self, payload: bytes) -> str:
        """Decrypts AES-GCM payload."""
        if not self.symmetric_key:
            raise ValueError("Symmetric key not derived yet.")
        nonce = payload[:12]
        ciphertext = payload[12:]
        aesgcm = AESGCM(self.symmetric_key)
        decrypted_bytes = aesgcm.decrypt(nonce, ciphertext, None)
        return decrypted_bytes.decode()


# ---------------------------------------------------------------------------
# 2. NETWORKING & CLI INTERACTION
# ---------------------------------------------------------------------------
class P2PChatNode:
    def __init__(self, local_port=8888, tor_control_port=9051):
        self.local_port = local_port
        self.tor_control_port = tor_control_port
        self.crypto = CryptoSession()
        self.reader = None
        self.writer = None
        self.onion_address = None
        self.tor_hidden_service = None

    async def init_tor_service(self):
        """Connects to Tor and configures an ephemeral Hidden Service."""
        print("[*] Connecting to Tor Controller...")
        try:
            with Controller.from_port(port=self.tor_control_port) as controller:
                controller.authenticate()
                print("[*] Creating ephemeral Tor Hidden Service...")
                
                # Maps external onion port 80 to our local application running port
                # FIXED: The exact stem parameter is await_publication
                response = controller.create_ephemeral_hidden_service({80: self.local_port}, await_publication=True)
                self.onion_address = f"{response.service_id}.onion"
                print(f"\n=========================================")
                print(f" YOUR ONION ADDRESS: {self.onion_address}")
                print(f" Share this address securely with your peer.")
                print(f"=========================================\n")
        except Exception as e:
            print(f"[!] Tor Connection Failed: {e}")
            print("[!] Defaulting to local operational mode (no Tor insulation).")
            self.onion_address = "localhost"

    async def handle_incoming_peer(self, reader, writer):
        """Callback executed when a remote peer initiates a connection."""
        if self.writer:
            # Drop subsequent connection attempts if a session exists
            writer.close()
            return
        
        print("[*] Incoming peer connected. Performing key exchange...")
        self.reader = reader
        self.writer = writer
        await self.perform_key_exchange(is_host=True)

    async def connect_to_peer(self, peer_onion: str):
        """Establishes an outbound connection to the peer's onion service via SOCKS5."""
        print(f"[*] Resolving and connecting to {peer_onion}...")
        
        try:
            if ".onion" in peer_onion:
                print("[*] Routing connection via Tor SOCKS5 proxy (127.0.0.1:9050)...")
                
                # 1. Connect to the local Tor proxy
                self.reader, self.writer = await asyncio.open_connection('127.0.0.1', 9050)
                
                # 2. SOCKS5 Greeting: [Version 5] [1 Auth Method] [No Auth]
                self.writer.write(b'\x05\x01\x00')
                await self.writer.drain()
                
                response = await self.reader.readexactly(2)
                if response != b'\x05\x00':
                    raise Exception("Tor SOCKS5 proxy rejected connection.")
                
                # 3. SOCKS5 Connect Request to the .onion address
                port = 80 # The port Tor is exposing for the hidden service
                req = b'\x05\x01\x00\x03' + len(peer_onion).to_bytes(1, 'big') + peer_onion.encode() + port.to_bytes(2, 'big')
                self.writer.write(req)
                await self.writer.drain()
                
                # 4. Parse the proxy response to ensure circuit is established
                resp_header = await self.reader.readexactly(4)
                if resp_header[1] != 0x00:
                    raise Exception(f"Tor failed to connect to peer. Error code: {resp_header[1]}")
                
                # Clear the rest of the proxy response buffer based on address type
                addr_type = resp_header[3]
                if addr_type == 0x01:   # IPv4
                    await self.reader.readexactly(6)
                elif addr_type == 0x03: # Domain
                    domain_len = int.from_bytes(await self.reader.readexactly(1), 'big')
                    await self.reader.readexactly(domain_len + 2)
                    
                print("[*] Tor circuit established! Initiating key exchange...")
            else:
                # Fallback for local testing (localhost:8888)
                host, port = "127.0.0.1", int(peer_onion.split(":")[-1])
                self.reader, self.writer = await asyncio.open_connection(host, port)
                print("[*] Connected to local peer. Initiating key exchange...")

            # 5. Hand off to the cryptographic engine
            await self.perform_key_exchange(is_host=False)
            
        except Exception as e:
            print(f"[!] Connection failed: {e}")
            sys.exit(1)

    async def perform_key_exchange(self, is_host: bool):
        """Exchanges public keys and creates the absolute E2EE session."""
        try:
            my_pub_bytes = self.crypto.get_public_bytes()
            
            if is_host:
                # Host waits for client public key, then transmits its own
                peer_pub_bytes = await self.reader.readexactly(91) # SECP256R1 DER key size
                self.writer.write(my_pub_bytes)
                await self.writer.drain()
            else:
                # Client transmits public key, then reads host response
                self.writer.write(my_pub_bytes)
                await self.writer.drain()
                peer_pub_bytes = await self.reader.readexactly(91)

            self.crypto.compute_shared_key(peer_pub_bytes)
            print("[+] E2EE Handshake complete. Connection is entirely encrypted.\n")
            
            # Fire up concurrent read/write loops
            asyncio.create_task(self.read_loop())
            await self.write_loop()

        except Exception as e:
            print(f"[!] Handshake failed: {e}")
            self.close_connection()

    async def read_loop(self):
        """Continuously listens for incoming encrypted payloads."""
        try:
            while True:
                # Read structural length prefix (4 bytes)
                length_bytes = await self.reader.readexactly(4)
                length = int.from_bytes(length_bytes, byteorder='big')
                
                # Read actual encrypted payload
                encrypted_payload = await self.reader.readexactly(length)
                decrypted_message = self.crypto.decrypt(encrypted_payload)
                
                print(f"\r[Peer]: {decrypted_message}")
                print("[You]: ", end="", flush=True)
        except (asyncio.IncompleteReadError, ConnectionResetError):
            print("\n[!] Peer disconnected.")
        finally:
            self.close_connection()

    async def write_loop(self):
        """Listens for user console inputs to encrypt and broadcast."""
        loop = asyncio.get_event_loop()
        try:
            while True:
                # Run synchronous input() safely inside async workflow
                user_input = await loop.run_in_executor(None, input, "[You]: ")
                if user_input.strip() == "/exit":
                    break
                
                if user_input.strip():
                    encrypted_data = self.crypto.encrypt(user_input)
                    length_prefix = len(encrypted_data).to_bytes(4, byteorder='big')
                    
                    self.writer.write(length_prefix + encrypted_data)
                    await self.writer.drain()
        except Exception as e:
            print(f"\n[!] Send error: {e}")
        finally:
            self.close_connection()

    def close_connection(self):
        """Wipes active components from process memory cleanly."""
        if self.writer:
            self.writer.close()
        print("[*] Secure session closed. Memory cleared.")
        sys.exit(0)

    async def start(self):
        # 1. Initialize Tor Hidden Service
        await self.init_tor_service()
        
        # 2. Open standard TCP daemon listening infrastructure
        server = await asyncio.start_server(self.handle_incoming_peer, '127.0.0.1', self.local_port)
        
        print("[*] Listening loop initialized.")
        print("    Type /exit to leave at any time.")
        print("    Enter a peer's onion address to connect, or wait for inbound calls.")
        
        # 3. Handle asynchronous CLI menu selection
        loop = asyncio.get_event_loop()
        choice = await loop.run_in_executor(None, input, "\nEnter target peer address (or press Enter to wait): ")
        
        if choice.strip():
            await self.connect_to_peer(choice.strip())
        else:
            print("[*] Waiting patiently for secure inbound connection...")
            async with server:
                await server.serve_forever()

# ---------------------------------------------------------------------------
# 3. PROCESS INITIALIZATION
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Custom port assignments allowed via command line arguments for local debugging
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8888
    node = P2PChatNode(local_port=port)
    try:
        asyncio.run(node.start())
    except KeyboardInterrupt:
        print("\n[*] Process terminated via user signal.")