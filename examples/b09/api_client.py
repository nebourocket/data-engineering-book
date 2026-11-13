"""REST API から全ページを取り込むクライアント (ページング・429 への待機・認証)。"""
import time

import requests


def get_json(url, token, params=None, sleep=time.sleep, max_attempts=5):
    """GET して JSON を返します。429 は Retry-After の秒数だけ待って再試行します。"""
    for attempt in range(1, max_attempts + 1):
        response = requests.get(url, params=params, headers={"Authorization": f"Bearer {token}"}, timeout=10)
        if response.status_code == 429:
            # Retry-After が無い API もあるので、無ければ 1, 2, 4 ... 秒の指数バックオフにする
            if attempt == max_attempts:
                break  # 最後の 429 のあとは待たずに諦める
            wait = float(response.headers.get("Retry-After", 2 ** (attempt - 1)))
            sleep(wait)
            continue
        response.raise_for_status()  # 401 や 500 はここで例外にする (待っても直らないものは再試行しない)
        return response.json()
    raise RuntimeError(f"{max_attempts} 回続けて 429 でした: {url}")


def fetch_all(base_url, token, limit=500, sleep=time.sleep):
    """after_id を進めながら全ページを集めます (カーソル方式)。"""
    rows, after_id = [], 0
    while after_id is not None:
        body = get_json(f"{base_url}/orders", token, {"limit": limit, "after_id": after_id}, sleep)
        rows.extend(body["items"])
        after_id = body["next_after_id"]
    return rows
