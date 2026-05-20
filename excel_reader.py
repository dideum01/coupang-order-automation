"""
엑셀 파일에서 주문 정보 읽기.

지원 형식 2가지:
  1) 발주확인용 (shipment_box_id만 필요)
       - 컬럼: '묶음배송번호'  또는  'shipmentBoxId'
  2) 송장번호 업로드용
       - 컬럼: 묶음배송번호, 주문번호, 옵션ID, 택배사코드, 송장번호
              (shipmentBoxId, orderId, vendorItemId, deliveryCompanyCode, invoiceNumber)

엑셀 컬럼명은 한글/영문 둘 다 인식.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)


# 한글 → API 필드명 매핑
COLUMN_ALIASES: dict[str, str] = {
    # shipmentBoxId
    "묶음배송번호": "shipmentBoxId",
    "묶음배송id": "shipmentBoxId",
    "shipmentboxid": "shipmentBoxId",
    "shipment_box_id": "shipmentBoxId",
    # orderId
    "주문번호": "orderId",
    "orderid": "orderId",
    "order_id": "orderId",
    # vendorItemId
    "옵션id": "vendorItemId",
    "옵션아이디": "vendorItemId",
    "벤더아이템id": "vendorItemId",
    "vendoritemid": "vendorItemId",
    "vendor_item_id": "vendorItemId",
    # deliveryCompanyCode
    "택배사코드": "deliveryCompanyCode",
    "택배사": "deliveryCompanyCode",
    "deliverycompanycode": "deliveryCompanyCode",
    "delivery_company_code": "deliveryCompanyCode",
    # invoiceNumber
    "송장번호": "invoiceNumber",
    "운송장번호": "invoiceNumber",
    "invoicenumber": "invoiceNumber",
    "invoice_number": "invoiceNumber",
    # 보조 필드
    "분할배송여부": "splitShipping",
    "splitshipping": "splitShipping",
    "예상발송일": "estimatedShippingDate",
    "estimatedshippingdate": "estimatedShippingDate",
}


def _normalize(name: str) -> str:
    return str(name).strip().lower().replace(" ", "").replace("-", "")


def _rename_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename: dict[str, str] = {}
    for col in df.columns:
        key = _normalize(col)
        if key in COLUMN_ALIASES:
            rename[col] = COLUMN_ALIASES[key]
    return df.rename(columns=rename)


def _read_any(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls", ".xlsm"}:
        return pd.read_excel(path, dtype=str)
    if suffix == ".csv":
        # 한글 엑셀 CSV는 cp949 인 경우가 많음
        try:
            return pd.read_csv(path, dtype=str)
        except UnicodeDecodeError:
            return pd.read_csv(path, dtype=str, encoding="cp949")
    raise ValueError(f"지원하지 않는 파일 형식: {suffix}")


# ---------------------------------------------------------------------------
# 발주확인용
# ---------------------------------------------------------------------------
def read_shipment_box_ids(path: str | Path) -> list[int]:
    """엑셀에서 묶음배송번호(shipmentBoxId) 목록만 추출."""
    p = Path(path)
    df = _rename_columns(_read_any(p))
    if "shipmentBoxId" not in df.columns:
        raise ValueError(
            f"'{p.name}' 에 '묶음배송번호' 컬럼이 없습니다. "
            f"현재 컬럼: {list(df.columns)}"
        )
    ids = (
        df["shipmentBoxId"]
        .dropna()
        .astype(str)
        .str.strip()
        .loc[lambda s: s != ""]
        .unique()
        .tolist()
    )
    return [int(x) for x in ids]


# ---------------------------------------------------------------------------
# 송장 업로드용
# ---------------------------------------------------------------------------
REQUIRED_INVOICE_COLS = [
    "shipmentBoxId",
    "orderId",
    "vendorItemId",
    "deliveryCompanyCode",
    "invoiceNumber",
]


def read_invoices(path: str | Path) -> list[dict[str, Any]]:
    """엑셀에서 송장 업로드용 데이터 추출 (API body 형식의 dict 리스트)."""
    p = Path(path)
    df = _rename_columns(_read_any(p))

    missing = [c for c in REQUIRED_INVOICE_COLS if c not in df.columns]
    if missing:
        raise ValueError(
            f"'{p.name}' 송장 업로드에 필요한 컬럼 누락: {missing}\n"
            f"현재 컬럼: {list(df.columns)}"
        )

    invoices: list[dict[str, Any]] = []
    for idx, row in df.iterrows():
        try:
            entry: dict[str, Any] = {
                "shipmentBoxId": int(str(row["shipmentBoxId"]).strip()),
                "orderId": int(str(row["orderId"]).strip()),
                "vendorItemId": int(str(row["vendorItemId"]).strip()),
                "deliveryCompanyCode": str(row["deliveryCompanyCode"]).strip(),
                "invoiceNumber": str(row["invoiceNumber"]).strip(),
                "splitShipping": False,
                "preSplitShipped": False,
            }
        except (ValueError, TypeError) as exc:
            log.warning("행 %d 변환 실패, 건너뜀: %s", idx + 2, exc)
            continue

        # 선택 필드
        if "splitShipping" in df.columns and pd.notna(row.get("splitShipping")):
            entry["splitShipping"] = str(row["splitShipping"]).strip().lower() in {
                "true",
                "1",
                "y",
                "yes",
                "예",
            }
        if "estimatedShippingDate" in df.columns and pd.notna(
            row.get("estimatedShippingDate")
        ):
            entry["estimatedShippingDate"] = str(row["estimatedShippingDate"]).strip()

        invoices.append(entry)

    log.info("엑셀에서 송장 %d건 로드", len(invoices))
    return invoices
