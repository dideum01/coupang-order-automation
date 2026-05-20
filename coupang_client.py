"""
Coupang Wing Open API 클라이언트
- HMAC-SHA256 인증
- 주문서(ordersheet) 조회
- 발주 확인 처리 (ACCEPT -> INSTRUCT)
- 송장번호 업로드 (출고지시)

공식 문서 기준:
  Base URL : https://api-gateway.coupang.com
  인증 헤더 : Authorization: CEA algorithm=HmacSHA256, access-key=..., signed-date=..., signature=...
"""

from __future__ import annotations

import hmac
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable
from urllib.parse import urlencode

import requests

log = logging.getLogger(__name__)

BASE_URL = "https://api-gateway.coupang.com"


# ---------------------------------------------------------------------------
# 주문 상태 코드 (Coupang 문서 기준)
# ---------------------------------------------------------------------------
# ACCEPT          : 결제완료 (발주확인 전)
# INSTRUCT        : 상품준비중 (발주확인 됨, 송장입력 전)
# DEPARTURE       : 배송지시
# DELIVERING      : 배송중
# FINAL_DELIVERY  : 배송완료
# NONE_TRACKING   : 업체 직접 배송(배송 정보 없음)


@dataclass
class CoupangCredentials:
    """API 인증 정보."""

    vendor_id: str
    access_key: str
    secret_key: str

    @classmethod
    def from_env(cls) -> "CoupangCredentials":
        import os

        vendor_id = os.environ.get("COUPANG_VENDOR_ID")
        access_key = os.environ.get("COUPANG_ACCESS_KEY")
        secret_key = os.environ.get("COUPANG_SECRET_KEY")
        missing = [
            k
            for k, v in {
                "COUPANG_VENDOR_ID": vendor_id,
                "COUPANG_ACCESS_KEY": access_key,
                "COUPANG_SECRET_KEY": secret_key,
            }.items()
            if not v
        ]
        if missing:
            raise RuntimeError(
                f"환경변수 누락: {', '.join(missing)} (.env 파일 또는 OS 환경변수에 설정)"
            )
        return cls(vendor_id=vendor_id, access_key=access_key, secret_key=secret_key)


# ---------------------------------------------------------------------------
# HMAC 서명
# ---------------------------------------------------------------------------
def _signed_datetime() -> str:
    """UTC 기준 YYMMDD'T'HHMMSS'Z' 포맷."""
    return datetime.now(timezone.utc).strftime("%y%m%dT%H%M%SZ")


