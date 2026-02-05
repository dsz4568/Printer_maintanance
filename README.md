# Printer_maintanance
The system was designed to monitor a fleet of printers (simulated by an external application in C++) and automatically detect service needs. It uses the Random Forest model to classify the condition of the device based on telemetry data (drum wear, fuser temperature, number of paper jams, etc.).


System Deployment Instructions (Deployment Guide)

To launch the full test environment, follow the steps below in the given order.

Step 1: Preparing the Python Environment

Make sure you have Python version 3.8 or newer installed.

Installing libraries: Open a terminal in the project folder and install the required dependencies:

pip install -r requirements.txt


Starting the Flask server: On first startup, the server will initialize the printer_system.db database and the folder structure for models.

python app.py


The server will be available at: http://localhost:5000
.

Step 2: Compiling and Running the C++ Simulator

The simulator requires the libcurl library to send data over HTTP and the json.hpp header.

Compilation (Linux / GCC):

g++ printer_simulator.cpp -o printer_simulator -lcurl


Compilation (Windows / Visual Studio):

Open the Printer_maintanance.sln file.

Make sure the curl library is linked in the project settings.

Build the project in Release mode.

Running the simulator: In a new terminal window, run the compiled file:

./printer_simulator      # Linux
printer_simulator.exe    # Windows


The simulator will start generating data for 500 printers and send it to the server in batches of 50.

Step 3: Monitoring and ML Training

Web interface: Open a browser and go to http://localhost:5000
. You should see incoming data displayed in the prediction table.

Automatic training: After receiving 500 telemetry records, the system will automatically start training a RandomForest model in the background.

Verification: Logs in the Flask server console will confirm successful model training and report its accuracy (Accuracy).
