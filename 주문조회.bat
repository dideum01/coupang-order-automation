@echo off
chcp 949 > nul
cd /d "%~dp0"
echo === 신규 주문 조회 ===
python main.py list --hours 24
pause
