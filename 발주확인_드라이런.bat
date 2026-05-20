@echo off
chcp 949 > nul
cd /d "%~dp0"
echo === 발주확인 + 구글시트 (드라이런 - 시뮬레이션) ===
python main.py acknowledge --source api --hours 24 --gsheet --dry-run
pause
