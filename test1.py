import time
import hmac
import hashlib
import base64
import requests
import json

API_KEY = "6894bd32c714e80001ef887a"
API_SECRET = "6f307557-c4a5-4d54-a28c-da40124dc700"
API_PASSPHRASE = "Nfx921011."

def get_ws_token():
    url = "https://api-futures.kucoin.com/api/v1/bullet-private"
    ts = str(int(time.time() * 1000))
    sign = base64.b64encode(
        hmac.new(
            API_SECRET.encode(),
            f"{ts}POST/api/v1/bullet-private".encode(),
            hashlib.sha256
        ).digest()
    ).decode()

    headers = {
        "KC-API-KEY": API_KEY,
        "KC-API-SIGN": sign,
        "KC-API-TIMESTAMP": ts,
        "KC-API-PASSPHRASE": base64.b64encode(
            hmac.new(API_SECRET.encode(), API_PASSPHRASE.encode(), hashlib.sha256).digest()
        ).decode(),
        "KC-API-KEY-VERSION": "2",
    }

    return requests.post(url, headers=headers).json()

data = get_ws_token()["data"]
ws_url = data["instanceServers"][0]["endpoint"]
token = data["token"]

import websocket
import json
import threading

def on_message(ws, message):
    print(message)
    msg = json.loads(message)
    if msg.get("type") == "message" and msg.get("topic") == "/contract/positionAll":
        handle_position(msg["data"])

def handle_position(data):
    print('datassss')
    for pos in data:
        print(
            pos["symbol"],
            pos["side"],
            pos["size"],
            pos["entryPrice"],
            pos["unrealisedPnl"],
            pos["liquidationPrice"],
            pos["marginMode"],
        )

def on_open(ws):
    sub = {
        "id": 1,
        "type": "subscribe",
        "topic": "/contract/positionAll",
        "privateChannel": True,
        "response": True
    }
    ws.send(json.dumps(sub))
    print("aaa")

def on_error(ws, error):
    print("WS error:", error)


def on_close(ws, code, reason):
    print("WS closed:", code, reason)

ws = websocket.WebSocketApp(
    f"{ws_url}?token={token}",
    on_open=on_open,
    on_message=on_message,
    on_error=on_error,
    on_close=on_close,
)

threading.Thread(target=ws.run_forever, daemon=True).start()

while True:
    time.sleep(1)

