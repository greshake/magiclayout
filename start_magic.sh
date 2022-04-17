#!/bin/bash

# Set pwd to the directory of this script
cd "$(dirname "$0")" || exit

# source venv if it exists
if [ -f venv/bin/activate ]; then
    source venv/bin/activate
fi

# Start the magic

# Restart if it dies
while true; do
    python src/magiclayout.py magic --db=~/.config/magiclayout.db
    sleep 1
done
