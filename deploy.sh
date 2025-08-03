#!/bin/bash
cd /root/booking_room
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
deactivate
pkill gunicorn
nohup gunicorn app:app --bind 127.0.0.1:5000 &
echo "Deploy selesai!"
