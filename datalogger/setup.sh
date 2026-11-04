python3 -m venv ./daf_datalogger_venv/
source ./daf_datalogger_venv/bin/activate
pip install -r requirements.txt
sudo mv datalogger.service /etc/systemd/system/datalogger.service
sudo chmod +x setup_ap.py
sudo mv setup_ap.py /usr/local/bin/setup_ap.py
sudo mv field-ap-init.service /etc/systemd/system/field-ap-init.service
sudo systemctl daemon-reload
sudo systemctl enable datalogger.service datalogger.service
sudo systemctl start datalogger.service datalogger.service
sudo systemctl enable field-ap-init.service
sudo systemctl start field-ap-init.service