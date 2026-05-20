"""
IP 차단 에러 팝업 — Tkinter messagebox 보다 풍부한 다이얼로그.
기능:
  - 현재 차단된 IP 표시
  - 이전에 등록되었던 IP 와 비교 표시 (.last_ip 파일에서)
  - "Wing IP 관리 페이지 열기" 버튼
  - "IP 자동 복사" 버튼
"""

from __future__ import annotations

import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import ttk

WING_IP_PAGE_URL = "https://wing.coupang.com/tenants/seller-web/info/openapi"
LAST_IP_FILE = Path(__file__).resolve().parent / ".last_ip"


def _read_last_ip() -> str | None:
    """이전에 성공적으로 사용했던 IP 읽기."""
    try:
        if LAST_IP_FILE.exists():
            return LAST_IP_FILE.read_text(encoding="utf-8").strip() or None
    except Exception:
        pass
    return None


def save_current_ip(ip: str) -> None:
    """API 호출 성공 시 현재 IP 저장 (다음 차단 시 비교용)."""
    try:
        LAST_IP_FILE.write_text(ip.strip(), encoding="utf-8")
    except Exception:
        pass


def show_ip_blocked_popup(blocked_ip: str, message: str = "") -> None:
    """
    IP 차단 안내 팝업을 띄움.

    Args:
        blocked_ip: 쿠팡 응답에서 추출한 차단된 IP 주소
        message: 추가 안내 메시지 (선택)
    """
    last_ip = _read_last_ip()
    is_changed = bool(last_ip) and last_ip != blocked_ip

    root = tk.Tk()
    root.title("쿠팡 API — IP 등록 필요")
    root.geometry("520x420")
    root.resizable(False, False)

    main = ttk.Frame(root, padding=20)
    main.pack(fill="both", expand=True)

    # 헤더
    header = ttk.Label(
        main,
        text="⚠️  접속 IP 주소 등록이 필요합니다",
        font=("Malgun Gothic", 14, "bold"),
        foreground="#c0392b",
    )
    header.pack(anchor="w", pady=(0, 10))

    # 본문
    body_text = (
        "현재 사용 중인 IP 가 쿠팡 Wing 에 등록되어 있지 않아 API 호출이 차단되었습니다.\n\n"
        "Wing > 내정보 > OPEN API 키 관리 페이지에서 아래 IP 를 추가해주세요."
    )
    body = ttk.Label(main, text=body_text, wraplength=470, justify="left")
    body.pack(anchor="w", pady=(0, 15))

    # IP 비교 영역
    ip_frame = ttk.LabelFrame(main, text="  IP 정보  ", padding=12)
    ip_frame.pack(fill="x", pady=(0, 15))

    if is_changed:
        ttk.Label(ip_frame, text="이전 IP:", foreground="gray").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Label(ip_frame, text=last_ip, foreground="gray", font=("Consolas", 10)).grid(
            row=0, column=1, sticky="w"
        )

        ttk.Label(ip_frame, text="    ↓ 변경됨", foreground="#e67e22").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(2, 2)
        )

    label_text = "현재 IP:" if is_changed else "현재 (등록 필요) IP:"
    ttk.Label(ip_frame, text=label_text, foreground="#c0392b", font=("Malgun Gothic", 10, "bold")).grid(
        row=2, column=0, sticky="w", padx=(0, 8), pady=(2, 0)
    )
    ip_value = ttk.Label(
        ip_frame,
        text=blocked_ip,
        foreground="#c0392b",
        font=("Consolas", 12, "bold"),
    )
    ip_value.grid(row=2, column=1, sticky="w", pady=(2, 0))

    if message:
        ttk.Label(main, text=message, foreground="gray", wraplength=470).pack(anchor="w", pady=(0, 10))

    # 상태 라벨 (복사 알림용)
    status = ttk.Label(main, text="", foreground="green")
    status.pack(anchor="w", pady=(0, 8))

    # 버튼 영역
    btn_frame = ttk.Frame(main)
    btn_frame.pack(fill="x", pady=(5, 0))

    def copy_ip():
        root.clipboard_clear()
        root.clipboard_append(blocked_ip)
        root.update()
        status.config(text=f"📋  IP '{blocked_ip}' 가 클립보드에 복사되었습니다!", foreground="green")

    def open_wing():
        webbrowser.open(WING_IP_PAGE_URL)
        status.config(text="🌐  Wing 페이지를 열었습니다. 로그인 후 IP 추가하세요.", foreground="blue")

    def close():
        root.destroy()

    copy_btn = ttk.Button(btn_frame, text="📋  IP 복사", command=copy_ip, width=14)
    copy_btn.pack(side="left", padx=(0, 8))

    wing_btn = ttk.Button(btn_frame, text="🌐  Wing 이동", command=open_wing, width=14)
    wing_btn.pack(side="left", padx=(0, 8))

    close_btn = ttk.Button(btn_frame, text="닫기", command=close, width=10)
    close_btn.pack(side="right")

    root.bind("<Escape>", lambda e: close())
    root.bind("<Control-c>", lambda e: copy_ip())

    # 가능한 한 항상 위로
    root.attributes("-topmost", True)
    root.after(200, lambda: root.attributes("-topmost", False))

    root.mainloop()


if __name__ == "__main__":
    # 단독 실행 시 데모
    import sys
    test_ip = sys.argv[1] if len(sys.argv) > 1 else "203.0.113.42"
    show_ip_blocked_popup(test_ip)
