@echo off
title MasterAI — Servidor
color 0A

echo.
echo  ================================================
echo   MasterAI Pro — Pipeline de Masterizacao
echo  ================================================
echo.
echo  Instalando dependencias...
pip install flask soundfile librosa scipy pyloudnorm mutagen numpy -q 2>nul

echo.
echo  Servidor iniciando em http://localhost:5000
echo  O navegador vai abrir automaticamente.
echo.
echo  Para ATUALIZAR o app.py: salve o arquivo e
echo  pressione CTRL+C aqui, depois ENTER para reiniciar.
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
