@echo off
rem acq 信息查询工具（cmd）。用法见 docs\11-acq-query-tool.md
setlocal
set "ROOT=%~dp0.."
set "PYTHONPATH=%ROOT%\src\tools;%PYTHONPATH%"
set "PYTHONIOENCODING=utf-8"
python -X utf8 -m acq_query %*
