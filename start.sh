pkill solarcentral
sleep 1
cd /home/pi/SolarCentral
nohup python server.py > /dev/null 2>&1&
