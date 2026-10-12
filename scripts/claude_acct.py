#!/usr/bin/env python3
"""claude-acct — quản lý nhiều account Claude Code (claude.ai login) trên một máy.

Lệnh:
  save   <name>   Lưu account đang đăng nhập (sau khi /login) dưới tên <name>
  list            Liệt kê account đã lưu + usage 5h / 7 ngày
  switch <name>   Đổi sang account <name> (có hiệu lực ở phiên/tab Claude mới)
  remove <name>   Xoá account <name> khỏi danh sách (xoá token đã lưu)

Nơi Claude Code giữ đăng nhập (live):
  macOS         Keychain, service "Claude Code-credentials", account = $USER
  Windows/Linux <config_dir>/.credentials.json
  Danh tính     <home>/.claude.json, khoá "oauthAccount"

Nơi script giữ các account đã lưu ($CLAUDE_ACCT_HOME, mặc định ~/.claude-acct):
  accounts.json         danh sách + thông tin không bí mật + usage cache
  macOS                 token ở Keychain, service "claude-acct", account = <name>
  Windows/Linux         token ở secrets/<name>.json (quyền 600)

Chỉ dùng thư viện chuẩn của Python 3.8+.
"""

import argparse
import datetime as dt
import getpass
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

# CLAUDE_ACCT_BACKEND=file ép dùng file thay Keychain (để test luồng Windows/Linux trên macOS)
IS_MAC = sys.platform == "darwin" and os.environ.get("CLAUDE_ACCT_BACKEND") != "file"
LIVE_SERVICE = "Claude Code-credentials"
STORE_SERVICE = os.environ.get("CLAUDE_ACCT_KEYCHAIN_SERVICE", "claude-acct")
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"  # không chính thức
USAGE_CACHE_TTL = 120  # giây — tránh bị 429
EXPIRY_MARGIN_MS = 60_000


class AcctError(Exception):
    pass


# ---------------------------------------------------------------- paths

def config_dir():
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    return os.path.abspath(os.path.expanduser(env)) if env else os.path.expanduser("~/.claude")


def global_config_path():
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    if env:
        return os.path.join(config_dir(), ".claude.json")
    return os.path.expanduser("~/.claude.json")


def store_dir():
    return os.path.abspath(os.path.expanduser(os.environ.get("CLAUDE_ACCT_HOME", "~/.claude-acct")))


def index_path():
    return os.path.join(store_dir(), "accounts.json")


# ---------------------------------------------------------------- file helpers

def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def write_json_atomic(path, data, private=False):
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        if private and not sys.platform.startswith("win"):
            os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


# ---------------------------------------------------------------- macOS keychain

def _kc_find(service, account):
    r = subprocess.run(
        ["security", "find-generic-password", "-s", service, "-a", account, "-w"],
        capture_output=True, text=True,
    )
    return r.stdout.rstrip("\n") if r.returncode == 0 else None


def _kc_write(service, account, secret):
    # Ghi qua `security -i` (stdin) + -X hex để token không xuất hiện trên argv / ps.
    hexdata = secret.encode("utf-8").hex()
    cmd = 'add-generic-password -U -s "%s" -a "%s" -X %s\n' % (service, account, hexdata)
    r = subprocess.run(["security", "-i"], input=cmd, capture_output=True, text=True)
    if r.returncode != 0 or "error" in (r.stderr or "").lower():
        raise AcctError("Ghi Keychain thất bại (%s/%s): %s" % (service, account, r.stderr.strip()))


def _kc_delete(service, account):
    subprocess.run(["security", "delete-generic-password", "-s", service, "-a", account],
                   capture_output=True, text=True)


def live_keychain_service():
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    if not env:
        return LIVE_SERVICE
    # Theo quan sát cộng đồng (anthropics/claude-code#20553): hậu tố = 8 ký tự hex sha256 của đường dẫn.
    return "%s-%s" % (LIVE_SERVICE, hashlib.sha256(config_dir().encode()).hexdigest()[:8])


