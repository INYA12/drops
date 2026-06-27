@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
chcp 65001 >nul
title DROPS LAN ^| File Sharing Server
mode con cols=72 lines=50
color 0F

:: -------------------------------------------------------
:: Check Python
:: -------------------------------------------------------
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo   [ERROR] Python not found!
    echo   Install Python 3 from https://python.org
    echo   and make sure it is added to PATH.
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%v in ('python --version 2^>^&1') do set PYVER=%%v

:: -------------------------------------------------------
:: Check admin rights + auto-elevate if needed
:: -------------------------------------------------------
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo    Requesting admin rights for firewall setup...
    echo.
    set "ELEVATE_VBS=%TEMP%\drops_elevate.vbs"
    (
        echo Set UAC = CreateObject^("Shell.Application"^)
        echo UAC.ShellExecute "%~f0", "", "%~dp0", "runas", 1
    ) >"!ELEVATE_VBS!"
    cscript //nologo "!ELEVATE_VBS!"
    del /f /q "!ELEVATE_VBS!" >nul 2>&1
    exit /b 0
)

:: If we reach here, we have admin rights. Re-set directory after elevation.
cd /d "%~dp0"

:: -------------------------------------------------------
:: Configure Windows Firewall (auto)
:: -------------------------------------------------------
set "FW_RULE_NAME=DROPS LAN Server"
set "FW_OK=0"
set "FW_STATUS=Unknown"

:: Check if firewall rule already exists
netsh advfirewall firewall show rule name="%FW_RULE_NAME% TCP-In" >nul 2>&1
if %errorlevel% equ 0 (
    set "FW_OK=1"
    set "FW_STATUS=Rules already configured"
) else (
    :: Add inbound TCP rule for ports 8888-8899
    netsh advfirewall firewall add rule name="%FW_RULE_NAME% TCP-In" dir=in action=allow protocol=TCP localport=8888-8899 profile=any enable=yes >nul 2>&1
    if !errorlevel! equ 0 set "FW_OK=1"

    :: Add inbound UDP rule
    netsh advfirewall firewall add rule name="%FW_RULE_NAME% UDP-In" dir=in action=allow protocol=UDP localport=8888-8899 profile=any enable=yes >nul 2>&1

    :: Also allow the Python executable itself
    for /f "tokens=*" %%p in ('where python 2^>nul') do (
        set "PYTHON_PATH=%%p"
    )
    if defined PYTHON_PATH (
        netsh advfirewall firewall add rule name="%FW_RULE_NAME% Python" dir=in action=allow program="!PYTHON_PATH!" profile=any enable=yes >nul 2>&1
    )

    if "!FW_OK!"=="1" (
        set "FW_STATUS=Rules created successfully"
    ) else (
        set "FW_STATUS=FAILED - manual setup needed"
    )
)

:: -------------------------------------------------------
:: Gather Network Info
:: -------------------------------------------------------
set "HOSTNAME_PC=%COMPUTERNAME%"
set "USERNAME_PC=%USERNAME%"

:: Get local IPs
set "IP_LIST="
set "IP_COUNT=0"
set "RADMIN_IP="
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /i "IPv4"') do (
    set "IP=%%a"
    set "IP=!IP: =!"
    if not "!IP!"=="" (
        set /a IP_COUNT+=1
        if defined IP_LIST (
            set "IP_LIST=!IP_LIST!, !IP!"
        ) else (
            set "IP_LIST=!IP!"
        )
        echo !IP! | findstr /b "26." >nul 2>&1
        if !errorlevel! equ 0 (
            set "RADMIN_IP=!IP!"
        )
    )
)

:: Get default gateway using PowerShell (more reliable)
set "GATEWAY="
for /f "tokens=*" %%g in ('powershell -NoProfile -Command "(Get-NetRoute -DestinationPrefix '0.0.0.0/0' | Sort-Object RouteMetric | Select-Object -First 1).NextHop" 2^>nul') do (
    set "GATEWAY=%%g"
)

:: Get MAC address of active adapter using PowerShell
set "MAC_ADDR="
for /f "tokens=*" %%m in ('powershell -NoProfile -Command "(Get-NetAdapter | Where-Object {$_.Status -eq 'Up'} | Select-Object -First 1).MacAddress" 2^>nul') do (
    set "MAC_ADDR=%%m"
)

