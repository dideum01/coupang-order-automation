# 쿠팡 Wing 발주확인 + 구글시트 자동화

쿠팡 Wing Open API로 **신규 주문 조회 → 발주 확인 → CSV 저장 → 구글시트 업로드** 를 한 번에 처리하는 파이썬 도구.

## 설치

```powershell
pip install -r requirements.txt
```

## 환경 설정 (.env)

```env
COUPANG_VENDOR_ID=...
COUPANG_ACCESS_KEY=...
COUPANG_SECRET_KEY=...
GSHEET_SPREADSHEET_ID=...
GSHEET_GID=958182324
GSHEET_KEY_PATH=service-account.json
```

서비스 계정 JSON 파일은 프로젝트 루트에 `service-account.json` 으로 저장.

## 사용

### 신규 주문 조회 (안전, 변경 없음)

```powershell
python main.py list --hours 24
```

### 발주확인 + CSV 저장

```powershell
python main.py acknowledge --source api --hours 24
```

CSV 는 `./orders/YYYYMMDD_HHMMSS_발주확인.csv` 로 저장됨.

### 발주확인 + CSV + 구글시트 업로드 ⭐

```powershell
python main.py acknowledge --source api --hours 24 --gsheet
```

자동으로:
1. 구글시트 현재 상태를 `./backups/` 폴더에 .xlsx 백업
2. Wing 발주서 컬럼 → 구글시트 컬럼 매핑 후 append
3. CSV 파일도 `./orders/` 에 저장
4. Coupang에 발주확인 API 호출

### 드라이런 (API 호출 없이 시뮬레이션)

```powershell
python main.py acknowledge --source api --hours 24 --gsheet --dry-run
```

### 송장번호 업로드

```powershell
python main.py invoice --file invoices.xlsx
```

## 구글시트 컬럼 매핑

| 구글시트 | ← | Wing 발주서 |
|---|---|---|
| 구매날짜 | ← | 주문일 (YY.MM.DD 변환) |
| 이름 | ← | 수취인이름 |
| 전화번호 | ← | 수취인전화번호 |
| 주소 | ← | 수취인 주소 |
| 배송메세지 | ← | 배송메세지 |
| 상품명 | ← | 상품명 / 옵션명 |
| 구매수량 | ← | 구매수(수량) |
| 판매가격 | ← | 결제액 |

나머지 컬럼 (상태, 매입가격, 수수료비율, 수수료, 판매마진, 마진율, 매입처, 결제) 은 비워둡니다.

## 안전 장치

- 구글시트 수정 전 자동 백업 (`./backups/` 폴더)
- `--dry-run` 으로 미리 시뮬레이션 가능
- `.env`, `service-account.json` 은 .gitignore 처리

## 파일 구조

```
발주확인처리/
├── main.py              # CLI 진입점
├── coupang_client.py    # Coupang Open API 클라이언트
├── excel_reader.py      # 엑셀/CSV 리더
├── order_exporter.py    # 발주서 CSV 저장
├── gsheet_uploader.py   # 구글시트 업로드 + 백업
├── requirements.txt
├── .env                 # API 키 (gitignore)
├── service-account.json # 구글 서비스 계정 (gitignore)
├── orders/              # CSV 저장 폴더
└── backups/             # 시트 백업 폴더
```
