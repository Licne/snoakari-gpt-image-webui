@echo off
chcp 65001 >nul
cd /d %~dp0
title gpt-image WebUI
python app.py
echo.
echo 服务已停止。如果上方有报错信息，请检查配置或控制台输出。
pause
