@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "D:\Finance\projects\fund-match"
echo.
echo    基金匹配器 v1.0
echo    正在启动...
echo.
python main.py
