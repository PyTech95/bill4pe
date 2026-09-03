# BILL4PE — Hostinger VPS Deployment Guide

A single-domain setup: Nginx serves the built React app and reverse-proxies
`/api` to the FastAPI backend (uvicorn + gunicorn). MongoDB runs locally.

```
Internet ──▶ Nginx (443, HTTPS) ──┬─▶ /            → React static build
                                  └─▶ /api          → 127.0.0.1:8001 (uvicorn)
                                                       │
                                                       └─▶ MongoDB 127.0.0.1:27017
```

Assumptions: Ubuntu 22.04/24.04 VPS, a domain (`yourdomain.com`) with an A
record pointing to your VPS IP, SSH access as root or a sudo user.

---

## 0. Before you start (security — do this first)

The Razorpay live key and Gemini key you shared earlier are **compromised**
(they were pasted in plaintext). **Regenerate both now**:
- Razorpay Dashboard → Settings → API Keys → Regenerate
- Google AI Studio → revoke + create a new Gemini key

Use TEST Razorpay keys until you've done one successful sandbox transaction,
then switch `RAZORPAY_ENV=live` with the LIVE keys.

---

## 1. Install system packages

```bash
sudo apt update && sudo apt upgrade -y
# Python
sudo apt install -y python3 python3-venv python3-pip
# Node 20 + Yarn
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
sudo npm install -g yarn
# Nginx + certbot
sudo apt install -y nginx
sudo apt install -y certbot python3-certbot-nginx
```

### MongoDB 7
```bash
curl -fsSL https://pgp.mongodb.com/server-7.0.asc | sudo gpg -o /usr/share/keyrings/mongodb-server-7.0.gpg --dearmor
echo "deb [ arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg ] https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/7.0 multiverse" | sudo tee /etc/apt/sources.list.d/mongodb-org-7.0.list
sudo apt update && sudo apt install -y mongodb-org
sudo systemctl enable --now mongod
```

---

## 2. Get the code

```bash
sudo mkdir -p /var/www/bill4pe && sudo chown $USER:$USER /var/www/bill4pe
cd /var/www/bill4pe
# upload your project here (scp/git). You should end with:
#   /var/www/bill4pe/backend  and  /var/www/bill4pe/frontend
```

---

## 3. Backend (FastAPI)

```bash
cd /var/www/bill4pe/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create `/var/www/bill4pe/backend/.env` from `.env.production.example`
(fill in your rotated keys, domain, webhook secret), then lock it down:

```bash
chmod 600 /var/www/bill4pe/backend/.env
```

### systemd service — `/etc/systemd/system/bill4pe.service`
```ini
[Unit]
Description=BILL4PE FastAPI
After=network.target mongod.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/bill4pe/backend
EnvironmentFile=/var/www/bill4pe/backend/.env
ExecStart=/var/www/bill4pe/backend/.venv/bin/uvicorn server:app --host 127.0.0.1 --port 8001 --workers 2
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```bash
sudo chown -R www-data:www-data /var/www/bill4pe
sudo systemctl daemon-reload
sudo systemctl enable --now bill4pe
sudo systemctl status bill4pe --no-pager
curl -s http://127.0.0.1:8001/api/health   # -> {"status":"ok"}
```

---

## 4. Frontend (React build)

```bash
cd /var/www/bill4pe/frontend
# create .env from .env.production.example first (REACT_APP_BACKEND_URL=https://yourdomain.com)
yarn install
yarn build          # outputs ./build
```

---

## 5. Nginx — `/etc/nginx/sites-available/bill4pe`

```nginx
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;

    root /var/www/bill4pe/frontend/build;
    index index.html;

    # HSTS (added after HTTPS is live in step 6)
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    client_max_body_size 15M;   # receipt/audio uploads

    # API -> FastAPI. RAW body is preserved (required for webhook HMAC).
    location /api/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $remote_addr;   # single trusted hop
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }

    # React SPA fallback
    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/bill4pe /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

---

## 6. HTTPS (Let's Encrypt)

```bash
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
# auto-renew is installed as a systemd timer; verify:
sudo certbot renew --dry-run
```

---

## 7. Razorpay webhook

In Razorpay Dashboard → Settings → Webhooks:
- URL: `https://yourdomain.com/api/webhooks/razorpay`  (confirm exact path in `routers/webhooks.py`)
- Set a **signing secret** → paste the same value into `RAZORPAY_WEBHOOK_SECRET`
  and `RAZORPAY_PAYMENT_WEBHOOK_SECRET` in the backend `.env`, then
  `sudo systemctl restart bill4pe`.
- Subscribe to `payment.captured` / `payment.failed` (+ payout events if using RazorpayX).

---

## 8. MongoDB backups (before real data lands)

```bash
sudo mkdir -p /var/backups/bill4pe
# daily 2am dump, keep 14 days
( crontab -l 2>/dev/null; echo '0 2 * * * mongodump --db bill4pe_prod --archive=/var/backups/bill4pe/bill4pe-$(date +\%F).gz --gzip && find /var/backups/bill4pe -name "*.gz" -mtime +14 -delete' ) | crontab -
```

---

## 9. Go-live smoke test (payments)

1. Keep `RAZORPAY_ENV=test`. Create an invoice → pay the fee with a Razorpay
   test card (`4111 1111 1111 1111`, any future expiry/CVV). Confirm the
   wallet/bill updates and the webhook is received.
2. Only then switch to LIVE: set `RAZORPAY_ENV=live`, paste the rotated LIVE
   keys + live webhook secret, `sudo systemctl restart bill4pe`.
3. Do ONE real small-amount transaction and confirm reconciliation, then
   you're production-ready.

---

## Firewall (recommended)

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
# Mongo stays on 127.0.0.1 only — never expose 27017 publicly.
```
