"""AWS MCP用の認証確認。認証情報を出力・保存しない。Python 3.11以上。"""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time

WAIT_SECONDS = 180
ENDPOINT = "https://aws-mcp.us-east-1.api.aws/mcp"


def validate(profile, region):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.@+-]{0,127}", profile):
        raise ValueError("プロファイル名は英数字で始まる128文字以内の英数字・_.@+-にしてください。")
    if not re.fullmatch(r"[a-z]{2}(?:-[a-z0-9]+)+-\d+", region):
        raise ValueError("AWSリージョン名を確認してください。")


def environment(profile, region):
    env = os.environ.copy()
    # 明示したプロファイルと、親プロセスの一時認証情報を混在させない。
    for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_SECURITY_TOKEN"):
        env.pop(key, None)
    env.update(AWS_PROFILE=profile, AWS_MCP_PROXY_PROFILES=profile,
               AWS_REGION=region, AWS_DEFAULT_REGION=region, AWS_PAGER="")
    return env


def check_auth(aws, profile, region):
    result = subprocess.run(
        [aws, "sts", "get-caller-identity", "--profile", profile, "--region", region,
         "--query", "Account != "+chr(96)+"null"+chr(96), "--output", "text", "--no-cli-pager"],
        env=environment(profile, region), capture_output=True, text=True, timeout=20)
    if result.returncode == 0:
        return True
    expired = ("refresh token has expired", "session has expired", "loginrefreshrequired",
               "expiredtoken", "unable to locate credentials")
    if any(message in result.stderr.lower() for message in expired):
        return False
    raise RuntimeError("AWS接続確認に失敗しました。ネットワーク・権限・プロファイル設定を確認してください。自動ログインは実行しません。")


def login(aws, profile, region):
    if sys.stdin.isatty():
        result = subprocess.run([aws, "login", "--profile", profile, "--region", region],
                                env=environment(profile, region), timeout=WAIT_SECONDS)
        if result.returncode:
            raise RuntimeError("ログインに失敗、またはキャンセルされました。")
        return
    if sys.platform != "darwin":
        raise RuntimeError("このOSのGUI起動では自動ログインできません。端末で同じヘルパーに --login-only を付けて実行後、MCPを再接続してください。")
    command = shlex.join([sys.executable, str(Path(__file__).resolve()),
                         "--profile", profile, "--region", region, "--login-only"])
    apple = 'tell application "Terminal"\nactivate\ndo script '+json.dumps(command)+'\nend tell'
    subprocess.run(["/usr/bin/osascript", "-e", apple], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
    print("TerminalでAWSログインを開きました。3分以内にブラウザー認証を完了してください。", file=sys.stderr)
    deadline = time.monotonic()+WAIT_SECONDS
    while time.monotonic() < deadline:
        time.sleep(3)
        if check_auth(aws, profile, region):
            return
    raise RuntimeError("ログイン待機が終了しました。認証を完了してからMCPを再接続してください。")


@contextmanager
def login_lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        os.chmod(path, 0o600)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        deadline = time.monotonic()+WAIT_SECONDS
        while True:
            try:
                if os.name == "nt":
                    import msvcrt
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except (BlockingIOError, OSError):
                if time.monotonic() >= deadline:
                    raise RuntimeError("別のAWSログインを待機中です。認証後にMCPを再接続してください。")
                time.sleep(1)
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def ensure_auth(aws, profile, region, cache=None):
    cache = cache or Path.home()/".cache"/"aws-agent-skills-ja"
    name = hashlib.sha256(profile.encode()).hexdigest()[:24]+".lock"
    with login_lock(cache/name):
        if not check_auth(aws, profile, region):
            login(aws, profile, region)
            if not check_auth(aws, profile, region):
                raise RuntimeError("認証後のAWS接続確認に失敗しました。")


def main():
    parser = argparse.ArgumentParser(description="AWSログインを確認してAWS MCPを起動")
    parser.add_argument("--profile", required=True)
    parser.add_argument("--region", required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="認証確認のみ。ログインやMCP起動はしない")
    mode.add_argument("--login-only", action="store_true", help="端末で対話ログインのみを実行")
    args = parser.parse_args()
    validate(args.profile, args.region)
    aws = shutil.which("aws")
    if not aws:
        raise RuntimeError("AWS CLIがPATHにありません。AWS CLI v2.32以降を設定してください。")
    if args.check:
        if not check_auth(aws, args.profile, args.region):
            raise RuntimeError("AWSセッションが失効しています。--login-only で再認証してください。")
        print("AWS認証確認: 成功")
        return
    if args.login_only:
        login(aws, args.profile, args.region)
        if not check_auth(aws, args.profile, args.region):
            raise RuntimeError("認証後の接続確認に失敗しました。")
        return
    uvx = shutil.which("uvx")
    if not uvx:
        raise RuntimeError("uvxがPATHにありません。uvを設定してください。")
    ensure_auth(aws, args.profile, args.region)
    os.execvpe(uvx, [uvx, "mcp-proxy-for-aws-cli@latest", ENDPOINT],
               environment(args.profile, args.region))


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
    except Exception:
        # SDK・OS例外の全文には識別情報が含まれる場合がある。
        print("AWSログイン補助でエラーが発生しました。依存ツールと接続を確認してください。", file=sys.stderr)
        sys.exit(1)
