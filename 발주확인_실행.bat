@echo off
chcp 949 > nul
cd /d "%~dp0"
echo === 발주확인 + CSV + 구글시트 업로드 ===
python main.py acknowledge --source api --hours 24 --gsheet
pause
