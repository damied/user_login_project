# KDT Resource — Dual-Backend Auth System (Node.js + Flask on AWS)

A user authentication system (register / login / JWT-protected dashboard) implemented twice — once in **Node.js/Express** and once in **Python/Flask** — both backed by a shared **MongoDB Atlas** cluster, deployed to a single **AWS EC2** instance behind **Nginx**, and served over **HTTPS** via free Let's Encrypt certificates.

Live:
- `https://kdtresource.online` → Node.js/Express backend
- `https://www.kdtresource.online` → Python/Flask backend (via Gunicorn)

---

## Screenshots

| Node.js backend | Flask backend |
|---|---|
| ![Node login](screenshots/node-login.png) | ![Flask login](screenshots/flask-login.png) |
| ![Node dashboard](screenshots/node-dashboard.png) | ![Flask dashboard](screenshots/flask-dashboard.png) |

---

## Architecture

## Architecture

```
                                   ┌───────────────────────────────────────┐
                                   │            EC2 Instance                │
                                   │         (Ubuntu 24.04, Nginx)          │
                                   │                                         │
kdtresource.online     ──HTTPS──▶ │  Nginx :443 ──▶ Node/Express :4000     │
                                   │                  (PM2-managed)          │
                                   │                                         │
www.kdtresource.online ──HTTPS──▶ │  Nginx :443 ──▶ Flask/Gunicorn :5000    │
                                   │                  (PM2-managed)          │
                                   └────────────────────┬────────────────────┘
                                                          │
                                                          ▼
                                             MongoDB Atlas (shared cluster,
                                               `kdt_resource` database)
```

Both backends implement the same REST contract and share the same database, so a user registered on one domain can log in on the other.

| Route | Method | Description |
|---|---|---|
| `/api/auth/register` | POST | Hash password (bcrypt), create user, return JWT |
| `/api/auth/login` | POST | Verify password hash, return JWT |
| `/api/auth/me` | GET | JWT-protected — returns current user profile |

---

## Stack

| Layer | Technology |
|---|---|
| Backend A | Node.js 22, Express 4, Mongoose, bcryptjs, jsonwebtoken |
| Backend B | Python 3.14, Flask 3, PyMongo, bcrypt, PyJWT, Gunicorn |
| Database | MongoDB Atlas (M0 free tier) |
| Reverse proxy | Nginx |
| Process manager | PM2 (manages both the Node process and the Gunicorn/Flask process) |
| TLS | Let's Encrypt via Certbot (Nginx plugin, auto-renewing) |
| Hosting | AWS EC2 (Ubuntu 24.04, t2/t3.micro — free tier) |
| DNS | Namecheap (A records → EC2 public IP) |

---

## Repository Structure

```
.
├── node_project/              # Express backend
│   ├── server.js
│   ├── package.json
│   ├── .env.example
│   └── public/
│       ├── index.html         # register/login page
│       └── dashboard.html
│
└── flask_project/             # Flask backend
    ├── app.py
    ├── requirements.txt
    ├── ecosystem.config.js
    └── public/
        ├── index.html
        └── dashboard.html
```

---

## Local Development

### Node.js backend
```bash
cd node_project
npm install
cp .env.example .env        # fill in MONGO_URI, JWT_SECRET, PORT=4000
npm start
```

### Flask backend
```bash
cd flask_project
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
# create .env with MONGO_URI, JWT_SECRET, PORT=5000
python app.py
```

Both apps read `MONGO_URI` and `JWT_SECRET` from `.env` — use the **same values** for both if you want sessions to be portable between them.

---

## Production Deployment (EC2)

### 1. Provision the server
- Ubuntu 24.04 LTS, t2/t3.micro (free tier)
- Security group: inbound 22 (SSH), 80 (HTTP), 443 (HTTPS) only
- Install: `nodejs` (v20+ via NodeSource), `python3-venv`, `nginx`, `git`

### 2. Deploy each app
- Transfer source via `rsync`/`scp` (exclude `node_modules` / `venv` — reinstall fresh on the server)
- Node: `npm install` → run under PM2 (`pm2 start server.js --name node`)
- Flask: create venv → `pip install -r requirements.txt` → run **Gunicorn** (not the Flask dev server) under PM2:
  ```bash
  pm2 start "venv/bin/gunicorn -w 2 -b 127.0.0.1:5000 app:app" --name flask-app
  ```
- `pm2 startup && pm2 save` on both, so processes survive a reboot

