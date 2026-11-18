# One image: the React UI is built, then served by the FastAPI backend.
FROM node:22-alpine AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.15-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=ui /ui/dist /app/frontend/dist
# SQLite lives on a volume so data survives container restarts.
ENV DATABASE_URL=sqlite:////data/tracker.db APP_URL=http://localhost:8000 FRONTEND_ORIGIN=http://localhost:8000
VOLUME ["/data"]
EXPOSE 8000
# Hosts that assign a port (Render, Railway, Fly) pass it as $PORT.
CMD ["sh", "-c", "exec python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips=*"]
