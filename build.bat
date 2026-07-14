@echo off
echo === Building Docker image ===
docker build -t gaze-tracker .
echo === Exporting to tar ===
docker save -o gaze-tracker.tar gaze-tracker
echo === Done! ===
echo Load on target: docker load -i gaze-tracker.tar
echo Run: docker run -d --network host -e DEMO_PORT=8081 -v rooms.json:/app/rooms.json gaze-tracker
pause
