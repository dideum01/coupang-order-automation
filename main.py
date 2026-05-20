"""쿠팡 Wing 발주확인 / 송장업로드 / 구글시트 업로드 자동화 CLI.

사용 예시:
  python main.py list --hours 24
  python main.py acknowledge --source api --hours 24
  python main.py acknowledge --source api --hours 24 --gsheet
  python main.py acknowledge --source excel --file orders.xlsx
  python main.py invoice --file invoices.xlsx
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from coupang_client import CoupangAPIError, CoupangClient, CoupangCredentials, CoupangIPBlockedError
from excel_reader import read_invoices, read_shipment_box_ids
from order_exporter import save_orders_csv

try:
    from gsheet_uploader import append_orders_to_sheet
    _GSHEET_AVAILABLE = True
    _GSHEET_IMPORT_ERROR = ""
except ImportError as _e:
    _GSHEET_AVAILABLE = False
    _GSHEET_IMPORT_ERROR = str(_e)


log = logging.getLogger("발주확인")


def _time_range(hours):
    now = datetime.now()
    start = now - timedelta(hours=hours) + timedelta(minutes=1)
    fmt = "%Y-%m-%dT%H:%M"
    return start.strftime(fmt), now.strftime(fmt)


def _make_client():
    return CoupangClient(CoupangCredentials.from_env())


def _print_orders(orders):
    if not orders:
        print("  (조회된 주문 없음)")
        return
    print(f"{'shipmentBoxId':<15} {'orderId':<15} {'수령자':<10} {'상품명'}")
    print("-" * 80)
    for o in orders:
        items = o.get("orderItems") or []
        pname = items[0].get("vendorItemName", "") if items else ""
        print(
            f"{o.get('shipmentBoxId', ''):<15} "
            f"{o.get('orderId', ''):<15} "
            f"{(o.get('receiver') or {}).get('name', ''):<10} "
            f"{pname[:40]}"
        )


def cmd_list(args):
    client = _make_client()
    start, end = _time_range(args.hours)
    log.info("주문 조회: %s ~ %s (status=%s)", start, end, args.status)
    orders = client.list_ordersheets(start, end, status=args.status)
    print(f"\n📦 신규 주문 {len(orders)}건")
    _print_orders(orders)
    return 0


def _upload_to_gsheet(args, orders):
    if not _GSHEET_AVAILABLE:
        log.warning("구글시트 모듈 미설치: %s — pip install gspread google-auth", _GSHEET_IMPORT_ERROR)
        return
    try:
        ss_id = args.gsheet_id or os.environ.get("GSHEET_SPREADSHEET_ID")
        gid = args.gsheet_gid or os.environ.get("GSHEET_GID")
        sheet_name = args.gsheet_name or os.environ.get("GSHEET_SHEET_NAME")
        key_path = args.gsheet_key or os.environ.get("GSHEET_KEY_PATH", "service-account.json")
        if not ss_id:
            raise RuntimeError("Spreadsheet ID 필요. --gsheet-id 또는 .env 의 GSHEET_SPREADSHEET_ID")
        result = append_orders_to_sheet(
            orders, spreadsheet_id=ss_id, gid=gid, sheet_name=sheet_name,
            key_path=key_path, backup=not args.no_backup, dry_run=args.dry_run,
        )
        print(f"\n📊 구글시트: 탭 '{result['sheet_title']}' 에 {result['rows_added']}행 {'예정' if args.dry_run else '추가'}")
        if result.get("backup_path"):
            print(f"💾 백업: {result['backup_path']}")
    except Exception as exc:
        import traceback
        log.error("구글시트 업로드 실패: %s: %s", type(exc).__name__, exc)
        log.error("상세 트레이스백:\n%s", traceback.format_exc())


def cmd_acknowledge(args):
    orders = []
    if args.source == "api":
        client = _make_client()
        start, end = _time_range(args.hours)
        log.info("API 신규(ACCEPT) 조회: %s ~ %s", start, end)
        orders = client.list_ordersheets(start, end, status="ACCEPT")
        box_ids = sorted({int(o["shipmentBoxId"]) for o in orders if o.get("shipmentBoxId")})
    else:
        if not args.file:
            print("ERROR: --file <엑셀경로> 필요", file=sys.stderr)
            return 2
        box_ids = read_shipment_box_ids(args.file)
        client = _make_client() if not args.dry_run else None

    if not box_ids:
        print("✅ 처리할 신규 주문이 없습니다.")
        return 0

    print(f"\n📋 발주확인 대상 묶음배송번호 {len(box_ids)}건:")
    for bid in box_ids:
        print(f"  - {bid}")

    if args.source == "api" and not args.no_save_csv and orders:
        try:
            label = "발주확인_DRYRUN" if args.dry_run else "발주확인"
            csv_path = save_orders_csv(orders, output_dir=args.csv_dir, label=label)
            print(f"\n📄 발주서 CSV 저장: {csv_path}")
        except Exception as exc:
            log.warning("CSV 저장 실패: %s", exc)

    if args.source == "api" and args.gsheet and orders:
        _upload_to_gsheet(args, orders)

    if args.dry_run:
        print("\n[DRY-RUN] 실제 API 호출 없이 종료.")
        return 0

    try:
        result = client.acknowledge_ordersheets(box_ids)
        print(f"\n✅ 발주확인 완료: {result}")
        return 0
    except CoupangAPIError as exc:
        log.error("발주확인 실패: %s", exc)
        return 1


def cmd_invoice(args):
    if not args.file:
        print("ERROR: --file <엑셀경로> 필요", file=sys.stderr)
        return 2
    invoices = read_invoices(args.file)
    if not invoices:
        print("✅ 업로드할 송장 없음.")
        return 0
    print(f"\n📦 송장 업로드 대상 {len(invoices)}건")
    for inv in invoices[:10]:
        print(f"  - box={inv['shipmentBoxId']:>12} order={inv['orderId']:>12} 택배사={inv['deliveryCompanyCode']:<8} 송장={inv['invoiceNumber']}")
    if len(invoices) > 10:
        print(f"  ... 외 {len(invoices) - 10}건")
    if args.dry_run:
        print("\n[DRY-RUN] 종료.")
        return 0
    client = _make_client()
    try:
        result = client.upload_invoices(invoices)
        print(f"\n✅ 송장 업로드 완료: {result}")
        return 0
    except CoupangAPIError as exc:
        log.error("송장 업로드 실패: %s", exc)
        return 1




def cmd_settings(args):
    """설정 다이얼로그 열기."""
    try:
        from settings_gui import open_settings_dialog
    except ImportError as exc:
        print(f"GUI 모듈 로드 실패: {exc}", file=sys.stderr)
        return 1
    open_settings_dialog()
    return 0

def build_parser():
    p = argparse.ArgumentParser(prog="orders")
    p.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING"])
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("list")
    sp.add_argument("--hours", type=int, default=24)
    sp.add_argument("--status", default="ACCEPT",
                    choices=["ACCEPT", "INSTRUCT", "DEPARTURE", "DELIVERING", "FINAL_DELIVERY"])
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("acknowledge")
    sp.add_argument("--source", choices=["api", "excel"], default="api")
    sp.add_argument("--hours", type=int, default=24)
    sp.add_argument("--file")
    sp.add_argument("--dry-run", action="store_true")
    sp.add_argument("--csv-dir", default="./orders")
    sp.add_argument("--no-save-csv", action="store_true")
    sp.add_argument("--gsheet", action="store_true")
    sp.add_argument("--gsheet-id")
    sp.add_argument("--gsheet-gid")
    sp.add_argument("--gsheet-name")
    sp.add_argument("--gsheet-key")
    sp.add_argument("--no-backup", action="store_true")
    sp.set_defaults(func=cmd_acknowledge)

    sp = sub.add_parser("invoice")
    sp.add_argument("--file", required=True)
    sp.add_argument("--dry-run", action="store_true")
    sp.set_defaults(func=cmd_invoice)

    sp = sub.add_parser("settings", help="설정 다이얼로그 열기 (API 키 / 구글시트 설정)")
    sp.set_defaults(func=cmd_settings)

    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    try:
        return args.func(args)
    except CoupangIPBlockedError as exc:
        print(f"\n🚫 IP 차단됨: {exc.blocked_ip}", file=sys.stderr)
        try:
            from ip_error_popup import show_ip_blocked_popup, save_current_ip
            save_current_ip(exc.blocked_ip)  # 마지막 확인된 IP 저장 (다음 비교용)
            show_ip_blocked_popup(exc.blocked_ip)
        except Exception as gui_exc:
            print(f"(팝업 표시 실패: {gui_exc})", file=sys.stderr)
            print(f"수동 안내: Wing > 내정보 > OPEN API 키 관리 에서 IP '{exc.blocked_ip}' 추가하세요.", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"파일 없음: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"입력 오류: {exc}", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"실행 오류: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
