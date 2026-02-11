@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ========================================
echo   CoinPilot AI - Windows 自動安裝程式
echo ========================================
echo.

:: 檢查 Python 是否存在
echo [1/8] 檢查 Python 環境...
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ 錯誤：找不到 Python！
    echo.
    echo 請先安裝 Python 3.10 或更新版本：
    echo https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

:: 檢查 Python 版本
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo ✅ 找到 Python %PYTHON_VERSION%

:: 解析版本號 (取主要版本和次要版本)
for /f "tokens=1,2 delims=." %%a in ("%PYTHON_VERSION%") do (
    set MAJOR=%%a
    set MINOR=%%b
)

:: 檢查版本是否 >= 3.10
if !MAJOR! LSS 3 (
    echo ❌ 錯誤：需要 Python 3.10 或更新版本，目前版本為 %PYTHON_VERSION%
    pause
    exit /b 1
)
if !MAJOR! EQU 3 if !MINOR! LSS 10 (
    echo ❌ 錯誤：需要 Python 3.10 或更新版本，目前版本為 %PYTHON_VERSION%
    pause
    exit /b 1
)

echo.

:: 檢查並建立虛擬環境
echo [2/8] 建立虛擬環境 (.venv)...
if exist ".venv\" (
    echo ⚠️  虛擬環境已存在，跳過建立步驟
) else (
    python -m venv .venv
    if errorlevel 1 (
        echo ❌ 錯誤：虛擬環境建立失敗
        pause
        exit /b 1
    )
    echo ✅ 虛擬環境建立成功
)
echo.

:: 啟動虛擬環境並升級 pip
echo [3/8] 升級 pip 到最新版本...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul 2>&1
echo ✅ pip 已升級
echo.

:: 安裝 Python 套件
echo [4/8] 安裝 Python 套件（包含開發工具）...
echo 這可能需要幾分鐘，請稍候...
pip install -e ".[dev]"
if errorlevel 1 (
    echo ❌ 錯誤：套件安裝失敗
    echo.
    echo 請檢查網路連線或手動執行：
    echo   .venv\Scripts\activate
    echo   pip install -e ".[dev]"
    pause
    exit /b 1
)
echo ✅ Python 套件安裝完成
echo.

:: 檢查 Hugo
echo [5/8] 檢查 Hugo Extended...
hugo version >nul 2>&1
if errorlevel 1 (
    echo ⚠️  未找到 Hugo，嘗試使用 Chocolatey 安裝...
    
    :: 檢查 Chocolatey 是否存在
    choco --version >nul 2>&1
    if errorlevel 1 (
        echo ❌ Chocolatey 未安裝，無法自動安裝 Hugo
        echo.
        echo 請手動安裝 Hugo Extended：
        echo.
        echo 方法 1 - 使用 Chocolatey（推薦）：
        echo   1. 以管理員身分開啟 PowerShell
        echo   2. 執行：Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
        echo   3. 執行：choco install hugo-extended -y
        echo.
        echo 方法 2 - 手動下載：
        echo   下載網址：https://github.com/gohugoio/hugo/releases
        echo   請下載 hugo_extended_xxx_windows-amd64.zip
        echo   解壓後將 hugo.exe 加入系統 PATH
        echo.
    ) else (
        echo 找到 Chocolatey，開始安裝 Hugo Extended...
        choco install hugo-extended -y
        if errorlevel 1 (
            echo ❌ Hugo 安裝失敗
            echo 請手動安裝：https://github.com/gohugoio/hugo/releases
        ) else (
            echo ✅ Hugo Extended 安裝成功
            :: 重新載入環境變數
            call refreshenv >nul 2>&1
        )
    )
) else (
    :: 檢查是否為 Extended 版本
    hugo version | findstr /i "extended" >nul 2>&1
    if errorlevel 1 (
        echo ⚠️  警告：找到 Hugo 但不是 Extended 版本
        echo Stack 主題需要 Hugo Extended 以編譯 SCSS
        echo 請安裝 Extended 版本：choco install hugo-extended -y
    ) else (
        for /f "tokens=*" %%i in ('hugo version') do set HUGO_VERSION=%%i
        echo ✅ 找到 !HUGO_VERSION!
    )
)
echo.

:: 檢查 Git
echo [6/8] 檢查 Git...
git --version >nul 2>&1
if errorlevel 1 (
    echo ⚠️  未找到 Git（GitHub 推送功能需要）
    echo 下載網址：https://git-scm.com/download/win
) else (
    for /f "tokens=*" %%i in ('git --version') do set GIT_VERSION=%%i
    echo ✅ 找到 !GIT_VERSION!
)
echo.

:: 建立必要目錄
echo [7/8] 建立資料目錄...
if not exist "data\" mkdir data
if not exist "site\static\images\" mkdir site\static\images
echo ✅ 目錄結構已就緒
echo.

:: 複製環境變數範本
echo [8/8] 設定環境變數...
if exist ".env" (
    echo ⚠️  .env 檔案已存在，跳過複製
) else (
    copy .env.example .env >nul
    echo ✅ 已複製 .env.example → .env
    echo.
    echo ⚠️  重要：請編輯 .env 檔案並填入您的 GITHUB_TOKEN
    echo    1. 開啟 .env 檔案
    echo    2. 將 GITHUB_TOKEN=your_github_token_here 改為您的實際 Token
    echo    3. Token 需要有 GitHub Copilot 訂閱權限
)
echo.

:: 執行系統狀態檢查
echo ========================================
echo   安裝完成！執行系統檢查...
echo ========================================
echo.
python main.py status
echo.

:: 顯示後續步驟
echo ========================================
echo   🎉 安裝完成！
echo ========================================
echo.
echo 📝 後續步驟：
echo.
echo 1. 編輯 .env 檔案，填入您的 GITHUB_TOKEN：
echo    notepad .env
echo.
echo 2. 啟動虛擬環境（每次使用時執行）：
echo    .venv\Scripts\activate
echo.
echo 3. 測試資料採集功能：
echo    python main.py collect
echo.
echo 4. 執行完整流程（使用 BAIA 智能代理）：
echo    python main.py baia
echo.
echo 5. 其他可用指令：
echo    python main.py status    - 查看系統狀態
echo    python main.py write     - AI 生成文章
echo    python main.py build     - 建置網站
echo    python main.py serve     - 啟動預覽伺服器
echo    python main.py web       - 開啟 Web 控制台
echo.
echo 📖 完整文件：請參閱 README.md
echo.
pause
