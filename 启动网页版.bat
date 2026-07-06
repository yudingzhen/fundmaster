@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "D:\Finance\projects\fund-match"
echo.
echo    基金匹配器 - 网页版
echo    浏览器打开 http://localhost:8501
echo.
streamlit run app.py --server.port 8501
