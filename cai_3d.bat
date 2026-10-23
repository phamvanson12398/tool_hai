@echo off
REM Cai phan ve boi canh 3D cho Truyen ke (Stable Diffusion XL tren may) - khong bat buoc
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo   ============================================
echo    CAI PHAN VE BOI CANH 3D (Stable Diffusion)
echo   ============================================
echo   Can card NVIDIA 8GB tro len (GTX 1080 11GB chay duoc).
echo   Tai khoang 7 GB, chi can lam MOT lan.
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo   [LOI] Khong tim thay Python. Chay cai_dat.bat truoc.
    pause
    exit /b 1
)

echo   [1/3] Kiem tra PyTorch + card NVIDIA...
python -c "import torch; assert torch.cuda.is_available(); print('        ', torch.cuda.get_device_name(0))"
if errorlevel 1 (
    echo   [LOI] Chua co PyTorch ban CUDA hoac khong thay card NVIDIA. Chay cai_dat.bat truoc.
    pause
    exit /b 1
)
echo.

echo   [2/3] Cai thu vien ve anh (diffusers)...
REM Khong dong vao transformers (OmniVoice dang dung); diffusers ban moi hop voi transformers moi
python -c "import transformers" 2>nul
if errorlevel 1 pip install transformers
pip install -U "diffusers>=0.35.2" "accelerate>=1.2" "peft>=0.17"
if errorlevel 1 (
    echo   [LOI] Cai thu vien that bai. Chi xem thong bao loi o tren.
    pause
    exit /b 1
)
echo.

echo   [3/3] Tai mo hinh SDXL + SDXL-Lightning (khoang 7 GB, cho mot luc)...
python -c "import sys; sys.path.insert(0,'.'); from core import bg3d; bg3d.download(); print('        OK')"
if errorlevel 1 (
    echo.
    echo   [LOI] Chua tai / nap duoc mo hinh. Chup man hinh loi o tren gui lai nhe.
    echo         Mang yeu thi chay lai cai_3d.bat, phan da tai se khong tai lai.
    pause
    exit /b 1
)
echo.

echo   ============================================
echo    XONG. Mo tool, tab Truyen ke, o "Boi canh" chon "3D".
echo   ============================================
echo.
pause
