@echo off
chcp 65001 >nul
echo ============================================
echo  选股意图解释器 · 一键启动 (Windows)
echo ============================================
cd /d "%~dp0"
echo [1/2] 检查依赖...
python -c "import flask" 2>nul || python -m pip install -r requirements.txt
echo [2/2] 启动服务: http://127.0.0.1:8000
echo 可选环境变量示例（写入此文件上方 set 即可）：
echo   set LLM_API_KEY=xxx
echo   set LLM_MODEL=xxx
echo   set FUYAO_API_KEY=xxx
python app.py
pause
