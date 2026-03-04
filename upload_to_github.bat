@echo off
REM 切换到你的项目目录
cd /d C:\Users\Administrator\Desktop\bs

REM 初始化 Git 仓库（如果已经初始化过，这条不会有问题）
git init

REM 配置全局用户名和邮箱（如果之前配置过就不会有影响）
git config --global user.name "wyf"
git config --global user.email "wyf@example.com"

REM 添加所有文件并提交（如果没有变化则不会创建新提交）
git add .
git commit -m "auto commit"

REM 重新设置远程地址（如果已存在就先删除）
git remote remove origin 2>nul
git remote add origin https://github.com/Wyf66669/bc.git

REM 推送到 GitHub，把当前分支推到远程的 main 分支
git push -u origin HEAD:main

pause

