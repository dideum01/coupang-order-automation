@echo off
chcp 949 > nul
cd /d "%~dp0"
echo.
echo ==========================================
echo   PyInstaller Build Start
echo ==========================================
echo.
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] pip install failed
    pause
    exit /b 1
)
echo.
echo Building EXE via PyInstaller...
python -m PyInstaller --clean --noconfirm 발주확인.spec
if errorlevel 1 (
    echo [ERROR] PyInstaller build failed
    pause
    exit /b 1
)

echo.
echo ==========================================
echo   Build OK - Copying config files...
echo ==========================================
echo.

REM .env 자동 복사
if exist "%~dp0.env" (
    copy /Y "%~dp0.env" "%~dp0dist\발주확인\.env" > nul
    echo   [OK] .env copied
) else (
    echo   [SKIP] .env not found in project root
)

REM service-account.json 자동 복사
if exist "%~dp0service-account.json" (
    copy /Y "%~dp0service-account.json" "%~dp0dist\발주확인\service-account.json" > nul
    echo   [OK] service-account.json copied
) else (
    echo   [SKIP] service-account.json not found
)

REM 단축 .bat 5개 자동 생성 (영문 명령, 한글 메시지)
> "%~dp0dist\발주확인\주문조회.bat" (
    echo @echo off
    echo chcp 949 ^> nul
    echo cd /d "%%~dp0"
    echo echo === 신규 주문 조회 ===
    echo "%%~dp0발주확인.exe" list --hours 24
    echo pause
)
> "%~dp0dist\발주확인\발주확인_드라이런.bat" (
    echo @echo off
    echo chcp 949 ^> nul
    echo cd /d "%%~dp0"
    echo echo === 발주확인 + 구글시트 (드라이런) ===
    echo "%%~dp0발주확인.exe" acknowledge --source api --hours 24 --gsheet --dry-run
    echo pause
)
> "%~dp0dist\발주확인\발주확인_실행.bat" (
    echo @echo off
    echo chcp 949 ^> nul
    echo cd /d "%%~dp0"
    echo echo === 발주확인 + CSV + 구글시트 (실제 처리!) ===
    echo pause
    echo "%%~dp0발주확인.exe" acknowledge --source api --hours 24 --gsheet
    echo pause
)
> "%~dp0dist\발주확인\설정.bat" (
    echo @echo off
    echo chcp 949 ^> nul
    echo cd /d "%%~dp0"
    echo "%%~dp0발주확인.exe" settings
)
> "%~dp0dist\발주확인\송장업로드.bat" (
    echo @echo off
    echo chcp 949 ^> nul
    echo cd /d "%%~dp0"
    echo echo === 송장 업로드 ===
    echo set /p FILE="송장 엑셀 경로: "
    echo "%%~dp0발주확인.exe" invoice --file "%%FILE%%"
    echo pause
)
echo   [OK] Shortcut .bat files created (5 files)

echo.
echo ==========================================
echo   ALL DONE!
echo ==========================================
echo.
echo Output: dist\발주확인\
echo.
echo Ready to use:
echo   - dist\발주확인\발주확인.exe (main)
echo   - dist\발주확인\주문조회.bat
echo   - dist\발주확인\발주확인_실행.bat
echo   - dist\발주확인\설정.bat
echo   - etc.
echo.
pause