# ---------------------------------------------------------------- live credentials

def live_creds_file():
    return os.path.join(config_dir(), ".credentials.json")


def read_live_creds():
    """Trả về (dict credentials, nơi lưu) của account Claude Code đang đăng nhập."""
    if IS_MAC:
        raw = _kc_find(live_keychain_service(), getpass.getuser())
        if raw:
            return json.loads(raw), "keychain"
    data = read_json(live_creds_file())
    if data:
        return data, "file"
    raise AcctError("Không thấy đăng nhập Claude Code nào. Hãy gõ /login trước.")


def write_live_creds(creds, where):
    if where == "keychain":
        _kc_write(live_keychain_service(), getpass.getuser(), json.dumps(creds))
    else:
        write_json_atomic(live_creds_file(), creds, private=True)


def read_live_profile():
    return (read_json(global_config_path(), {}) or {}).get("oauthAccount")


def write_live_profile(profile):
    path = global_config_path()
    data = read_json(path, {}) or {}
    data["oauthAccount"] = profile
    write_json_atomic(path, data)


# ---------------------------------------------------------------- stored accounts

def load_index():
    idx = read_json(index_path(), None) or {}
    idx.setdefault("accounts", {})
    return idx


def save_index(idx):
    write_json_atomic(index_path(), idx, private=True)


def read_stored_creds(name):
    if IS_MAC:
        raw = _kc_find(STORE_SERVICE, name)
        if raw is None:
            raise AcctError("Thiếu token đã lưu của '%s' trong Keychain." % name)
        return json.loads(raw)
    data = read_json(os.path.join(store_dir(), "secrets", name + ".json"))
    if data is None:
        raise AcctError("Thiếu token đã lưu của '%s'." % name)
    return data


def write_stored_creds(name, creds):
    if IS_MAC:
        _kc_write(STORE_SERVICE, name, json.dumps(creds))
    else:
        write_json_atomic(os.path.join(store_dir(), "secrets", name + ".json"), creds, private=True)


def delete_stored_creds(name):
    if IS_MAC:
        _kc_delete(STORE_SERVICE, name)
    else:
        try:
            os.unlink(os.path.join(store_dir(), "secrets", name + ".json"))
        except FileNotFoundError:
            pass


# ---------------------------------------------------------------- identity

def identity(profile):
    if not profile:
        return None
    return (profile.get("accountUuid"), profile.get("organizationUuid"))


def find_by_identity(idx, ident):
    if not ident or ident == (None, None):
        return None
    for name, meta in idx["accounts"].items():
        if identity(meta.get("profile")) == ident:
            return name
    return None


def current_name(idx):
    return find_by_identity(idx, identity(read_live_profile()))


def sync_current(idx):
    """Ghi token mới nhất của account đang dùng vào kho (Claude Code tự làm mới token theo thời gian)."""
    name = current_name(idx)
    if not name:
        return None
    creds, _ = read_live_creds()
    write_stored_creds(name, creds)
    meta = idx["accounts"][name]
    meta["profile"] = read_live_profile()
    meta["oauth"] = public_oauth(creds)
    return name


def public_oauth(creds):
    o = creds.get("claudeAiOauth", {})
    return {k: o.get(k) for k in ("expiresAt", "subscriptionType", "rateLimitTier")}


def valid_name(name):
    if not name or any(c in name for c in '/\\:"\' ') or name.startswith("."):
        raise AcctError("Tên account không hợp lệ: '%s' (không dùng khoảng trắng, / \\ : hoặc dấu nháy)." % name)


# ---------------------------------------------------------------- usage

