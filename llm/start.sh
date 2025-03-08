#!/bin/bash
python3 app.py &
chainlit run sensor_chat.py --watch
