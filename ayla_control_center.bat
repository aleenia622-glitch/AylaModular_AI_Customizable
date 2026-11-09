@echo off
title Ayla Control Center ^& RAG Test Hub 🐾
cd /d "%~dp0"
cls
echo ===================================================
echo    AYLA CONTROL HUB ^& TESTE DE RAG HIBRIDO 🐾
echo ===================================================
echo.
echo   [1] Iniciar Hub Web (Painel Discord no Navegador)
echo   [2] Testar RAG Hibrido (CLI: Digitar mensagem e ver memorias)
echo   [3] Iniciar Ambos (Painel Web em 2o plano + CLI de Teste)
echo   [4] Sair
echo.
echo ===================================================
set /p choice="Escolha uma opcao [1-4] (Padrao: 2): "

if "%choice%"=="1" (
    python ayla_control_center.py --web
) else if "%choice%"=="3" (
    python ayla_control_center.py --both
) else if "%choice%"=="4" (
    exit /b
) else (
    python ayla_control_center.py --rag
)
pause

