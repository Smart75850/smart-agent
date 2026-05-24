import os

import requests

SIGN_SRV_URL = os.getenv("SIGN_SRV_URL", "http://127.0.0.1:9001")


class SignSrvUnavailable(Exception):
    pass


def sign(url: str) -> dict:
    try:
        resp = requests.post(
            f"{SIGN_SRV_URL}/sign",
            json={"url": url},
            timeout=3,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        raise SignSrvUnavailable(f"SignSrv 不可用: {e}") from e
