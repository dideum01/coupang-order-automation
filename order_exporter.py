"""
주문 데이터 → CSV 내보내기.
쿠팡 Wing 수동 다운로드 발주서와 비슷한 컬럼 구성.
"""

from __future__ import annotations

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


# Wing 수동 다운로드 발주서 양식과 유사하게 컬럼 정의
CSV_HEADERS = [
    "묶음배송번호",
    "주문번호",
    "주문일자",
    "결제일자",
    "주문상태",
    "노출상품ID",
    "노출상품명",
    "옵션ID",
    "옵션명",
    "업체상품코드",
    "수량",
    "주문금액",
    "할인금액",
    "구매자명",
    "구매자연락처",
    "구매자이메일",
    "수취인명",
    "수취인연락처(안심번호)",
    "우편번호",
    "주소",
    "상세주소",
    "배송메시지",
    "분리배송여부",
    "묶음배송여부",
    "도서산간여부",
    "추가배송비",
    "택배사",
    "송장번호",
]


def _get(d: dict | None, *keys: str, default: Any = "") -> Any:
    """중첩 dict 안전 조회. _get(o, 'receiver', 'name')."""
    cur: Any = d or {}
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
        if cur is None:
            return default
    return cur if cur is not None else default


def _split_address(addr: str) -> tuple[str, str]:
    """주소를 기본주소/상세주소로 대충 분리. 쿠팡은 addr1/addr2 분리되어 옴."""
    return addr, ""


def _row_for_item(order: dict, item: dict) -> list[Any]:
    """주문 1개 + 옵션 1개 = CSV 한 행."""
    return [
        order.get("shipmentBoxId", ""),
        order.get("orderId", ""),
        order.get("orderedAt", ""),
        order.get("paidAt", ""),
        order.get("status", ""),
        item.get("sellerProductId", ""),
        item.get("sellerProductName", ""),
        item.get("vendorItemId", ""),
        item.get("vendorItemName", ""),
        item.get("externalVendorSkuCode", ""),
        item.get("shippingCount", ""),
        item.get("orderPrice", ""),
        item.get("discountPrice", ""),
        _get(order, "orderer", "name"),
        _get(order, "orderer", "safeNumber") or _get(order, "orderer", "ordererNumber"),
        _get(order, "orderer", "email"),
        _get(order, "receiver", "name"),
        _get(order, "receiver", "safeNumber") or _get(order, "receiver", "receiverNumber"),
        _get(order, "receiver", "postCode"),
        _get(order, "receiver", "addr1"),
        _get(order, "receiver", "addr2"),
        order.get("parcelPrintMessage", ""),
        "Y" if order.get("splitShipping") else "N",
        "Y" if order.get("combinedShipping") else "N",
        "Y" if order.get("remoteArea") else "N",
        order.get("remotePrice", ""),
        order.get("deliveryCompanyName", ""),
        order.get("invoiceNumber", ""),
    ]


def save_orders_csv(
    orders: list[dict[str, Any]],
    output_dir: str | Path = "./orders",
    filename: str | None = None,
    label: str = "발주확인",
) -> Path:
    """
    주문 리스트를 CSV 파일로 저장.

    Args:
        orders: Coupang API 응답의 'data' 리스트 (주문서 dict 리스트)
        output_dir: 저장 폴더 (없으면 자동 생성)
        filename: 직접 파일명 지정. None 이면 'YYYYMMDD_HHMMSS_{label}.csv'
        label: 자동 생성 파일명에 들어갈 접미사

    Returns:
        저장된 파일 경로

    Notes:
        - UTF-8-SIG (BOM 포함) 으로 저장하여 한글 Windows Excel 에서 깨짐 방지
        - 한 주문에 옵션이 여러 개면 행이 여러 개로 펼쳐짐 (수동 발주서와 동일 방식)
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{label}.csv"

    csv_path = out_dir / filename

    rows: list[list[Any]] = []
    for order in orders:
        items = order.get("orderItems") or []
        if not items:
            # 옵션 정보 없으면 헤더 정보만 한 줄
            rows.append(_row_for_item(order, {}))
        else:
            for item in items:
                rows.append(_row_for_item(order, item))

    # 한글 Excel 호환을 위해 utf-8-sig 사용
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADERS)
        writer.writerows(rows)

    log.info(
        "📄 CSV 저장 완료: %s (주문 %d건, 행 %d개)",
        csv_path,
        len(orders),
        len(rows),
    )
    return csv_path
