"""メッセージに列が増えたとき、厳密に読む側と、知らない列を無視する側で何が起きるかを数えます。"""
import json

KNOWN = {"id", "category", "arrival"}


def make_messages(n=1000, new_field_from=700):
    """前半は古い形、new_field_from 件目からは coupon という列が増えた形のメッセージ。"""
    messages = []
    for i in range(n):
        body = {"id": i, "category": "寝具", "arrival": i}
        if i >= new_field_from:
            body["coupon"] = "SPRING"
        messages.append(json.dumps(body))
    return messages


def read_strict(message):
    """知っている列だけを許す読み方。知らない列があると例外にします。"""
    body = json.loads(message)
    extra = set(body) - KNOWN
    if extra:
        raise ValueError(f"知らない列: {sorted(extra)}")
    return body


def read_tolerant(message):
    """知らない列は読み捨てる読み方。"""
    body = json.loads(message)
    return {k: v for k, v in body.items() if k in KNOWN}


def count_failures(messages, reader):
    """読めなかったメッセージの数。"""
    failures = 0
    for message in messages:
        try:
            reader(message)
        except ValueError:
            failures += 1
    return failures
