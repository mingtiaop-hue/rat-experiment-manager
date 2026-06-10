@echo off
chcp 65001 >nul
title 动物实验管理系统 - ProView Lab
cd /d "%~dp0"

echo.
echo   ╔══════════════════════════════════╗
echo   ║  🐀 动物实验记录与数据管理系统   ║
echo   ║  糖尿病大鼠创面愈合实验          ║
echo   ╚══════════════════════════════════╝
echo.
echo   正在启动服务器...
echo   启动后浏览器会自动打开
echo   手机扫码也可访问（同一WiFi）
echo.
echo   按 Ctrl+C 可停止服务器
echo   ———————————————————————————————

streamlit run app.py --server.headless true

pause
