#!/usr/bin/env python3
"""The PC side of mp3-ps4's live console (mp3/ps4/mp3_ps4_live.cpp, port 7340 on the console).

  live.py --host <PS4 IP> [--port 7340] <command> [<command> ...]    each command's answer, in order
  live.py --host <PS4 IP> --watch [seconds] [command]                 the command (stats) again every few seconds
  live.py --host <PS4 IP>                                             interactive

Commands: stats | get <setting> | set <setting> <value> | save | dump | profile [s] | help
"""
import argparse
import os
import socket
import sys
import time


class Live:
    def __init__(self, host, port):
        self.sock = socket.create_connection((host, port), timeout=15)
        self.buf = b""
        self.answer()  # the greeting

    def answer(self):
        lines = []
        while True:
            while b"\n" not in self.buf:
                data = self.sock.recv(65536)
                if not data:
                    raise ConnectionError("the game closed the connection")
                self.buf += data
            line, self.buf = self.buf.split(b"\n", 1)
            text = line.decode("utf-8", "replace")
            if text == ".":
                return "\n".join(lines)
            lines.append(text)

    def run(self, command):
        self.sock.sendall(command.encode() + b"\n")
        return self.answer()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=os.environ.get("PS4_HOST"), help="the PS4's IP address (default: PS4_HOST)")
    ap.add_argument("--port", type=int, default=7340)
    ap.add_argument("--watch", type=float, nargs="?", const=10.0, help="repeat the command every N seconds")
    ap.add_argument("command", nargs="*")
    a = ap.parse_args()
    if not a.host:
        ap.error("give the PS4's address: --host <IP> (or set PS4_HOST)")
    live = Live(a.host, a.port)
    if a.watch:
        command = " ".join(a.command) or "stats"
        while True:
            print(time.strftime("%H:%M:%S"), live.run(command), flush=True)
            time.sleep(a.watch)
    if a.command:
        # Each argument is one command ("set mp3_60fps false" quoted as one).
        for command in a.command:
            print(f"> {command}\n{live.run(command)}", flush=True)
        return
    while True:
        try:
            command = input("live> ").strip()
        except EOFError:
            return
        if command:
            print(live.run(command))
            if command == "quit":
                return


if __name__ == "__main__":
    sys.exit(main())
