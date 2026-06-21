#!/bin/bash
set -e

INSTALL_DIR="/opt/aprs-ai-panel"
SERVICE_FILE="/etc/systemd/system/aprs-ai-panel.service"

echo "=== APRS AI Gateway Installer ==="

# Copy files
echo "[1/4] Installing to $INSTALL_DIR..."
sudo mkdir -p "$INSTALL_DIR"
sudo cp app.py ai_module.py requirements.txt "$INSTALL_DIR/"

# Setup venv
echo "[2/4] Setting up Python environment..."
sudo python3 -m venv "$INSTALL_DIR/venv"
sudo "$INSTALL_DIR/venv/bin/pip" install -q -r "$INSTALL_DIR/requirements.txt"

# Create service
echo "[3/4] Creating systemd service..."
sudo tee "$SERVICE_FILE" > /dev/null << 'EOF'
[Unit]
Description=APRS AI Gateway Panel
After=network.target aprs-agent.service

[Service]
Type=simple
Restart=always
RestartSec=5
WorkingDirectory=/opt/aprs-ai-panel
ExecStart=/opt/aprs-ai-panel/venv/bin/python app.py
Environment=APRS_CONFIG=/etc/aprsagent.toml
Environment=AI_PANEL_PORT=8081
StandardOutput=journal
StandardError=journal
SyslogIdentifier=aprs-ai-panel

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable aprs-ai-panel

echo "[4/4] Done!"
echo ""
echo "  Start:  sudo systemctl start aprs-ai-panel"
echo "  Panel:  http://$(hostname -I | awk '{print $1}'):8081"
echo ""
echo "  Configure AI settings in /etc/aprsagent.toml"
echo "  or through the web dashboard."
