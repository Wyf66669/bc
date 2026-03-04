@echo off
setlocal

REM === 配置区：如果你项目路径变了，只需要改下面这一行 ===
set "PROJECT_DIR=C:\Users\Administrator\Desktop\bs"
set "REMOTE_URL=https://github.com/Wyf66669/bc.git"

cd /d "%PROJECT_DIR%"

REM 初始化（已初始化也没关系）
git init

REM 把所有改动/新文件加入暂存区，并尝试提交
git add -A
git commit -m "auto commit" || echo (No changes to commit)

REM 推送到 GitHub（会提示输入账号/Token）
git remote remove origin 2>nul
git remote add origin "%REMOTE_URL%"
git push -u origin HEAD:main

echo.
echo Done. If you see errors above, copy them to troubleshoot.
pause

