# CFO Sentinel

AI-Powered Financial Survival & Strategic Decision System for SMEs

## Quick Start (Local Development)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Copy .env.example to .env and set your API keys
cp .env.example .env

# 3. Run FastAPI backend
python -m uvicorn api.main:app --reload --port 8000

# 4. Run Streamlit dashboard (optional)
streamlit run dashboard/app.py

# 5. Open API docs
# http://localhost:8000/docs
```

## API Endpoints

| Method | Endpoint                  | Description            | Auth Required |
|--------|---------------------------|------------------------|---------------|
| POST   | `/api/v1/auth/register`   | Daftar user baru       | ❌            |
| POST   | `/api/v1/auth/login`      | Login                  | ❌            |
| POST   | `/api/v1/auth/logout`     | Logout                 | ✅            |
| GET    | `/api/v1/auth/me`         | Get current user       | ✅            |
| POST   | `/api/v1/analysis/run`    | Run financial analysis | ✅            |
| GET    | `/api/v1/history/list`    | Get analysis history   | ✅            |
| GET    | `/api/v1/history/stats`   | Get stats summary      | ✅            |
| POST   | `/api/v1/chat/ask`        | Ask CFO AI             | ✅            |

## Docker Deployment

```bash
docker-compose up --build -d
```

Services:
- **cfo-api**: FastAPI backend on port 8000
- **cfo-dashboard**: Streamlit dashboard on port 8501

## VPS Deployment Guide (Nginx)

Create `/etc/nginx/sites-available/cfo-sentinel`:

```nginx
server {
    listen 80;
    server_name cfosentinel.my.id www.cfosentinel.my.id;

    # FastAPI Backend
    location /api/ {
        proxy_pass         http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }

    # API Docs (Swagger)
    location /docs {
        proxy_pass http://localhost:8000/docs;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
    }

    # React Frontend (akan ditambah nanti)
    location / {
        proxy_pass         http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade $http_upgrade;
        proxy_set_header   Connection "upgrade";
        proxy_set_header   Host $host;
        proxy_read_timeout 86400;
    }
}
```

Enable the site:
```bash
sudo ln -s /etc/nginx/sites-available/cfo-sentinel /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

## Tech Stack

- **Backend**: FastAPI + Python 3.11
- **AI Orchestration**: LangGraph
- **LLM**: Groq (Llama 3.3 70B)
- **Database**: SQLite
- **Dashboard**: Streamlit
- **Validation**: Pydantic 2.x