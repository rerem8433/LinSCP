"""SSH connection helper shared by the SFTP and SCP backends."""
from __future__ import annotations

import base64
import hashlib
import os
import socket

import paramiko

from ..config import CONFIG_DIR
from .base import Site

KNOWN_HOSTS = os.path.join(CONFIG_DIR, "known_hosts")


def fingerprint(key: paramiko.PKey) -> str:
    digest = hashlib.sha256(key.asbytes()).digest()
    return f"{key.get_name()} SHA256:{base64.b64encode(digest).decode().rstrip('=')}"


def host_id(host: str, port: int) -> str:
    return host if port == 22 else f"[{host}]:{port}"


class _AskPolicy(paramiko.MissingHostKeyPolicy):
    def __init__(self, trust_cb):
        self.trust_cb = trust_cb

    def missing_host_key(self, client, hostname, key):
        fp = fingerprint(key)
        if self.trust_cb is None or not self.trust_cb("ssh", hostname, fp, False):
            raise paramiko.SSHException("Host key rejected by user")
        _save_key(hostname, key)
        client.get_host_keys().add(hostname, key.get_name(), key)


def _save_key(hostname: str, key: paramiko.PKey, replace: bool = False) -> None:
    os.makedirs(os.path.dirname(KNOWN_HOSTS), exist_ok=True)
    hk = paramiko.HostKeys()
    if os.path.exists(KNOWN_HOSTS):
        try:
            hk.load(KNOWN_HOSTS)
        except Exception:
            pass
    if replace and hostname in hk:
        del hk[hostname]
    hk.add(hostname, key.get_name(), key)
    hk.save(KNOWN_HOSTS)


def _load_pkey(path: str, passphrase: str | None):
    last = None
    classes = [getattr(paramiko, n) for n in ("Ed25519Key", "ECDSAKey", "RSAKey", "DSSKey") if hasattr(paramiko, n)]
    for cls in classes:
        try:
            return cls.from_private_key_file(path, password=passphrase or None)
        except paramiko.PasswordRequiredException:
            raise
        except Exception as e:  # wrong type, try next
            last = e
    raise paramiko.SSHException(f"Unsupported key: {last}")


def open_ssh(site: Site, trust_cb, timeout: float = 15.0) -> paramiko.SSHClient:
    port = site.effective_port()
    client = paramiko.SSHClient()
    # LinSCP keeps its own store (like WinSCP) so ~/.ssh/known_hosts is never modified
    if os.path.exists(KNOWN_HOSTS):
        try:
            client.get_host_keys().load(KNOWN_HOSTS)
        except Exception:
            pass
    client.set_missing_host_key_policy(_AskPolicy(trust_cb))

    kwargs = dict(hostname=site.host, port=port, username=site.user or None,
                  timeout=timeout, banner_timeout=timeout, auth_timeout=timeout)
    if site.auth == "key":
        if site.key_file:
            kwargs["pkey"] = _load_pkey(os.path.expanduser(site.key_file), site.password)
            kwargs.update(look_for_keys=False, allow_agent=False)
        else:
            kwargs.update(look_for_keys=True, allow_agent=True)
    else:
        kwargs.update(password=site.password, look_for_keys=False, allow_agent=False)

    for attempt in range(2):
        try:
            client.connect(**kwargs)
            break
        except paramiko.BadHostKeyException as e:
            hid = host_id(site.host, port)
            if attempt == 0 and trust_cb and trust_cb("ssh", hid, fingerprint(e.key), True):
                _save_key(hid, e.key, replace=True)
                try:
                    del client.get_host_keys()[hid]
                except Exception:
                    pass
                client.get_host_keys().add(hid, e.key.get_name(), e.key)
                continue
            raise
        except paramiko.BadAuthenticationType as e:
            # server only offers keyboard-interactive: answer prompts with the password
            if site.auth == "password" and "keyboard-interactive" in (e.allowed_types or []):
                t = client.get_transport()
                t.auth_interactive(site.user, lambda title, instr, prompts: [site.password for _ in prompts])
                break
            raise
    t = client.get_transport()
    if t is not None:
        t.set_keepalive(30)
        try:
            t.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except Exception:
            pass
    return client