def fetch_usage(access_token):
    req = urllib.request.Request(USAGE_URL, headers={
        "Authorization": "Bearer " + access_token,
        "anthropic-beta": "oauth-2025-04-20",
        "Content-Type": "application/json",
        "User-Agent": "claude-acct/0.1",
    })
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def refresh_usage(meta, creds, force=False):
    """Cập nhật meta['usage'] nếu token còn hạn. Trả về chuỗi trạng thái."""
    cache = meta.get("usage")
    now = time.time()
    if cache and not force and now - cache.get("fetchedAt", 0) < USAGE_CACHE_TTL:
        return "cache"
    o = creds.get("claudeAiOauth", {})
    if not o.get("accessToken") or (o.get("expiresAt") or 0) < now * 1000 + EXPIRY_MARGIN_MS:
        return "expired"
    try:
        data = fetch_usage(o["accessToken"])
    except urllib.error.HTTPError as e:
        return "http %d" % e.code
    except Exception as e:  # mạng lỗi, timeout...
        return "lỗi: %s" % type(e).__name__
    meta["usage"] = {"fetchedAt": now, "data": data}
    return "ok"


def fmt_window(w):
    if not isinstance(w, dict) or w.get("utilization") is None:
        return "—"
    s = "%d%%" % round(w["utilization"])
    reset = w.get("resets_at")
    if reset:
        try:
            if isinstance(reset, (int, float)):
                t = dt.datetime.fromtimestamp(reset / 1000 if reset > 1e11 else reset).astimezone()
            else:
                t = dt.datetime.fromisoformat(str(reset).replace("Z", "+00:00")).astimezone()
            s += " (reset %s)" % t.strftime("%d/%m %H:%M")
        except (ValueError, OverflowError, OSError):
            pass
    return s


