@echo off
echo Starting 学科知识整合智能体 开发服务器...
echo.

echo [1/2] Starting Backend (FastAPI) on port 8001...
start "Backend" cmd /k "python -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8001"

echo [2/2] Starting Frontend (Vite) on port 5173...
start "Frontend" cmd /k "cd frontend && npm run dev"

echo.
echo ========================================
echo 开发服务器已启动!
echo - 后端: http://localhost:8001
echo - 前端: http://localhost:5173
echo - API文档: http://localhost:8001/docs
echo ========================================
echo.
pause
