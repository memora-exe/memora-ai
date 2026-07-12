@echo off
cd /d A:\SE\project\memora\memora-ai
start /B venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 3010 > uvicorn.out.log 2> uvicorn.err.log