@echo off
title MasterAI - Servidor
color 0A
cd /d "%~dp0"

echo.
echo  ================================================
echo   MasterAI Pro - roda so no seu computador
echo  ================================================
echo.
echo  Instalando/conferindo dependencias...
python -m pip install flask soundfile librosa scipy pyloudnorm mutagen numpy numba -q 2>nul

REM --- Separador de stems (Demucs): instala uma vez so ---
python -c "import demucs" 2>nul
if errorlevel 1 (
    echo.
    echo  Instalando o separador de stems Demucs - so na primeira vez.
    echo  Sao uns 300 MB de download, pode demorar alguns minutos...
    python -m pip install torch==2.5.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cpu -q
    if errorlevel 1 (
        echo  Versao 2.5.1 indisponivel para o seu Python, tentando a 2.8.0...
        REM 2.8.0 e a ultima em que o torchaudio ainda salva audio do jeito que o Demucs 4 usa
        python -m pip install torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cpu -q
    )
    python -m pip install demucs==4.0.1 -q
    python -c "import demucs" 2>nul
    if errorlevel 1 (
        echo  [aviso] O Demucs nao instalou. A masterizacao funciona normalmente,
        echo          so a aba "Separador de stems" fica indisponivel.
    ) else (
        echo  Demucs instalado.
    )
)

REM Uso local: nao usa o separador na nuvem
set STEMS_SPACE=

echo.
echo  Servidor iniciando em http://localhost:5000
echo  O navegador vai abrir automaticamente.
echo  Para fechar, feche esta janela.
echo.

:LOOP
start "" http://localhost:5000
python app.py --reload
echo.
echo  Servidor encerrado. Pressione ENTER para reiniciar
echo  ou feche esta janela para sair.
pause > nul
echo  Reiniciando...
goto LOOP
