# 🖨️ Predictive Printer Maintenance System

![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![Flask](https://img.shields.io/badge/Flask-3.0-green)
![C++](https://img.shields.io/badge/C%2B%2B-Simulator-orange)
![License](https://img.shields.io/badge/License-MIT-lightgrey)

## 📌 Overview
This project is an intelligent system designed to monitor a fleet of printers and predict maintenance needs before failures occur. It utilizes a **Random Forest Classifier** to analyze telemetry data (drum wear, temperature, jams) and classify the device status.

The system consists of:
1.  **Backend API (Python/Flask):** Handles data ingestion, database management, and the dashboard.
2.  **ML Engine (Scikit-learn):** Retrains automatically in the background to improve prediction accuracy.
3.  **Fleet Simulator (C++):** A high-performance application simulating 500+ network printers generating real-time telemetry.

## 🚀 Features
- **Real-time Monitoring:** Live dashboard showing active printers and alerts.
- **Predictive Maintenance:** AI model detects potential failures based on component wear patterns.
- **Auto-Training:** The model updates itself automatically after every 500 new data points.
- **Dynamic Thresholds:** Adjust sensitivity (e.g., Fuser Temperature limits) directly from the UI.
- **Service Management:** Assign technicians to specific interventions.

## 🛠️ Tech Stack
- **Backend:** Python, Flask, SQLite
- **Machine Learning:** Scikit-learn, Pandas, Joblib
- **Simulation:** C++, libcurl, nlohmann/json
- **Frontend:** HTML/CSS (Jinja2 templates)

---

## ⚙️ Installation & Setup

### 1. Prerequisites
- Python 3.8 or higher
- C++ Compiler (GCC/Clang or MSVC)
- `libcurl` library (for the C++ simulator)

### 2. Python Environment (Backend)

Clone the repository and install dependencies:

```bash
# Install required Python libraries
pip install -r requirements.txt