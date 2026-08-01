#!/usr/bin/env bash
# ==============================================================================
# VDSINA VPS Deployment Script — AI Adaptive Coach v7.0
# Autonomous Setup Script for Ubuntu 22.04 / 24.04 LTS on VDSINA VPS
# ==============================================================================

set -euo pipefail

echo "================================================================="
echo " 🚀 VDSINA VPS Automated Setup — AI Adaptive Coach v7.0"
echo "================================================================="

# 1. System Updates & Prerequisites
echo "[1/6] Updating APT packages and installing Docker..."
sudo apt-get update -y
sudo apt-get install -y curl git ufw certbot python3-certbot-nginx ca-certificates gnupg

# Install Docker & Docker Compose if missing
if ! command -v docker &> /dev/null; then
    echo "Installing Docker Engine..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker "$USER"
    rm get-docker.sh
fi

# 2. Firewall Configuration (UFW)
echo "[2/6] Configuring UFW Firewall..."
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable

# 3. Clone / Update Repository
PROJECT_DIR="/opt/ai_coach"
echo "[3/6] Setting up project repository in ${PROJECT_DIR}..."

if [ ! -d "$PROJECT_DIR" ]; then
    echo "Cloning repository from GitHub..."
    sudo git clone https://github.com/AnanyevMA/AI-Coach.git "$PROJECT_DIR"
    sudo chown -R "$USER:$USER" "$PROJECT_DIR"
else
    echo "Updating repository from GitHub..."
    cd "$PROJECT_DIR"
    git pull origin main
fi

cd "$PROJECT_DIR"

# 4. Check Environment File (.env)
echo "[4/6] Verifying environment configuration (.env)..."
if [ ! -f ".env" ]; then
    echo "Creating .env file from .env.example..."
    cp .env.example .env
    echo "⚠️ WARNING: Please edit ${PROJECT_DIR}/.env with your real TELEGRAM_BOT_TOKEN and GEMINI_API_KEY!"
fi

# 5. Build and Start Docker Containers
echo "[5/6] Building and starting Docker services (FastAPI, PostgreSQL, Redis, Nginx, Telegram Bot)..."
docker compose down || true
docker compose build --no-cache
docker compose up -d

# 6. Verify Deployment Health
echo "[6/6] Verifying deployment status..."
sleep 5
docker compose ps

echo "================================================================="
echo " ✅ VDSINA VPS Deployment Completed Successfully!"
echo " 🤖 Telegram Bot & Backend are running in Docker."
echo " 🔗 Check Health: curl http://localhost:8000/health"
echo "================================================================="
