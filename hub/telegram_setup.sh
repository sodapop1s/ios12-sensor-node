#!/bin/bash
# One-time setup of notify-telegram. Run on the server (ssh -t). Nothing you type is echoed or logged.
#  1. In Telegram, talk to @BotFather: /newbot -> pick a name -> it gives you a TOKEN (a secret).
#  2. Run this, paste the token when asked.
#  3. Send any message (e.g. "hi") to your new bot in Telegram when told to; the script finds your chat id itself.
set -e
CONF="$HOME/.config/telegram-notify"
mkdir -p "$HOME/.config" "$HOME/bin"
printf "Paste the bot token from @BotFather (hidden): "
stty -echo; read TOKEN; stty echo; echo
python3 - "$TOKEN" "$CONF" <<'PY'
import json, os, sys, time, urllib.request
token, conf = sys.argv[1], sys.argv[2]
def api(m): return json.load(urllib.request.urlopen("https://api.telegram.org/bot%s/%s" % (token, m), timeout=35))
try: me = api("getMe")["result"]
except Exception: sys.exit("That token was rejected by Telegram. Check it and run again.")
print("Bot found: @%s" % me["username"])
print("Now open Telegram and send any message to @%s (waiting up to 90 s)..." % me["username"])
chat, t0 = None, time.time()
while time.time() - t0 < 90 and chat is None:
    for u in api("getUpdates?timeout=10")["result"]:
        m = u.get("message") or u.get("channel_post")
        if m: chat = m["chat"]["id"]; who = m["chat"].get("first_name") or m["chat"].get("title") or "chat"
if chat is None: sys.exit("No message received. Send one to the bot and run this again.")
fd = os.open(conf, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w") as f: f.write("token=%s\nchat_id=%s\n" % (token, chat))
print("Saved %s (mode 600) for %s." % (conf, who))
PY
unset TOKEN
install -m 755 "$(dirname "$0")/notify_telegram.py" "$HOME/bin/notify-telegram"
"$HOME/bin/notify-telegram" "Test: this server can now send you alerts." && echo "Test message sent - check Telegram."
