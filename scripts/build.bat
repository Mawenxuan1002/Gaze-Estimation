@echo off
setlocal
cd /d "%~dp0\.."
echo === Building Docker image ===
docker build -t gaze-tracker . || exit /b 1
echo === Exporting to tar ===
docker save -o gaze-tracker.tar gaze-tracker || exit /b 1
echo === Done ===
echo Load on target: docker load -i gaze-tracker.tar
echo Run: docker run -d --name gaze-tracker -p 8081:8081 -v "%%cd%%\config:/app/config" gaze-tracker
endlocal
