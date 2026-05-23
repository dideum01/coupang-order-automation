@echo off
chcp 949 > nul
title 발주확인 - 의존성 설치

echo ============================================================
echo  발주확인 프로그램 - 필수 패키지 설치
echo ============================================================
echo.

REM Python 설치 확인
where python > nul 2>&1
if errorlevel 1 (
    echo [오류] Python 이 설치되어 있지 않습니다.
    echo.
    echo  https://www.python.org/downloads/  에서 Python 3.10 이상을 설치하세요.
    echo  설치 시 "Add Python to PATH" 옵션을 반드시 체크하세요.
    echo.
    pause
    exit /b 1
)

echo [확인] Python 버전:
python --version
echo.

REM pip 업그레이드
echo [1/2] pip 업그레이드 중...
python -m pip install --upgrade pip
if errorlevel 1 (
    echo [경고] pip 업그레이드 실패. 계속 진행합니다.
)
echo.

REM requirements.txt 설치
echo [2/2] 필수 패키지 설치 중 (requirements.txt)...
echo  - requests, pandas, openpyxl, python-dotenv, gspread, google-auth, pyinstaller
echo.
python -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo.
    echo [오류] 패키지 설치 실패.
    echo  인터넷 연결 또는 권한 문제일 수 있습니다.
    echo  관리자 권한 cmd 에서 다시 시도하거나, 회사망이면 프록시 설정을 확인하세요.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  설치 완료!
echo ============================================================
echo.
echo  이제 다음 .bat 파일들을 더블클릭해서 사용할 수 있습니다:
echo    - 주문조회.bat
echo    - 발주확인_드라이런.bat
echo    - 발주확인_실행.bat
echo    - 설정.bat
echo    - 송장업로드.bat
echo.
pause
