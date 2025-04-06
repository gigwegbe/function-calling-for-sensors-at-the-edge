TO run this, make sure the thingsboard docker container is running,
You can run "stream.py" to simulate sensor data
Run main file to set up alarm, "python alertSetter.py"

the above scripts, creates a temperature chain rule, a deafult root rule chain confired to receive message from a device, the message passed through chain rule to decide when to raise an alarm or not
