PYCHARM SETUP

1. Open PyCharm.
2. Choose File -> Open.
3. Select the "epicondylitis_ui" folder.
4. Open the PyCharm terminal.
5. Run:

   pip install -r requirements.txt

6. Confirm:
   Arduino Uno = COM16
   ESP32 = COM9

   If your ports change, edit these two lines in app.py:
   ARDUINO_PORT = "COM16"
   ESP32_PORT = "COM9"

7. Upload the Arduino EMG sketch and ESP32 MPU sketch first.
8. CLOSE Arduino Serial Monitor / Serial Plotter.
9. Keep both boards plugged into USB.
10. In PyCharm, run app.py.
11. Open:

    http://127.0.0.1:5000

IMPORTANT:
Only one program can normally use each COM port at a time.
Do not leave Arduino Serial Monitor open while running app.py.