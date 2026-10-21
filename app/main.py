#!/usr/bin/env python3
"""The software: starts the local engine (server.py) on a free port and shows it in its own window (no browser)."""
import os, socket, sys, threading
import webview

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import server


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


if __name__ == "__main__":
    port = free_port()
    threading.Thread(target=lambda: server.app.run("127.0.0.1", port), daemon=True).start()
    webview.create_window("WhatsApp 客户提取", f"http://127.0.0.1:{port}/", width=1150, height=800, min_size=(900, 600))
    webview.start()
