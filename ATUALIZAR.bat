@echo off
title MasterAI — Atualizador
color 0B

echo.
echo  ================================================
echo   MasterAI — Atualizador automatico
echo  ================================================
echo.

REM Verifica se o servidor esta rodando e mata
echo  Parando servidor anterior...
taskkill /f /im python.exe /fi "WINDOWTITLE eq MasterAI*" >nul 2>&1
timeout /t 1 /nobreak >nul

REM Copia o novo app.py se existir na pasta Downloads
if exist "%USERPROFILE%\Downloads\app.py" (
    echo  Novo app.py encontrado em Downloads!
    copy /y "%USERPROFILE%\Downloads\app.py" "%~dp0app.py" >nul
    echo  Copiado com sucesso.
    del "%USERPROFILE%\Downloads\app.py" >nul
) else (
    echo  Nenhum app.py novo encontrado em Downloads.
    echo  Coloque o novo app.py em: %USERPROFILE%\Downloads\
)

echo.
echo  Reiniciando servidor...
start "" "%~dp0INICIAR.bat"
exit
