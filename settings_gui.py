"""
설정 다이얼로그 — Tkinter 윈도우.
쿠팡 API 키와 구글시트 설정을 GUI 에서 입력하고 .env 파일에 저장.
"""

from __future__ import annotations

import os
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

ENV_PATH = Path(__file__).resolve().parent / ".env"

# (env_key, label, default, is_secret)
FIELDS = [
    ("COUPANG_VENDOR_ID",     "쿠팡 Vendor ID",       "",                       False),
    ("COUPANG_ACCESS_KEY",    "쿠팡 Access Key",       "",                       False),
    ("COUPANG_SECRET_KEY",    "쿠팡 Secret Key",       "",                       True),
    ("GSHEET_SPREADSHEET_ID", "구글시트 Spreadsheet ID", "",                       False),
    ("GSHEET_GID",            "구글시트 탭 gid",         "",                       False),
    ("GSHEET_SHEET_NAME",     "구글시트 탭 이름(선택)",     "",                       False),
    ("GSHEET_KEY_PATH",       "서비스계정 JSON 경로",    "service-account.json",   False),
]


def _read_env() -> dict:
    """현재 .env 값을 dict 로 읽기 (없으면 빈 dict)."""
    values = {k: default for (k, _, default, _) in FIELDS}
    if not ENV_PATH.exists():
        return values
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip()
        if k in values:
            values[k] = v
    return values


def _write_env(values: dict) -> None:
    """입력값을 .env 에 저장. 기존 주석은 유지하면서 키들만 업데이트."""
    header = (
        "# 쿠팡 Wing Open API 인증 정보\n"
        "# ⚠️ 이 파일은 절대 외부로 유출되지 않도록 주의 (.gitignore 처리됨)\n"
        "\n"
    )
    lines = [header]
    lines.append(f"COUPANG_VENDOR_ID={values.get('COUPANG_VENDOR_ID', '').strip()}\n")
    lines.append(f"COUPANG_ACCESS_KEY={values.get('COUPANG_ACCESS_KEY', '').strip()}\n")
    lines.append(f"COUPANG_SECRET_KEY={values.get('COUPANG_SECRET_KEY', '').strip()}\n")
    lines.append("\n# 구글시트 설정\n")
    lines.append(f"GSHEET_SPREADSHEET_ID={values.get('GSHEET_SPREADSHEET_ID', '').strip()}\n")
    lines.append(f"GSHEET_GID={values.get('GSHEET_GID', '').strip()}\n")
    sheet_name = values.get('GSHEET_SHEET_NAME', '').strip()
    if sheet_name:
        lines.append(f"GSHEET_SHEET_NAME={sheet_name}\n")
    lines.append(f"GSHEET_KEY_PATH={values.get('GSHEET_KEY_PATH', 'service-account.json').strip()}\n")
    ENV_PATH.write_text("".join(lines), encoding="utf-8")


def open_settings_dialog():
    """설정 다이얼로그 열기."""
    current = _read_env()

    root = tk.Tk()
    root.title("쿠팡 발주확인처리 — 설정")
    root.geometry("620x440")
    root.resizable(False, False)

    main_frame = ttk.Frame(root, padding=20)
    main_frame.pack(fill="both", expand=True)

    title_label = ttk.Label(
        main_frame,
        text="⚙️  API 키 및 구글시트 설정",
        font=("Malgun Gothic", 14, "bold"),
    )
    title_label.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 15))

    entries = {}
    for i, (key, label, _default, is_secret) in enumerate(FIELDS, start=1):
        ttk.Label(main_frame, text=label + ":").grid(row=i, column=0, sticky="w", pady=4)
        show_char = "•" if is_secret else ""
        entry = ttk.Entry(main_frame, width=55, show=show_char)
        entry.insert(0, current.get(key, ""))
        entry.grid(row=i, column=1, sticky="ew", pady=4, padx=(10, 0))
        entries[key] = entry

    main_frame.columnconfigure(1, weight=1)

    # Secret Key 보기/숨기기 토글
    def toggle_secret():
        e = entries["COUPANG_SECRET_KEY"]
        e.config(show="" if e.cget("show") else "•")

    toggle_btn = ttk.Button(main_frame, text="🔒 Secret Key 보기/숨기기", command=toggle_secret)
    toggle_btn.grid(row=len(FIELDS) + 1, column=1, sticky="w", pady=(8, 0))

    status_label = ttk.Label(main_frame, text="", foreground="gray")
    status_label.grid(row=len(FIELDS) + 2, column=0, columnspan=2, sticky="w", pady=(15, 5))

    def on_save():
        new_values = {k: e.get() for k, e in entries.items()}
        # 필수 항목 검증
        required = ["COUPANG_VENDOR_ID", "COUPANG_ACCESS_KEY", "COUPANG_SECRET_KEY"]
        missing = [k for k in required if not new_values[k].strip()]
        if missing:
            messagebox.showerror(
                "필수 항목 누락",
                "다음 필드는 반드시 입력해야 합니다:\n\n" + "\n".join(f"• {k}" for k in missing),
                parent=root,
            )
            return
        try:
            _write_env(new_values)
            status_label.config(text=f"✅ 저장됨: {ENV_PATH}", foreground="green")
            messagebox.showinfo(
                "저장 완료",
                f".env 파일이 업데이트되었습니다.\n\n위치:\n{ENV_PATH}",
                parent=root,
            )
        except Exception as exc:
            messagebox.showerror("저장 실패", f"파일 저장 중 오류 발생:\n\n{exc}", parent=root)

    def on_cancel():
        root.destroy()

    btn_frame = ttk.Frame(main_frame)
    btn_frame.grid(row=len(FIELDS) + 3, column=0, columnspan=2, sticky="e", pady=(15, 0))

    save_btn = ttk.Button(btn_frame, text="💾  저장", command=on_save, width=12)
    save_btn.pack(side="right", padx=(8, 0))

    close_btn = ttk.Button(btn_frame, text="닫기", command=on_cancel, width=12)
    close_btn.pack(side="right")

    # ESC 로 닫기, Ctrl+S 로 저장
    root.bind("<Escape>", lambda e: on_cancel())
    root.bind("<Control-s>", lambda e: on_save())

    root.mainloop()


if __name__ == "__main__":
    open_settings_dialog()
