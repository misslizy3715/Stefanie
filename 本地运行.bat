@echo off
chcp 65001 >nul
echo =============================================
echo   热点概念追踪 · 本地生成工具
echo =============================================
echo.
echo 请先从 WorkBuddy 获取 neodata token
echo 路径：C:\Users\李昱\.workbuddy\.neodata_token
echo.
set /p TOKEN="请粘贴 NEODATA_TEMP_TOKEN（直接回车跳过，使用缓存token）: "

if not "%TOKEN%"=="" (
    echo [保存Token]
    echo %TOKEN% > "%USERPROFILE%\.neodata_token"
)

echo.
echo [安装依赖]
pip install requests -q

echo.
echo [运行数据抓取]
python fetch_and_render.py

echo.
echo [完成] 请查看 index.html
pause
