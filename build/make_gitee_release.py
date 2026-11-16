#!/usr/bin/env python3
"""Make the Gitee update folder for one version (PLAN E, 11-17): <out>/current.json (signed) + <out>/app-<v>.zip.
Usage: python build/make_gitee_release.py <app.zip> <out_dir>
The signing key is read from env WAT_UPDATE_SIGNING_KEY or the Galaxy .env (never printed, never written to <out>).
Push <out> to gitee.com/Jalane/whatsapp-lead-update (master) only after the boss says yes."""
import base64, hashlib, json, os, sys, zipfile
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

HERE = os.path.dirname(os.path.abspath(__file__))
PUBKEY = "aTYJQu13U0NvufHXrG5eXkVO+RmiLMLwMANlAfLt0kY="   # must equal launcher.py PUBKEY


def signing_key():
    v = os.environ.get("WAT_UPDATE_SIGNING_KEY", "")
    if not v:
        env = os.path.join(HERE, "..", "..", "..", "..", ".env")         # Galaxy/.env
        for line in open(env, encoding="utf-8"):
            if line.startswith("WAT_UPDATE_SIGNING_KEY="): v = line.split("=", 1)[1].strip()
    if not v: sys.exit("WAT_UPDATE_SIGNING_KEY missing")
    return Ed25519PrivateKey.from_private_bytes(base64.b64decode(v))


def make(app_zip, out, key):
    with zipfile.ZipFile(app_zip) as z:
        version = z.read("VERSION").decode("utf-8").strip()
    data = open(app_zip, "rb").read()
    name = f"app-{version}.zip"
    payload = json.dumps({"app": "whatsapp-lead-tool", "version": version, "zip": name,
                          "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}, sort_keys=True).encode()
    pub = base64.b64encode(key.public_key().public_bytes_raw()).decode()
    if pub != PUBKEY: sys.exit("signing key does not match the launcher's public key")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, name), "wb") as f: f.write(data)
    with open(os.path.join(out, "current.json"), "w", encoding="utf-8") as f:
        json.dump({"payload": base64.b64encode(payload).decode(), "sig": base64.b64encode(key.sign(payload)).decode()}, f)
    return version, name


if __name__ == "__main__":
    v, n = make(sys.argv[1], sys.argv[2], signing_key())
    print(f"ok version={v} files=current.json,{n} -> {sys.argv[2]}")
