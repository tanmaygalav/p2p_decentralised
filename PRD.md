Product Requirements Document (PRD): Decentralized P2P Secure Chat

Document Status: V1 - Initial Architecture & Build Plan
Objective: Deliver an end-to-end untraceable communication protocol.
1. Product Overview

Vision: To build an entirely decentralized, untraceable terminal-based communication tool. It eliminates the need for central servers, preventing IP leakage by routing all traffic through Tor Hidden Services and securing data with application-layer Perfect Forward Secrecy.

Target User: Privacy-conscious individuals, journalists, and developers comfortable executing terminal commands and managing local Python environments.
2. Architectural Paradigm Shift

Building a P2P anonymity network requires a complete departure from traditional client-server models. Unlike building serverless API gateways that handle centralized routing, rate limiting, and analytics, this application pushes all routing and security logic directly to the edge nodes. There is no central point to collect analytics or enforce API limits; every instance is simultaneously both a client and a server.

Component,Technology,Purpose
Language,Python 3,Core backend logic and initial CLI implementation.
Networking,libp2p (Python port),"Peer discovery, connection multiplexing, and decentralized routing."
Anonymity,Tor (Stem library),Programmatic creation of .onion ephemeral services to hide IP addresses.
Encryption,cryptography / Signal Protocol,Implementation of the Double Ratchet algorithm for Perfect Forward Secrecy.
Future UI,Electron + React/Next.js,Wrapping the Python binary in a standard full-stack desktop application.

3. Core Requirements (MVP)
Functional Requirements

    Tor Node Generation: On startup, the application must automatically generate a temporary, ephemeral Tor Hidden Service (.onion address).

    Peer Handshake: Users must be able to input a peer's .onion address into the terminal to initiate a connection request.

    Key Exchange: Upon connection, the application must silently perform an Elliptic-Curve Diffie-Hellman (ECDH) key exchange before allowing text input.

    Message Transmission: Text entered into the CLI must be encrypted using the current ratchet key, sent over the Tor socket, and decrypted locally by the receiver's terminal.

Non-Functional Requirements

    Zero State Persistence: Cryptographic keys and .onion addresses must be held only in RAM and destroyed upon application exit to prevent forensic recovery.

    Strict Routing: The application must strictly fail to send data if the Tor daemon connection drops. No fallback to standard TCP/IP is permitted.

4. Step-by-Step Build Plan
Phase 1: Local Environment & Standard P2P

Goal: Establish a basic peer-to-peer terminal chat without Tor or encryption to validate the asynchronous networking logic.

    Set up the core development environment using standard sudo apt package management for system dependencies and pip3 for Python libraries.

    Write a Python script using standard socket programming to bind to localhost.

    Implement a basic asynchronous CLI loop (using asyncio) so the terminal can listen for incoming messages while simultaneously waiting for user keyboard input.

    Milestone: Run two terminal windows side-by-side and seamlessly pass plaintext messages between them over local ports.

Phase 2: The Anonymity Layer (Tor Integration)

Goal: Route the existing socket connections through the Tor network to strip IP metadata.

    Install the Tor daemon on the host machine.

    Import the Stem Python library to programmatically authenticate with and control the Tor controller.

    Modify the Python script to request an ephemeral Hidden Service on startup. The script should print: Your address is: [random-string].onion.

    Update the connection logic so that entering an .onion address routes the traffic through a local SOCKS5 proxy (provided by Tor) instead of making a direct IP connection.

    Milestone: Two separate machines on entirely different networks connect and chat using only .onion addresses, completely hiding their physical IP addresses.

Phase 3: The Encryption Layer (Double Ratchet)

Goal: Ensure the payload is mathematically useless even if a Tor exit node or relay is compromised.

    Integrate the cryptography Python package.

    Implement the initial ECDH handshake to generate a shared master secret between the two peers.

    Implement the Key Derivation Function (KDF) chain. Every time a message is sent or received, the symmetric key used for the payload must advance (ratchet) forward.

    Append a Message Authentication Code (MAC) to each payload to prevent active tampering or man-in-the-middle manipulation.

    Milestone: Capture the local network traffic using a packet sniffer (like Wireshark). Verify that only encrypted ciphertext is visible leaving the application layer.

Phase 4: Full-Stack UI Integration

Goal: Move from a specialized terminal tool to a user-friendly graphical interface.

    Package the stable Python backend into a standalone, distributable executable.

    Build a frontend utilizing modern full-stack web technologies (e.g., React, Tailwind) bundled with Electron or Tauri for cross-platform desktop compatibility.

    Establish an Inter-Process Communication (IPC) bridge or local WebSocket connection so the Python backend can send decrypted message events directly to the frontend UI.

    Milestone: A polished desktop application where users can share .onion addresses and chat via a clean, modern interface.
