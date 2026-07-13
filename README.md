# 🌑 P2PEXE
**Decentralized. Untraceable. Amnesiac.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Platform: Linux](https://img.shields.io/badge/Platform-Linux-lightgrey.svg)]()
[![Network: Tor](https://img.shields.io/badge/Network-Tor-7D4698.svg)]()

DarkChat is a paranoia-grade, peer-to-peer terminal chat application. It completely bypasses traditional client-server architecture, utilizing Tor Ephemeral Hidden Services and Perfect Forward Secrecy to create mathematically untraceable communication sockets directly in your Linux terminal.

There are no central servers. There are no databases. The moment you quit, the cryptographic keys are destroyed, the `.onion` address collapses, and the node vanishes from the Dark Web.

---

## ⚡ Core Architecture

* **The Anonymity Layer (Tor):** Generates ephemeral `.onion` nodes on startup. Traffic is routed through SOCKS5 proxies across global encrypted relays, ensuring total IP obfuscation.
* **The Cryptographic Engine:** Implements an Elliptic-Curve Diffie-Hellman (ECDH) key exchange to derive Perfect Forward Secrecy. Payloads are secured using AES-GCM authenticated encryption.
* **The Interface (Textual):** A high-performance, asynchronous Terminal User Interface (TUI) that feels like a native desktop app, built entirely for the shell.
* **Amnesiac State:** Zero state persistence. Keys and routing coordinates exist purely in RAM.

---

## 🚀 Installation

Forget compiling from source or fighting with virtual environments. DarkChat is packaged as a native Debian binary and hosted on a zero-config APT repository.

Drop this one-liner into your terminal to trust the repository and install the daemon:

```bash
echo "deb [trusted=yes] [https://tanmaygalav.github.io/p2pexe-repo](https://tanmaygalav.github.io/p2pexe-repo) ./" | sudo tee /etc/apt/sources.list.d/p2pexe.list && sudo apt update && sudo apt install p2pexe
```
*Note: The `apt` package manager will automatically resolve dependencies, install the background Tor daemon, and configure your system control ports.*

---

## 💻 Usage

Launch the node from anywhere on your system:
```bash
sudo darkchat
```

### The Handshake Protocol
1. **Initialize:** Wait for the local Tor Controller to sync and publish your temporary `.onion` coordinate (displayed in the top header).
2. **Share:** Transmit your `.onion` address to your peer via an out-of-band channel.
3. **Connect:** The peer pastes your `.onion` address into their input bar.
4. **Exchange:** DarkChat automatically establishes the Tor circuit, executes the 91-byte SECP256R1 handshake, and drops you into a secure socket.

**Hotkeys:**
* `Ctrl + C`: Instantly copy your current `.onion` address to the system clipboard.
* `Ctrl + Q`: Sever the connection, shred the session keys, and exit.

---

## 🛠️ Tech Stack

* **Language:** Python 3
* **Networking Engine:** `asyncio` & Socket multiplexing
* **Anonymity:** `Stem` (Tor Controller API)
* **Encryption:** `cryptography` (ECDH, HKDF, AES-GCM)
* **UI Framework:** `Textual` (Asynchronous TUI)
* **Distribution:** `dpkg` / GitHub Pages

---

## ⚠️ Disclaimer
DarkChat is designed as a technical prototype for decentralized networking and cryptographic routing. While it utilizes industry-standard encryption algorithms and the Tor network, it has not undergone an independent security audit. Use at your own risk.
