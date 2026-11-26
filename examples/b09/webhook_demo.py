"""Webhook 受け口の動作確認です。python examples/b09/webhook_demo.py で実行します。"""
import json
import urllib.error
import urllib.request

import webhook_receiver as webhook


def post(url, body, signature):
    request = urllib.request.Request(url, data=body, headers={"X-Signature": signature}, method="POST")
    try:
        return urllib.request.urlopen(request).status
    except urllib.error.HTTPError as e:
        return e.code


bodies = [json.dumps({"event_id": f"evt-{i}", "type": "order.placed"}).encode() for i in (1, 2, 3)]
with webhook.Receiver() as rx:
    for body in bodies:
        print("配信", json.loads(body)["event_id"], "->", post(rx.url, body, webhook.sign(body)))
    print("再送 evt-2 ->", post(rx.url, bodies[1], webhook.sign(bodies[1])))
    print("署名が違う evt-3 ->", post(rx.url, bodies[2], "0" * 64))
    print("保存された行数:", rx.count())
