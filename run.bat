@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist "config.json" (
    echo [!] Chua co file config.json. Dang khoi chay trinh thiet lap setup.py...
    python setup.py
)
python main.py
pause
