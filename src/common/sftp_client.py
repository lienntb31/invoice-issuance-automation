"""Thin wrapper around Paramiko for the partner SFTP exchange.

Credentials are never hardcoded: the password is pulled from the OS keyring at
connection time, keyed by (keyring_service, username) from config.py.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

import keyring
import paramiko

from config import SftpConfig


@contextmanager
def connect(cfg: SftpConfig) -> Iterator[paramiko.SFTPClient]:
    password = keyring.get_password(cfg.keyring_service, cfg.username)
    if password is None:
        raise RuntimeError(
            f"No password found in OS keyring for service={cfg.keyring_service!r}, "
            f"username={cfg.username!r}. Set it with keyring.set_password(...) first."
        )
    transport = paramiko.Transport((cfg.host, cfg.port))
    try:
        transport.connect(username=cfg.username, password=password)
        yield paramiko.SFTPClient.from_transport(transport)
    finally:
        transport.close()


def list_remote_files(sftp: paramiko.SFTPClient, remote_dir: str) -> set[str]:
    try:
        return set(sftp.listdir(remote_dir))
    except IOError:
        return set()


def upload_files(
    sftp: paramiko.SFTPClient,
    local_paths: list[str],
    remote_dir: str,
    overwrite: bool = False,
) -> list[str]:
    """Upload each local file to `remote_dir`. Skip existing remote files unless `overwrite`.

    Returns the list of files actually uploaded.
    """
    existing = list_remote_files(sftp, remote_dir)
    uploaded = []
    for local_path in local_paths:
        filename = os.path.basename(local_path)
        if filename in existing and not overwrite:
            continue
        remote_path = f"{remote_dir}/{filename}"
        sftp.put(local_path, remote_path)
        uploaded.append(filename)
    return uploaded


def download_files(
    sftp: paramiko.SFTPClient,
    remote_dir: str,
    local_dir: str,
    prefix: str,
    date_str: str,
    extension: str = ".CSV",
) -> list[str]:
    """Download files from `remote_dir` whose name starts with `prefix + date_str` and ends with `extension`."""
    os.makedirs(local_dir, exist_ok=True)
    downloaded = []
    for filename in list_remote_files(sftp, remote_dir):
        if filename.startswith(f"{prefix}{date_str}") and filename.upper().endswith(extension.upper()):
            local_path = os.path.join(local_dir, filename)
            sftp.get(f"{remote_dir}/{filename}", local_path)
            downloaded.append(local_path)
    return downloaded