def fmt_age(ts):
    mins = int((time.time() - ts) // 60)
    if mins < 1:
        return "vừa xong"
    if mins < 60:
        return "%d phút trước" % mins
    if mins < 60 * 24:
        return "%d giờ trước" % (mins // 60)
    return "%d ngày trước" % (mins // 1440)


# ---------------------------------------------------------------- commands

def cmd_save(args):
    valid_name(args.name)
    idx = load_index()
    profile = read_live_profile()
    creds, _ = read_live_creds()
    ident = identity(profile)
    existing = find_by_identity(idx, ident)
    if existing and existing != args.name:
        raise AcctError("Account đang đăng nhập (%s) đã được lưu với tên '%s'."
                        % ((profile or {}).get("emailAddress"), existing))
    if args.name in idx["accounts"] and identity(idx["accounts"][args.name].get("profile")) != ident:
        raise AcctError("Tên '%s' đang là của account khác (%s). Chọn tên khác hoặc /acct:logout %s trước."
                        % (args.name, idx["accounts"][args.name].get("profile", {}).get("emailAddress"), args.name))
    write_stored_creds(args.name, creds)
    idx["accounts"][args.name] = {
        "profile": profile,
        "oauth": public_oauth(creds),
        "savedAt": time.time(),
        "usage": idx["accounts"].get(args.name, {}).get("usage"),
    }
    save_index(idx)
    print("Đã lưu account **%s** — %s (%s)." % (
        args.name, (profile or {}).get("emailAddress", "?"), (profile or {}).get("organizationName", "?")))
    print("Để thêm account khác: gõ /login với account đó, rồi /acct:login <tên>.")


def cmd_list(args):
    idx = load_index()
    if not idx["accounts"]:
        print("Chưa lưu account nào. Đăng nhập bằng /login rồi gõ /acct:login <tên>.")
        return
    try:
        cur = sync_current(idx)
    except AcctError:
        cur = None
    live_profile = read_live_profile()
    rows = []
    for name in sorted(idx["accounts"]):
        meta = idx["accounts"][name]
        try:
            creds = read_stored_creds(name)
            status = refresh_usage(meta, creds, force=args.refresh)
        except AcctError as e:
            status = str(e)
        usage = (meta.get("usage") or {}).get("data") or {}
        fetched = (meta.get("usage") or {}).get("fetchedAt")
        if status in ("ok", "cache"):
            note = "cập nhật " + fmt_age(fetched)
        elif fetched:
            note = "số cũ, cập nhật %s (%s)" % (fmt_age(fetched), "token hết hạn" if status == "expired" else status)
        else:
            note = "chưa có số (%s)" % ("token hết hạn — switch sang để làm mới" if status == "expired" else status)
        p = meta.get("profile") or {}
        rows.append([
            ("▶ " if name == cur else "") + name,
            p.get("emailAddress", "?"),
            p.get("organizationName", "?"),
            (meta.get("oauth") or {}).get("subscriptionType") or "?",
            fmt_window(usage.get("five_hour")),
            fmt_window(usage.get("seven_day")),
            note,
        ])
    save_index(idx)
    head = ["Account", "Email", "Tổ chức", "Gói", "5 giờ", "7 ngày", "Ghi chú"]
    print("| " + " | ".join(head) + " |")
    print("|" + "---|" * len(head))
    for r in rows:
        print("| " + " | ".join(r) + " |")
    if not cur:
        print("\nĐang đăng nhập %s nhưng account này chưa được lưu — gõ /acct:login <tên> để lưu."
              % ((live_profile or {}).get("emailAddress") or "(không rõ)"))
    else:
        print("\n▶ = account đang dùng.")


def cmd_switch(args):
    idx = load_index()
    if args.name not in idx["accounts"]:
        raise AcctError("Không có account '%s'. Đã lưu: %s" % (args.name, ", ".join(sorted(idx["accounts"])) or "(trống)"))
    cur = current_name(idx)
    if cur == args.name:
        print("Đang dùng **%s** rồi." % args.name)
        return
    live_creds, where = read_live_creds()
    if cur is None and not args.force:
        raise AcctError("Account đang đăng nhập (%s) chưa được lưu — đổi đi sẽ mất đăng nhập này. "
                        "Gõ /acct:login <tên> để lưu trước, hoặc thêm --force để bỏ qua."
                        % ((read_live_profile() or {}).get("emailAddress") or "không rõ"))
    if cur:
        write_stored_creds(cur, live_creds)  # giữ token mới nhất của account cũ
        idx["accounts"][cur]["oauth"] = public_oauth(live_creds)
    target = read_stored_creds(args.name)
    write_live_creds(target, where)
    write_live_profile(idx["accounts"][args.name].get("profile"))
    save_index(idx)
    p = idx["accounts"][args.name].get("profile") or {}
    print("Đã chuyển sang **%s** — %s (%s)." % (args.name, p.get("emailAddress", "?"), p.get("organizationName", "?")))
    print("Mở tab/phiên Claude MỚI để dùng account này; tab đang mở vẫn giữ account cũ.")


def cmd_remove(args):
    idx = load_index()
    if args.name not in idx["accounts"]:
        raise AcctError("Không có account '%s'." % args.name)
    was_current = current_name(idx) == args.name
    delete_stored_creds(args.name)
    del idx["accounts"][args.name]
    save_index(idx)
    print("Đã xoá **%s** khỏi danh sách." % args.name)
    if was_current:
        print("Đây là account đang đăng nhập — Claude Code vẫn đăng nhập account này. "
              "Muốn đăng xuất hẳn thì gõ /logout, hoặc /acct:switch sang account khác.")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="claude-acct", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("save", help="lưu account đang đăng nhập"); p.add_argument("name", nargs="?"); p.set_defaults(fn=cmd_save)
    p = sub.add_parser("list", help="liệt kê + usage"); p.add_argument("--refresh", action="store_true"); p.set_defaults(fn=cmd_list)
    p = sub.add_parser("switch", help="đổi account"); p.add_argument("name", nargs="?"); p.add_argument("--force", action="store_true"); p.set_defaults(fn=cmd_switch)
    p = sub.add_parser("remove", help="xoá account khỏi danh sách"); p.add_argument("name", nargs="?"); p.set_defaults(fn=cmd_remove)
    args = ap.parse_args(argv)
    try:
        if hasattr(args, "name") and not args.name:
            hint = {"save": "/acct:login", "switch": "/acct:switch", "remove": "/acct:logout"}[args.cmd]
            raise AcctError("Thiếu tên account. Ví dụ: %s work" % hint)
        args.fn(args)
    except AcctError as e:
        print("Lỗi: %s" % e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
