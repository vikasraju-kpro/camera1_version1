#!/bin/bash
# This script starts the camera application using gunicorn

# Navigate to the project directory
cd /home/venku/projects/camera1_version1

# Activate the virtual environment
source venv/bin/activate

# Start the Flask app with Gunicorn
exec gunicorn --workers 1 --threads 4 --bind 0.0.0.0:5000 app:app