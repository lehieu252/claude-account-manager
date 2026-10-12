# claude-account-manager (`acct`)

Plugin Claude Code để quản lý nhiều account Claude (đăng nhập claude.ai): lưu account, xem usage 5 giờ / 7 ngày của tất cả account, và đổi account **không cần logout / login lại**. Dùng được trong CLI và extension VS Code, trên macOS, Windows và Linux.

| Lệnh | Việc làm |
|---|---|
| `/acct:login <tên>` | Lưu account **đang đăng nhập** vào danh sách với tên `<tên>` |
| `/acct:list [--refresh]` | Bảng các account đã lưu: email, tổ chức, gói, usage 5h / 7 ngày, giờ reset. `▶` = account đang dùng |
| `/acct:switch <tên>` | Đổi sang account `<tên>` |
| `/acct:logout <tên>` | Xoá account `<tên>` khỏi danh sách (xoá token đã lưu) |

## Cài đặt

Trong Claude Code (CLI hoặc ô chat của extension VS Code):

```
/plugin marketplace add <github-owner>/claude-account-manager
/plugin install acct@claude-account-manager
```

Cần Python 3.8+ (`python3`, `python` hoặc `py -3`). Trên Windows, Claude Code chạy lệnh qua Git Bash.

## Dùng lần đầu

Mỗi account làm **một lần**:

1. `/login` (lệnh có sẵn của Claude Code), đăng nhập account thứ nhất.
2. `/acct:login work`
3. `/login` lại, đăng nhập account thứ hai.
4. `/acct:login personal`

Từ đó trở đi chỉ cần `/acct:switch work` hoặc `/acct:switch personal`, rồi **mở tab / phiên Claude mới**. Tab đang mở vẫn giữ account cũ đến khi đóng.

## Cách hoạt động

- Claude Code giữ đăng nhập ở **Keychain** (macOS, mục `Claude Code-credentials`) hoặc file `~/.claude/.credentials.json` (Windows / Linux). Email / tổ chức của account nằm ở `~/.claude.json`, khoá `oauthAccount`.
- `login` sao chép token đang dùng vào kho riêng: Keychain mục `claude-acct` (macOS) hoặc `~/.claude-acct/secrets/<tên>.json`, quyền 600 (Windows / Linux). Danh sách + usage cache ở `~/.claude-acct/accounts.json` (không chứa token).
- `switch` lưu lại token **mới nhất** của account hiện tại (Claude Code tự làm mới token theo thời gian) rồi ghi token + `oauthAccount` của account đích vào chỗ Claude Code đọc.
- `switch` từ chối nếu account đang đăng nhập chưa được lưu, để không làm mất đăng nhập đó (`--force` để bỏ qua).
- Token **không bao giờ** được in ra hội thoại; lệnh chạy script trực tiếp (`disable-model-invocation`), Claude chỉ hiển thị kết quả.

## Giới hạn

- **Usage dùng API không chính thức** (`api.anthropic.com/api/oauth/usage`, cùng nguồn với `/usage`). Anthropic có thể đổi bất cứ lúc nào. Kết quả được cache 2 phút để tránh lỗi 429.
- Account không dùng lâu sẽ có token hết hạn. Khi đó `list` hiện **số cũ kèm giờ cập nhật**; script không tự làm mới token để tránh làm hỏng phiên đăng nhập. Switch sang account đó một lần là có số mới.
- `/acct:login` không tự đăng nhập hộ: bước đăng nhập claude.ai cần trình duyệt, nên vẫn dùng `/login` có sẵn.
- Không hỗ trợ đăng nhập bằng API key, Bedrock, Vertex.
- Nếu bạn đặt `CLAUDE_CONFIG_DIR` trên macOS, tên mục Keychain có hậu tố theo đường dẫn; script tính theo quan sát cộng đồng, chưa có tài liệu chính thức.
- Dùng nhiều account subscription phải tuân theo điều khoản của Anthropic.

## Dùng từ terminal

```bash
bash scripts/acct.sh list
bash scripts/acct.sh switch work
```

Biến môi trường: `CLAUDE_ACCT_HOME` (thư mục kho, mặc định `~/.claude-acct`).
