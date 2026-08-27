#!/usr/bin/env bash
# ==============================================================================
# WiseWater Automated DigitalOcean Deployment Script
# Supports: Ubuntu 20.04 / 22.04 / 24.04 LTS
# ==============================================================================

set -e

echo "========================================================"
echo " Starting WiseWater Backend Deployment on DigitalOcean "
echo "========================================================"

# 1. Update system packages
echo "[1/6] Updating system packages..."
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv nginx git ufw curl

# 2. Setup project directory
APP_DIR="/var/www/wisewater"
echo "[2/6] Configuring application directory at $APP_DIR..."
sudo mkdir -p $APP_DIR
sudo chown -R $USER:$USER $APP_DIR

# 3. Create Python Virtual Environment
echo "[3/6] Setting up Python virtual environment & dependencies..."
cd $APP_DIR
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
else
    pip install fastapi uvicorn[standard] sqlalchemy pydantic pydantic-settings httpx python-jose[cryptography] passlib[bcrypt] python-multipart
fi

# 4. Generate .env if not present
if [ ! -f "$APP_DIR/.env" ]; then
    echo "[4/6] Creating default production .env configuration..."
    RAND_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    cat <<EOF > $APP_DIR/.env
PROJECT_NAME="WiseWater API"
ENVIRONMENT="production"
DEBUG=False
SECRET_KEY="$RAND_SECRET"
ALGORITHM="HS256"
ACCESS_TOKEN_EXPIRE_MINUTES=10080
CMP_TOKEN_EXPIRE_MINUTES=720
DATABASE_URL="sqlite:///./wisewater.db"
ENABLE_TEST_OTP_BYPASS=False
SMS_PROVIDER="fast2sms"
FAST2SMS_API_KEY=""
EOF
    echo "Generated new production SECRET_KEY in .env"
else
    echo "[4/6] Existing .env found, keeping current configuration."
fi

# 5. Setup Systemd Service
echo "[5/6] Creating systemd service: wisewater.service..."
cat <<EOF | sudo tee /etc/systemd/system/wisewater.service > /dev/null
[Unit]
Description=WiseWater FastAPI Backend Service
After=network.target

[Service]
User=$USER
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/python server.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable wisewater
sudo systemctl restart wisewater

# 6. Configure Nginx Reverse Proxy
echo "[6/6] Configuring Nginx reverse proxy on port 80..."
cat <<EOF | sudo tee /etc/nginx/sites-available/wisewater > /dev/null
server {
    listen 80;
    server_name _;

    client_max_body_size 25M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_connect_timeout 60s;
        proxy_read_timeout 60s;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/wisewater /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx

# 7. Configure Firewall (UFW)
echo "Configuring UFW firewall..."
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable

echo "========================================================"
echo " ✅ Deployment Completed Successfully! "
echo " API is now running live on port 80! "
echo " Test with: curl http://localhost/api/search-apartments"
echo "========================================================"