def _build_authorization(
    method: str,
    path: str,
    query: str,
    access_key: str,
    secret_key: str,
) -> tuple[str, str]:
    """
    Coupang HMAC-SHA256 서명 생성.
    Returns (authorization_header_value, signed_date)
    """
    signed_date = _signed_datetime()
    message = f"{signed_date}{method}{path}{query}"
    signature = hmac.new(
        secret_key.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    authorization = (
        f"CEA algorithm=HmacSHA256, access-key={access_key}, "
        f"signed-date={signed_date}, signature={signature}"
    )
    return authorization, signed_date


# ---------------------------------------------------------------------------
# 클라이언트
# ---------------------------------------------------------------------------
class CoupangClient:
    """Coupang Wing Open API 호출 래퍼."""

    def __init__(self, creds: CoupangCredentials, timeout: int = 30) -> None:
        self.creds = creds
        self.timeout = timeout
        self.session = requests.Session()

    # ---- 저수준 요청 ----------------------------------------------------
    def _request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        body: dict | None = None,
    ) -> dict[str, Any]:
        params = params or {}
        # Coupang 서명용 query string은 키 순서 그대로 사용
        query = urlencode(params, doseq=True)
        full_url = f"{BASE_URL}{path}"
        if query:
            full_url = f"{full_url}?{query}"

        authorization, _ = _build_authorization(
            method=method,
            path=path,
            query=query,
            access_key=self.creds.access_key,
            secret_key=self.creds.secret_key,
        )

        headers = {
            "Authorization": authorization,
            "Content-Type": "application/json;charset=UTF-8",
            "X-EXTENDED-TIMEOUT": "90000",
        }

        log.debug("HTTP %s %s body=%s", method, full_url, body)
        resp = self.session.request(
            method=method,
            url=full_url,
            headers=headers,
            data=json.dumps(body) if body is not None else None,
            timeout=self.timeout,
        )

        try:
            payload = resp.json()
        except ValueError:
            payload = {"raw": resp.text}

        if not resp.ok:
            # 403 + IP 차단 메시지 → 전용 예외
            if resp.status_code == 403 and isinstance(payload, dict):
                msg = str(payload.get("message", ""))
                if "ip address" in msg.lower():
                    import re as _re
                    m = _re.search(r"\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b", msg)
                    blocked_ip = m.group(1) if m else "(알 수 없음)"
                    raise CoupangIPBlockedError(blocked_ip, payload, method, path)
            raise CoupangAPIError(
                status=resp.status_code,
                payload=payload,
                method=method,
                path=path,
            )
        # 성공 시 마지막으로 사용한 IP 기록 (다음 IP 차단 시 비교용)
        try:
            from ip_error_popup import save_current_ip
            import socket
            # 외부 IP 가져오기 어렵지만 응답 헤더에는 우리 IP 가 안 들어옴 → 생략
            # (현재는 IP 비교 기능은 차단 시점에 마지막 차단 IP 만 기록)
        except Exception:
            pass
        return payload

    # ---- 주문 조회 ------------------------------------------------------
    def list_ordersheets(
        self,
        created_at_from: str,
        created_at_to: str,
        status: str = "ACCEPT",
        max_per_page: int = 50,
        search_type: str = "timeFrame",
    ) -> list[dict[str, Any]]:
        """
        주문서 목록 조회. 페이징 자동 처리.

        Args:
            created_at_from / created_at_to:
                - search_type="timeFrame" 일 때 'YYYY-MM-DDTHH:MM:SS' (24시간 이내 범위)
                - search_type="dailyFrame" 일 때 'YYYY-MM-DD' (최대 31일)
            status: ACCEPT(결제완료) / INSTRUCT(상품준비중) 등
        """
        path = (
            f"/v2/providers/openapi/apis/api/v4/vendors/"
            f"{self.creds.vendor_id}/ordersheets"
        )

        results: list[dict[str, Any]] = []
        next_token: str | None = None

        while True:
            params = {
                "createdAtFrom": created_at_from,
                "createdAtTo": created_at_to,
                "status": status,
                "maxPerPage": str(max_per_page),
                "searchType": search_type,
            }
            if next_token:
                params["nextToken"] = next_token

            payload = self._request("GET", path, params=params)
            data = payload.get("data") or []
            results.extend(data)

            next_token = payload.get("nextToken")
            if not next_token:
                break

        log.info("조회된 주문서: %d건 (status=%s)", len(results), status)
        return results

    # ---- 발주 확인 ------------------------------------------------------
    def acknowledge_ordersheets(
        self, shipment_box_ids: Iterable[int | str]
    ) -> dict[str, Any]:
        """
        발주 확인 처리 (ACCEPT -> INSTRUCT).
        Args:
            shipment_box_ids: 묶음배송번호(shipmentBoxId) 리스트
        """
        ids = [int(x) for x in shipment_box_ids]
        if not ids:
            return {"code": "SKIP", "message": "처리할 주문 없음"}

        path = (
            f"/v2/providers/openapi/apis/api/v4/vendors/"
            f"{self.creds.vendor_id}/ordersheets/acknowledgement"
        )
        body = {"vendorId": self.creds.vendor_id, "shipmentBoxIds": ids}
        log.info("발주확인 요청: %d건", len(ids))
        return self._request("PUT", path, body=body)

    # ---- 송장번호 업로드 -------------------------------------------------
    def upload_invoices(self, invoices: list[dict[str, Any]]) -> dict[str, Any]:
        """
        송장번호 일괄 업로드 (출고지시).

        Args:
            invoices: 각 dict는 아래 키를 포함해야 함
              - shipmentBoxId (int)
              - orderId (int)
              - vendorItemId (int)
              - deliveryCompanyCode (str)  예: "CJGLS", "KGB", "EPOST" …
              - invoiceNumber (str)
              - splitShipping (bool, optional, default False)
              - preSplitShipped (bool, optional, default False)
              - estimatedShippingDate (str, optional, "YYYY-MM-DD")
        """
        if not invoices:
            return {"code": "SKIP", "message": "송장 데이터 없음"}

        path = (
            f"/v2/providers/openapi/apis/api/v4/vendors/"
            f"{self.creds.vendor_id}/orders/invoices"
        )
        body = {
            "vendorId": self.creds.vendor_id,
            "orderSheetInvoiceApplyDtos": invoices,
        }
        log.info("송장 업로드 요청: %d건", len(invoices))
        return self._request("POST", path, body=body)


# ---------------------------------------------------------------------------
# 예외
# ---------------------------------------------------------------------------
class CoupangAPIError(RuntimeError):
    def __init__(self, status: int, payload: Any, method: str, path: str) -> None:
        self.status = status
        self.payload = payload
        super().__init__(
            f"Coupang API {method} {path} 실패 (HTTP {status}): {payload}"
        )



class CoupangIPBlockedError(CoupangAPIError):
    """쿠팡 API 가 IP 화이트리스트에 없어서 차단했을 때 발생하는 전용 예외."""

    def __init__(self, blocked_ip: str, payload, method: str, path: str) -> None:
        self.blocked_ip = blocked_ip
        super().__init__(status=403, payload=payload, method=method, path=path)

