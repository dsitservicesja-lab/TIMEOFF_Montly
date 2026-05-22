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

# copy project files here, then:
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn
```

## 3) Set production environment variables

Set a strong secret key before starting the app:

```bash
export SECRET_KEY='replace-with-a-long-random-secret'
```

## 4) Test app startup with Gunicorn

```bash
cd /opt/timeoff
source .venv/bin/activate
gunicorn -w 2 -b 127.0.0.1:8000 "app:create_app()"
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
Environment="SECRET_KEY=replace-with-a-long-random-secret"
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

