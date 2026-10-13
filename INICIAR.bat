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
python -c "import demucs.pretrained, demucs.apply" 2>nul
if errorlevel 1 (
    echo.
    echo  Instalando o separador de stems Demucs - so na primeira vez.
    echo  Sao uns 300 MB de download, pode demorar alguns minutos...
    python -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu -q
    REM Demucs sem dependencias problematicas (lameenc); o app salva o audio com soundfile
    python -m pip install demucs==4.0.1 --no-deps -q
    python -m pip install dora-search einops julius openunmix pyyaml tqdm omegaconf -q
    python -c "import demucs.pretrained, demucs.apply" 2>nul
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
echo  O navegador abre sozinho quando o MasterAI estiver pronto.
echo  Se nao abrir, acesse http://localhost:5000
echo  Para fechar, feche esta janela.
echo.

:LOOP
python app.py
echo.
echo  Servidor encerrado. Pressione ENTER para reiniciar
echo  ou feche esta janela para sair.
pause > nul
echo  Reiniciando...
goto LOOP