:: Current date/time
for /f "tokens=*" %%d in ('powershell -NoProfile -Command "Get-Date -Format 'dd.MM.yyyy HH:mm:ss'"') do set "DATETIME=%%d"

:: -------------------------------------------------------
:: Print Banner
:: -------------------------------------------------------
cls
echo.
echo    +------------------------------------------------------+
echo    ^|                                                      ^|
echo    ^|       ######  ######   ####  ######   ####          ^|
echo    ^|       ##  ##  ##  ##  ##  ##  ##  ##  ##            ^|
echo    ^|       ##  ##  #####   ##  ##  #####    ####         ^|
echo    ^|       ##  ##  ##  ##  ##  ##  ##           ##       ^|
echo    ^|       ######  ##  ##   ####   ##       ####         ^|
echo    ^|                                                      ^|
echo    ^|           LAN  ~  File Sharing Server                ^|
echo    ^|                                                      ^|
echo    +------------------------------------------------------+
echo.
echo    +------------------------------------------------------+
echo    ^|  SYSTEM INFO                                         ^|
echo    +------------------------------------------------------+
echo    ^|  PC:       %HOSTNAME_PC%
echo    ^|  User:     %USERNAME_PC%
echo    ^|  Python:   %PYVER%
echo    ^|  Time:     %DATETIME%
echo    +------------------------------------------------------+
echo.
echo    +------------------------------------------------------+
echo    ^|  NETWORK INFO                                        ^|
echo    +------------------------------------------------------+

:: Print each IP
set "IP_IDX=0"
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /i "IPv4"') do (
    set "IP=%%a"
    set "IP=!IP: =!"
    if not "!IP!"=="" (
        set /a IP_IDX+=1
        echo    ^|  IPv4 #!IP_IDX!:  !IP!
    )
)

if defined GATEWAY (
    echo    ^|  Gateway:  %GATEWAY%
) else (
    echo    ^|  Gateway:  N/A
)
if defined MAC_ADDR (
    echo    ^|  MAC:      %MAC_ADDR%
)
echo    +------------------------------------------------------+

echo.
echo    +------------------------------------------------------+
echo    ^|  FIREWALL                                            ^|
echo    +------------------------------------------------------+
if "%FW_OK%"=="1" (
    echo    ^|  Status:   OK - Ports 8888-8899 open
    echo    ^|  Info:     %FW_STATUS%
) else (
    echo    ^|  Status:   WARNING - Could not configure
    echo    ^|  Fix:      Run start.bat as Administrator
)
echo    +------------------------------------------------------+

if defined RADMIN_IP (
    echo.
    echo    +------------------------------------------------------+
    echo    ^|  RADMIN VPN DETECTED                                 ^|
    echo    +------------------------------------------------------+
    echo    ^|  Radmin IP:  %RADMIN_IP%
    echo    ^|  Share:      http://%RADMIN_IP%:8888
    echo    +------------------------------------------------------+
)

echo.
echo    +------------------------------------------------------+
echo    ^|  STARTING SERVER...                                  ^|
echo    ^|                                                      ^|
echo    ^|  Port:     8888 (auto-fallback 8889-8899)            ^|
echo    ^|  Folder:   shared_files\                             ^|
echo    ^|  Ctrl+C    to stop the server                        ^|
echo    +------------------------------------------------------+
echo.
echo    ========================================================
echo.

:: -------------------------------------------------------
:: Launch Server
:: -------------------------------------------------------
python drops.py

echo.
echo    ========================================================
echo.
echo    Server stopped.
echo.

:: -------------------------------------------------------
:: Cleanup firewall rules on exit (optional - keep them)
:: Uncomment the lines below to remove rules when server stops:
:: netsh advfirewall firewall delete rule name="%FW_RULE_NAME% TCP-In" >nul 2>&1
:: netsh advfirewall firewall delete rule name="%FW_RULE_NAME% UDP-In" >nul 2>&1
:: netsh advfirewall firewall delete rule name="%FW_RULE_NAME% Python" >nul 2>&1
:: -------------------------------------------------------

pause
