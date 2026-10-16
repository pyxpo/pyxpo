"""Send a test push straight to a device through FCM HTTP v1 (no Expo push service).

    python tools/send_push.py --key ~/.pyxpo-secrets/service-account.json --token <device token> \
        --title "Hello" --body "from FCM" --data '{"k": "v"}'

`--token` is what `get_device_push_token_async()` returns on Android (`data`). Leave out --title and --body for a
data-only (silent) message. The service account key sends pushes for the whole project: keep it out of the repo.
Only the standard library and the `openssl` command are used.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SCOPE = "https://www.googleapis.com/auth/firebase.messaging"


def b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def sign(key_pem: str, data: bytes) -> bytes:
    fd, path = tempfile.mkstemp(suffix=".pem")
    try:
        os.chmod(path, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(key_pem)
        return subprocess.run(["openssl", "dgst", "-sha256", "-sign", path], input=data,
                              stdout=subprocess.PIPE, check=True).stdout
    finally:
        os.unlink(path)


def post(url: str, body: bytes, headers: dict) -> dict:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise SystemExit("HTTP %s from %s: %s" % (e.code, url, e.read().decode()))


def access_token(sa: dict) -> str:
    now = int(time.time())
    head = b64(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    claims = b64(json.dumps({"iss": sa["client_email"], "scope": SCOPE, "aud": sa["token_uri"],
                             "iat": now, "exp": now + 3600}).encode())
    unsigned = (head + "." + claims).encode()
    jwt = unsigned.decode() + "." + b64(sign(sa["private_key"], unsigned))
    body = urllib.parse.urlencode({"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                                   "assertion": jwt}).encode()
    return post(sa["token_uri"], body, {"Content-Type": "application/x-www-form-urlencoded"})["access_token"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--key", required=True, help="Firebase service account JSON")
    ap.add_argument("--token", required=True, help="FCM device token")
    ap.add_argument("--title")
    ap.add_argument("--body")
    ap.add_argument("--data", default="{}", help="JSON object of string values")
    ap.add_argument("--channel", help="Android notification channel id")
    a = ap.parse_args()

    sa = json.loads(Path(a.key).expanduser().read_text())
    msg: dict = {"token": a.token, "data": {k: str(v) for k, v in json.loads(a.data).items()}}
    if a.title or a.body:
        msg["notification"] = {k: v for k, v in (("title", a.title), ("body", a.body)) if v}
    if a.channel:
        msg["android"] = {"notification": {"channel_id": a.channel}}
    url = "https://fcm.googleapis.com/v1/projects/%s/messages:send" % sa["project_id"]
    out = post(url, json.dumps({"message": msg}).encode(),
               {"Authorization": "Bearer " + access_token(sa), "Content-Type": "application/json"})
    print("sent", out.get("name"))


if __name__ == "__main__":
    main()
