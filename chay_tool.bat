@echo off
REM Chay tool tao video hoat hinh hai thoai
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo   ============================================
echo    TOOL TAO VIDEO HOAT HINH HAI THOAI
echo   ============================================
echo.

REM Kiem tra Python
python --version >nul 2>&1
if errorlevel 1 (
    echo   [LOI] Khong tim thay Python.
    echo   Chi can cai Python 3.11 tu python.org, nho tick "Add to PATH".
    echo.
    pause
    exit /b 1
)

REM Kiem tra ffmpeg
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo   [LOI] Khong tim thay ffmpeg.
    echo   Chi tai ffmpeg tu https://www.gyan.dev/ffmpeg/builds/
    echo   roi them duong dan bin vao PATH.
    echo.
    pause
    exit /b 1
)

REM Kiem tra Claude CLI
call claude --version >nul 2>&1
if errorlevel 1 (
    echo   [CANH BAO] Khong tim thay Claude Code CLI.
    echo   Phan AI viet kich ban / ra soat se khong chay.
    echo   Cai bang: npm install -g @anthropic-ai/claude-code
    echo.
)

REM Kiem tra Gemini CLI (tuy chon, cho cac viec phu)
call gemini --version >nul 2>&1
if errorlevel 1 (
    echo   [GHI CHU] Chua cai Gemini CLI. Cac viec chon Gemini se tu dung Claude.
    echo   Cai bang: npm install -g @google/gemini-cli  roi chay "gemini" de dang nhap.
    echo.
)

echo   Dang chay server. Dong cua so nay la tat tool.
echo.
start "" cmd /c "timeout /t 3 >nul & start http://127.0.0.1:8766"
python web\server.py

pause
