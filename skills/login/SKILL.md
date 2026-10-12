---
name: login
description: Lưu account Claude đang đăng nhập vào danh sách (chạy sau /login).
argument-hint: "<tên-account>"
disable-model-invocation: true
allowed-tools: Bash(bash *)
---
!`bash "${CLAUDE_PLUGIN_ROOT}/scripts/acct.sh" save $ARGUMENTS 2>&1 || true`

Hiển thị NGUYÊN VĂN kết quả ở trên cho người dùng (giữ nguyên bảng markdown), không thêm nhận xét, không chạy thêm lệnh nào.
