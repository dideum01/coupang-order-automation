"""
Google Sheets 업로더.
- 서비스 계정 인증
- 시트 백업 (현재 상태를 로컬 .xlsx 로 다운로드)
- Wing 주문 데이터 → 구글시트 컬럼 매핑 → append

Wing API 응답 → 구글시트 컬럼 매핑:
  구매날짜      ← orderedAt (YY.MM.DD 변환)
  상태          ← (비움)
  이름          ← receiver.name
  전화번호      ← receiver.safeNumber
  주소          ← receiver.addr1 + " " + receiver.addr2
  배송메세지    ← parcelPrintMessage
  상품명        ← sellerProductName + " / " + vendorItemName
  구매수량      ← orderItems[].shippingCount
  판매가격      ← orderItems[].orderPrice
  매입가격..결제 ← (비움)
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import gspread
from google.oauth2.service_account import Credentials
from openpyxl import Workbook

log = logging.getLogger(__name__)


# 구글시트 컬럼 순서 (16개)
SHEET_COLUMNS = [
    "구매날짜",
    "상태",
    "이름",
    "전화번호",
    "주소",
    "배송메세지",
    "상품명",
    "구매수량",
    "판매가격",
    "매입가격",
    "수수료비율",
    "수수료",
    "판매마진",
    "마진율",
    "매입처",
    "결제",
]

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------
def _parse_date(s: Any) -> str:
    """Wing 의 ISO 8601 날짜 → YY.MM.DD."""
    if not s:
        return ""
    s = str(s).replace("T", " ").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s[: len(fmt) + 4 if "S" in fmt else len(fmt) - 6 if "%H" not in fmt else len(s)], fmt)
            return dt.strftime("%y.%m.%d")
        except ValueError:
            continue
    # 못 파싱하면 가능한 접두 10글자만 시도
    try:
        dt = datetime.strptime(s[:10], "%Y-%m-%d")
        return dt.strftime("%y.%m.%d")
    except ValueError:
        log.warning("날짜 파싱 실패, 원본 유지: %s", s)
        return s


def _safe_get(d: dict | None, *keys: str, default: str = "") -> str:
    cur: Any = d or {}
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
        if cur is None:
            return default
    return str(cur) if cur is not None else default


# ---------------------------------------------------------------------------
# 주문 → 행 변환
# ---------------------------------------------------------------------------
def order_to_rows(order: dict[str, Any]) -> list[list[Any]]:
    """
    주문 1개 → 구글시트 행 리스트 (옵션이 여러 개면 행 분할).
    각 행은 16개 컬럼 길이.
    """
    purchase_date = _parse_date(order.get("orderedAt"))
    name = _safe_get(order, "receiver", "name")
    phone = _safe_get(order, "receiver", "safeNumber") or _safe_get(
        order, "receiver", "receiverNumber"
    )
    addr1 = _safe_get(order, "receiver", "addr1")
    addr2 = _safe_get(order, "receiver", "addr2")
    address = (addr1 + " " + addr2).strip()
    delivery_msg = str(order.get("parcelPrintMessage") or "")

    items = order.get("orderItems") or [{}]
    rows: list[list[Any]] = []
    for item in items:
        product = str(item.get("sellerProductName") or item.get("vendorItemPackageName") or "")
        option = str(item.get("vendorItemName") or "")
        product_name = f"{product} / {option}" if (product and option) else (product or option)
        qty = item.get("shippingCount", "")
        price = item.get("orderPrice", "")

        # 16개 컬럼 — 채울 곳만 채우고 나머지는 빈 문자열
        row = [
            purchase_date,    # 구매날짜
            "",               # 상태
            name,             # 이름
            phone,            # 전화번호
            address,          # 주소
            delivery_msg,     # 배송메세지
            product_name,     # 상품명
            qty,              # 구매수량
            price,            # 판매가격
            "",               # 매입가격
            "",               # 수수료비율
            "",               # 수수료
            "",               # 판매마진
            "",               # 마진율
            "",               # 매입처
            "",               # 결제
        ]
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# 인증 / 시트 열기
# ---------------------------------------------------------------------------
def _authorize(key_path: str | Path) -> gspread.Client:
    key_path = str(key_path)
    if not os.path.exists(key_path):
        raise FileNotFoundError(
            f"서비스 계정 키 파일을 찾을 수 없습니다: {key_path}\n"
            f"Google Cloud Console 에서 JSON 키를 다운로드해 해당 위치에 두세요."
        )
    creds = Credentials.from_service_account_file(key_path, scopes=SCOPES)
    return gspread.authorize(creds)


def _get_worksheet(
    client: gspread.Client,
    spreadsheet_id: str,
    sheet_name: str | None = None,
    gid: int | str | None = None,
) -> gspread.Worksheet:
    """이름이나 gid 로 워크시트 가져오기."""
    spreadsheet = client.open_by_key(spreadsheet_id)
    if sheet_name:
        return spreadsheet.worksheet(sheet_name)
    if gid is not None:
        target_gid = int(gid)
        for ws in spreadsheet.worksheets():
            if ws.id == target_gid:
                return ws
        raise ValueError(
            f"gid={target_gid} 인 워크시트를 찾을 수 없습니다. "
            f"존재 시트: {[(w.title, w.id) for w in spreadsheet.worksheets()]}"
        )
    # 기본: 첫 번째 시트
    return spreadsheet.sheet1



def _normalize_tab_name(s: str) -> str:
    """탭 이름 비교용 정규화 — 보이지 않는 차이(공백·다양한 점·따옴표 등)를 흡수."""
    if not s:
        return ""
    s = str(s).strip()
    # 다양한 종류의 점(.) / 따옴표(') / 대시(-) 를 모두 ASCII 점(.) 으로 통일
    replacements = {
        "\u2024": ".", "\uff0e": ".", "\u3002": ".",   # ․ ． 。 → .
        "\u02bc": ".", "\u2019": ".", "\u2018": ".",  # ʼ ’ ‘  → .  (사용자 시트의 ' 같은 문자도 . 로 취급)
        "'": ".", "\u2032": ".",                       # ' ′ → .
        "\u30fb": ".", "\u00b7": ".",                # ・ · → .
    }
    for k, v in replacements.items():
        s = s.replace(k, v)
    return s


def _get_or_create_monthly_worksheet(
    spreadsheet,
    base_gid: int | str | None = None,
    base_name: str | None = None,
    *,
    dry_run: bool = False,
) -> "gspread.Worksheet":
    """
    현재 월(YY.MM)에 해당하는 탭을 찾거나, 없으면 기준 탭을 복제해서 새 탭 생성.
    dry_run=True 면 새 탭 생성·데이터 비우기 모두 건너뛰고 기준 탭을 그대로 반환 (안전 모드).
    """
    current_month = datetime.now().strftime("%y.%m")  # 예: "26.06"
    current_norm = _normalize_tab_name(current_month)

    # 디버그용: 시트의 모든 탭 정보 출력
    all_tabs = spreadsheet.worksheets()
    log.info("📋 시트 내 탭 목록 (%d개):", len(all_tabs))
    for ws in all_tabs:
        log.info("    - '%s' (gid=%d, repr=%r)", ws.title, ws.id, ws.title)

    # 1) 이미 존재하는 탭이면 그대로 사용 (정규화 비교)
    for ws in all_tabs:
        if _normalize_tab_name(ws.title) == current_norm:
            log.info("📌 현재 월 탭 매칭: '%s' (gid=%d) ← 입력 '%s'", ws.title, ws.id, current_month)
            return ws

    # 2) 없으면 기준 탭 찾기
    base_ws = None
    if base_gid not in (None, ""):
        try:
            target_gid = int(base_gid)
            for ws in all_tabs:
                if ws.id == target_gid:
                    base_ws = ws
                    break
        except (ValueError, TypeError):
            pass
    if base_ws is None and base_name:
        try:
            base_ws = spreadsheet.worksheet(base_name)
        except Exception:
            pass
    if base_ws is None:
        base_ws = spreadsheet.sheet1

    # 3) dry_run 이면 새 탭 만들지 않고 기준 탭 그대로 반환 (안전)
    if dry_run:
        log.warning(
            "⚠️  '%s' 탭 없음. [DRY-RUN] 이므로 새 탭 생성하지 않고 기준 탭 '%s' 를 임시 사용",
            current_month, base_ws.title,
        )
        log.warning(
            "    → 실제 실행 시 새 탭 '%s' 자동 생성 예정 (기준 탭 복제 + A3:I[마지막행] 비움)",
            current_month,
        )
        return base_ws

    # 4) 실제 실행: 새 탭 복제 + 데이터 비우기
    log.info("🆕 '%s' 탭이 없어서 '%s' 를 복제해 새로 생성", current_month, base_ws.title)
    new_ws = base_ws.duplicate(new_sheet_name=current_month)
    log.info("✅ 새 탭 생성 완료: '%s' (id=%d)", new_ws.title, new_ws.id)

    last_row = new_ws.row_count
    if last_row >= 3:
        range_to_clear = f"A3:I{last_row}"
        new_ws.batch_clear([range_to_clear])
        log.info(
            "🧹 새 탭 데이터 영역(A3:I%d) 비움 — 1~2행 헤더와 B열 드롭다운 서식 유지",
            last_row,
        )

    return new_ws


# ---------------------------------------------------------------------------
# 시트 백업
# ---------------------------------------------------------------------------
def backup_sheet(
    worksheet: gspread.Worksheet,
    backup_dir: str | Path = "./backups",
) -> Path:
    """현재 시트 전체 내용을 로컬 .xlsx 로 저장."""
    out_dir = Path(backup_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    data = worksheet.get_all_values()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_title = "".join(c if c.isalnum() else "_" for c in worksheet.title)[:30]
    backup_path = out_dir / f"{timestamp}_{safe_title}_backup.xlsx"

    wb = Workbook()
    ws = wb.active
    ws.title = safe_title or "Sheet1"
    for row in data:
        ws.append(row)

    # 모든 셀을 "텍스트" 포맷으로 강제 (Excel 이 전화번호의 선행 0 자동 제거 방지)
    for row_cells in ws.iter_rows():
        for cell in row_cells:
            cell.number_format = "@"

    wb.save(backup_path)

    log.info(
        "💾 시트 백업 완료: %s (%d행 x %d열)",
        backup_path,
        len(data),
        len(data[0]) if data else 0,
    )
    return backup_path


# ---------------------------------------------------------------------------
# 메인: 주문 데이터 업로드
# ---------------------------------------------------------------------------
def append_orders_to_sheet(
    orders: list[dict[str, Any]],
    spreadsheet_id: str,
    *,
    sheet_name: str | None = None,
    gid: int | str | None = None,
    key_path: str | Path = "service-account.json",
    backup: bool = True,
    backup_dir: str | Path = "./backups",
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    주문 리스트를 구글시트에 append.

    Returns:
        {'rows_added': int, 'backup_path': Path|None, 'sheet_title': str}
    """
    client = _authorize(key_path)
    spreadsheet = client.open_by_key(spreadsheet_id)
    # 월별 자동 탭 모드: 현재 월(YY.MM) 탭을 찾고, 없으면 기준 탭(gid/name)을 복제해 생성
    worksheet = _get_or_create_monthly_worksheet(
        spreadsheet, base_gid=gid, base_name=sheet_name, dry_run=dry_run
    )
    log.info("구글시트 연결 성공: '%s' (id=%d)", worksheet.title, worksheet.id)

    backup_path: Path | None = None
    if backup:
        backup_path = backup_sheet(worksheet, backup_dir)

    # 행 변환
    all_rows: list[list[Any]] = []
    for order in orders:
        all_rows.extend(order_to_rows(order))

    if not all_rows:
        return {
            "rows_added": 0,
            "backup_path": backup_path,
            "sheet_title": worksheet.title,
        }

    # 구매날짜(A열) 기준 다음 빈 행 찾기 — 우측 컬럼에 다른 데이터가 있어도 A열 기준으로 정확히 배치
    col_a = worksheet.col_values(1)
    while col_a and not col_a[-1]:
        col_a.pop()
    next_row = len(col_a) + 1
    last_row = next_row + len(all_rows) - 1
    log.info("📍 A열 기준 다음 빈 행: %d (기존 데이터 %d행)", next_row, len(col_a))

    # 채울 컬럼만 batch_update — 비워두는 컬럼(B, J~P)은 건드리지 않음 (기존 값/수식 유지)
    # all_rows 의 인덱스: A=0, B=1, C=2, D=3, E=4, F=5, G=6, H=7, I=8, J=9 ...
    col_a_values = [[r[0]] for r in all_rows]              # A열만
    col_c_to_i_values = [r[2:9] for r in all_rows]          # C~I열 (이름, 전화번호, 주소, 배송메세지, 상품명, 구매수량, 판매가격)

    batch_payload = [
        {"range": f"A{next_row}:A{last_row}", "values": col_a_values},
        {"range": f"C{next_row}:I{last_row}", "values": col_c_to_i_values},
    ]
    log.info("✏️  쓸 영역: A%d:A%d (구매날짜) + C%d:I%d (이름~판매가격)",
             next_row, last_row, next_row, last_row)
    log.info("   (B열 상태, J~P열 매입가격~결제 는 건드리지 않음)")

    if dry_run:
        log.info("[DRY-RUN] 시트 쓰기 건너뜀 (예정 %d행)", len(all_rows))
    else:
        worksheet.batch_update(batch_payload, value_input_option="USER_ENTERED")
        log.info("✅ 시트에 %d행 추가됨 (탭: %s)", len(all_rows), worksheet.title)

    return {
        "rows_added": len(all_rows),
        "backup_path": backup_path,
        "sheet_title": worksheet.title,
    }
