@echo off
title Tour Video Generator
echo Dang khoi dong...
call venv\Scripts\activate
streamlit run app.py --server.headless true
pause