### 3. DNS
Point A records at the EC2 public IP:
```
@     A    <EC2_PUBLIC_IP>
www   A    <EC2_PUBLIC_IP>
```

### 4. Nginx — hostname-based routing
Two independent `server` blocks, split by `server_name`, each proxying to a different local port:

```nginx
# kdtresource.online -> Node
server {
    listen 443 ssl;
    server_name kdtresource.online;

    ssl_certificate     /etc/letsencrypt/live/kdtresource.online/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/kdtresource.online/privkey.pem;
    include              /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam          /etc/letsencrypt/ssl-dhparams.pem;

    location / {
        proxy_pass http://localhost:4000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

# www.kdtresource.online -> Flask
server {
    listen 443 ssl;
    server_name www.kdtresource.online;

    ssl_certificate     /etc/letsencrypt/live/www.kdtresource.online/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/www.kdtresource.online/privkey.pem;
    include              /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam          /etc/letsencrypt/ssl-dhparams.pem;

    location / {
        proxy_pass http://localhost:5000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

# HTTP -> HTTPS redirect (both hosts)
server {
    listen 80;
    server_name kdtresource.online www.kdtresource.online;
    return 301 https://$host$request_uri;
}
```

Backend ports (4000, 5000) are **never opened in the security group** — they're only reachable via Nginx on the loopback interface. The only public entry points are 80/443.

### 5. TLS
```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d kdtresource.online
sudo certbot --nginx -d www.kdtresource.online
```
Certbot auto-configures the Nginx SSL block and schedules renewal (certs are valid 90 days; renewal runs automatically via systemd timer — verify with `sudo systemctl list-timers | grep certbot`).

---

## Key Design Decisions

- **Hostname-based routing, not path-based.** Both backends implement the *same* API — path-based routing (`/flask/...`) would collide on identical routes and leak implementation details into URLs. Splitting by hostname keeps each backend's URL space clean.
- **Gunicorn over Flask's dev server.** Flask's built-in server is explicitly unsafe for production (single-threaded, debugger exposes remote code execution risk). Gunicorn + PM2 mirrors the same "process manager in front of the app, Nginx never talks to a dev server" pattern used for the Node side.
- **PM2 for both languages.** One consistent operational surface (`pm2 status`, `pm2 logs`, `pm2 startup`) instead of separate tooling per language.
- **Let's Encrypt over ACM.** ACM certificates only integrate with AWS-managed services (ALB, CloudFront, API Gateway) — they cannot be installed directly on an EC2/Nginx box. An ALB was intentionally avoided here since it adds cost/complexity with no benefit for a single-instance deployment; Certbot's free, auto-renewing certs are the standard choice at this scale.

---

## Known Issues Encountered & Fixes

| Issue | Root Cause | Fix |
|---|---|---|
| `nginx -t` failed: `open() "sites-enabled/default" failed` | Dangling symlink left after removing the default site | Removed the broken symlink from `sites-enabled` |
| Root domain served under wrong TLS cert | Certbot's second run (for `www`) deployed its cert into the same combined config block as the root domain | Rewrote Nginx config into two explicit `server` blocks, each with its own cert path |
| `Cannot find module 'finalhandler'` (Express) | `package.json` didn't survive an early file transfer, leaving a stale/partial `node_modules` | Recreated `package.json`, wiped `node_modules`, reinstalled clean |
| `externally-managed-environment` (pip) | Ubuntu 24.04 blocks system-wide `pip install` (PEP 668) | Installed dependencies inside an isolated `venv` instead |

---

## Security Notes

- Passwords are hashed with `bcrypt` (12 rounds) — never stored in plaintext.
- JWTs are signed with a 256-bit random secret (`crypto.randomBytes(32)`), 7-day expiry.
- `.env` files (containing `MONGO_URI` and `JWT_SECRET`) are gitignored and **never committed**.
- Both app ports (4000, 5000) are bound to `127.0.0.1` / not exposed in the security group — Nginx is the only public-facing surface.

**Before deploying this yourself:** generate your own `JWT_SECRET` and use your own MongoDB Atlas credentials. Never reuse the example values in this repo.

---

## Next Steps

- [ ] Rate-limit `/api/auth/login` to mitigate brute-force attempts
- [ ] Move shared secrets into a centralized secrets manager (e.g. AWS Secrets Manager) instead of duplicated `.env` files
- [ ] Add structured logging / basic monitoring (e.g. PM2 log rotation, uptime checks)
- [ ] Evaluate ALB + ACM if a second instance is added for redundancy
