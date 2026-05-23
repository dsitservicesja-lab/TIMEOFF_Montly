# Deployment Guide

This project is a Flask app with a SQLite database.  
Use the steps below to deploy it on a Linux server with Gunicorn + Nginx.

## 1) Server prerequisites

- Ubuntu/Debian Linux server
- Python 3.10+ installed
- Nginx installed
- A domain name (optional, but recommended)

## 2) Copy project and install dependencies

```bash
sudo mkdir -p /opt/timeoff
sudo chown -R $USER:$USER /opt/timeoff
cd /opt/timeoff

# clone project files
git clone https://github.com/dsitservicesja-lab/TIMEOFF_Montly.git .
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn
sudo chown -R www-data:www-data /opt/timeoff
```

## 3) Set production environment variables

Create a protected environment file:

```bash
sudo mkdir -p /etc/timeoff
echo "SECRET_KEY=replace-with-a-long-random-secret" | sudo tee /etc/timeoff/env > /dev/null
sudo chown root:www-data /etc/timeoff/env
sudo chmod 640 /etc/timeoff/env
```

## 4) Test app startup with Gunicorn

```bash
sudo -u www-data bash -lc 'cd /opt/timeoff && source .venv/bin/activate && source /etc/timeoff/env && gunicorn -w 2 -b 127.0.0.1:8000 "app:create_app()"'
```

If startup works, stop Gunicorn (`Ctrl+C`) and continue.

## 5) Create a systemd service

Create `/etc/systemd/system/timeoff.service`:

```ini
[Unit]
Description=TIMEOFF Monthly Flask App
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/timeoff
EnvironmentFile=/etc/timeoff/env
ExecStart=/opt/timeoff/.venv/bin/gunicorn -w 2 -b 127.0.0.1:8000 "app:create_app()"
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable timeoff
sudo systemctl start timeoff
sudo systemctl status timeoff
```

## 6) Configure Nginx reverse proxy

Create `/etc/nginx/sites-available/timeoff`:

```nginx
server {
    listen 80;
    server_name your-domain-or-server-ip;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable site and reload Nginx:

```bash
sudo ln -s /etc/nginx/sites-available/timeoff /etc/nginx/sites-enabled/timeoff
sudo nginx -t
sudo systemctl reload nginx
```

## 7) (Recommended) Enable HTTPS

If using a domain:

```bash
sudo apt update
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d your-domain
```

## 8) Operations

- Check app logs: `sudo journalctl -u timeoff -f`
- Restart app: `sudo systemctl restart timeoff`
- Check Nginx logs: `/var/log/nginx/access.log` and `/var/log/nginx/error.log`
- Pull latest app updates: `/opt/timeoff/update.sh`
