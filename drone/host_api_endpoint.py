"""
Gray Greenridge
ggree024@ucr.edu
GeNeLa
2026

This is where the drone hosts the API endpoint. Over HTTP, the datalogger sends soil data to the drone's AP.
"""

import os
import csv
import yaml
import gzip
from datetime import datetime
from flask import Flask, request, jsonify

app = Flask(__name__)

with open("conf.yaml", "r") as file:
    config = yaml.safe_load(file)

UPLOAD_FOLDER = config["api_endpoint_config"]["upload_folder_path"]
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route('/soil_kpi_handler', methods=['POST']) # type: ignore
def receive_file():
    # Check if the post request has the file part
    if 'file' not in request.files:
        return jsonify({"error": "No file part in the request"}), 400
        
    file = request.files['file']
    
    # If the user does not select a file, the browser/client submits an empty part
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    if file:
        # Secure the filename and save it to your destination folder
        file_path = os.path.join(UPLOAD_FOLDER, f"{file.filename}_{datetime.now().isoformat()}")
        file.save(file_path)
        
        print(f"Successfully saved: {file_path}, sanity checking...")

        with gzip.open(file_path, 'rt', encoding='utf-8') as f:
            reader = csv.reader(f)
            row_count = sum(1 for row in reader) - 1

        return jsonify({"row_count" : row_count}), 200

if __name__ == '__main__':
    # Runs the server locally on http://127.0.0.1:5000
    app.run(host='0.0.0.0', port=5000, debug=True)
