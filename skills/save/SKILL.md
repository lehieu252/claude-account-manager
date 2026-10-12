---
name: save
description: Lưu account Claude ĐANG đăng nhập vào danh sách (không cần đăng nhập lại).
argument-hint: "<tên-account>"
disable-model-invocation: true
allowed-tools: Bash(bash *)
---
!`bash "${CLAUDE_PLUGIN_ROOT}/scripts/acct.sh" save $ARGUMENTS 2>&1 || true`

Hiển thị NGUYÊN VĂN kết quả ở trên cho người dùng (giữ nguyên bảng markdown), không thêm nhận xét, không chạy thêm lệnh nào.
