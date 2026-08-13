@echo off
REM ============================================================
REM UNI - start_llm.bat  (Hermes, 2026-08-13)
REM Запуск встроенного LLM (llama.cpp) на порту 1235.
REM Используется модель из downloads/ (по умолчанию Qwen3-8B-Q4_K_M.gguf).
REM CUDA-сборка: --n-gpu-layers 99 (GPU RTX 3060). Для CPU-режима убери флаг.
REM Старый путь LM Studio (1234) НЕ используется UNI (DEPRECATED).
REM ============================================================
setlocal
cd /d %~dp0\..
set "LLAMA=runtime\llama\llama-server.exe"
set "MODEL=downloads\Qwen3-8B-Q4_K_M.gguf"
set "PORT=1235"
set "API_KEY=uni-local"

if not exist "%LLAMA%" (
  echo [ERROR] %LLAMA% not found. Run P1 unpack first.
  exit /b 1
)
if not exist "%MODEL%" (
  echo [ERROR] %MODEL% not found. Put the .gguf into downloads/.
  exit /b 1
)

echo [UNI] Starting embedded LLM on http://127.0.0.1:%PORT%/v1 ...
"%LLAMA%" --model "%MODEL%" --host 127.0.0.1 --port %PORT% --n-gpu-layers 99 --api-key %API_KEY%
endlocal
