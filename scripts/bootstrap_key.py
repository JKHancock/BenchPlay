#!/usr/bin/env python3
"""密码一次性 -> 持久密钥引导. 门禁: 密钥复验 whoami == 用户名.
用法: python bootstrap_key.py <host> <user> [password]
依赖: paramiko (Vllm_Benchmark venv 已装). 输出: PASS/FAIL + 证据一行.
"""
import os
import subprocess
import sys

import paramiko

KEY = os.path.expanduser("~/.ssh/benchplaybook_ed25519")


def ensure_key():
    if os.path.exists(KEY):
        return
    os.makedirs(os.path.dirname(KEY), exist_ok=True)
    subprocess.run(
        ["ssh-keygen", "-t", "ed25519", "-N", "", "-C", "benchplaybook", "-f", KEY],
        check=True, capture_output=True)


def append_key(host, user, password):
    pub = open(KEY + ".pub").read().strip()
    cmd = (f"mkdir -p ~/.ssh && chmod 700 ~/.ssh && touch ~/.ssh/authorized_keys && "
           f"chmod 600 ~/.ssh/authorized_keys && "
           f"grep -qF '{pub}' ~/.ssh/authorized_keys || echo '{pub}' >> ~/.ssh/authorized_keys")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(host, username=user, password=password, timeout=15)
    _, out, err = client.exec_command(cmd)
    code = out.channel.recv_exit_status()
    client.close()
    if code != 0:
        raise SystemExit(f"FAIL 公钥追加失败: {err.read().decode()[:200]}")


def verify(host, user):
    """门禁: 密钥登录 whoami 必须==user."""
    probe = subprocess.run(
        ["ssh", "-i", KEY, "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no",
         f"{user}@{host}", "whoami"],
        capture_output=True, text=True, timeout=20)
    got = probe.stdout.strip()
    if probe.returncode == 0 and got == user:
        print(f"PASS 密钥复验通过 (whoami={got})")
    else:
        raise SystemExit(f"FAIL 密钥复验 whoami={got!r} rc={probe.returncode}")


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    host, user = sys.argv[1], sys.argv[2]
    password = sys.argv[3] if len(sys.argv) > 3 else None
    ensure_key()
    if password:
        append_key(host, user, password)
    verify(host, user)


if __name__ == "__main__":
    main()
