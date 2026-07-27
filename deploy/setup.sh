#!/usr/bin/env bash
# Run once on a fresh Ubuntu 24.04 EC2 box:
#   ssh -i axiora-dev-key.pem ubuntu@<IP> 'bash -s' < setup.sh
# After this, GitHub Actions handles every deploy.

set -euo pipefail

echo "▸ Installing Docker"
sudo apt-get update -qq
sudo apt-get install -y -qq ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" |
	sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
sudo apt-get update -qq
sudo apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

sudo usermod -aG docker ubuntu
sudo systemctl enable --now docker

echo "▸ Creating /opt/axiora"
sudo mkdir -p /opt/axiora/dist /opt/axiora/axiora-pulse-be
sudo chown -R ubuntu:ubuntu /opt/axiora

echo
echo "Done. Docker $(sudo docker --version | cut -d' ' -f3 | tr -d ,) installed."
echo "Next: create /opt/axiora/.env, then push to develop to trigger a deploy."
