#!/usr/bin/env python3
"""notify-telegram: send a message to your Telegram bot/chat. Stdlib only.

  notify-telegram "disk is 90% full"          # message as arguments
  echo "backup finished" | notify-telegram     # or from stdin
Config: ~/.config/telegram-notify (mode 600), two lines:  token=<bot token>  chat_id=<id>
Created by telegram_setup.sh. Exit status is non-zero if the message could not be sent.
"""
import json, os, socket, sys, urllib.parse, urllib.request

CONF = os.environ.get("TELEGRAM_NOTIFY_CONF", os.path.expanduser("~/.config/telegram-notify"))


def load():
    cfg = {}
    for line in open(CONF):
        k, _, v = line.strip().partition("=")
        if k and v: cfg[k] = v
    return cfg["token"], cfg["chat_id"]


def send(text, prefix=True):
    token, chat = load()
    if prefix: text = "[%s] %s" % (socket.gethostname(), text)
    data = urllib.parse.urlencode({"chat_id": chat, "text": text[:4000], "disable_web_page_preview": "true"}).encode()
    req = urllib.request.Request("https://api.telegram.org/bot%s/sendMessage" % token, data=data)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r).get("ok", False)


if __name__ == "__main__":
    msg = " ".join(sys.argv[1:]) or sys.stdin.read().strip()
    if not msg: sys.exit("usage: notify-telegram MESSAGE")
    try:
        sys.exit(0 if send(msg) else 1)
    except Exception as e:
        # never print the token (it is in the URL of an HTTPError)
        sys.exit("notify-telegram failed: %s" % type(e).__name__)
