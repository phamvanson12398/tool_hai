@echo off
REM Cai dat lan dau cho tool tao video hoat hinh hai thoai
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo   ============================================
echo    CAI DAT TOOL HOAT HINH HAI THOAI
echo   ============================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo   [LOI] Khong tim thay Python.
    echo   Chi cai Python 3.11 tu python.org, nho tick "Add Python to PATH".
    echo.
    pause
    exit /b 1
)

echo   [1/5] Kiem tra card NVIDIA...
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>nul
if errorlevel 1 (
    echo         Khong thay card NVIDIA. Phan tao giong se rat cham hoac khong chay.
) else (
    echo         OK
)
echo.

echo   [2/5] Cai PyTorch ban CUDA 12.6 (vai GB, cho mot luc)...
python -c "import torch; print('da co torch', torch.__version__)" 2>nul
if errorlevel 1 (
    pip install torch==2.6.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cu126
) else (
    echo         Da co san, bo qua.
)
echo.

echo   [3/5] Cai cac thu vien con lai...
pip install -r requirements.txt
if errorlevel 1 (
    echo   [LOI] Cai thu vien that bai. Chi xem thong bao loi o tren.
    pause
    exit /b 1
)
echo.

echo   [4/5] Tao tieng dong mac dinh...
python core\make_sfx.py
echo.

echo   [5/5] Tai mo hinh giong noi (OmniVoice + Whisper, vai GB)...
python -c "import sys; sys.path.insert(0,'.'); from core import voice; voice._model(); print('     OmniVoice OK')"
if errorlevel 1 (
    echo         Tai mo hinh chua xong. Lan dau chay tool se tu tai tiep.
)
echo.

echo   ============================================
echo    XONG. Bam dup vao chay_tool.bat de mo tool.
echo   ============================================
echo.
echo   Luu y: phan AI viet kich ban can Claude Code CLI:
echo     npm install -g @anthropic-ai/claude-code
echo     claude    (dang nhap mot lan)
echo.
pause
