FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (separate layer — only rebuilds when requirements.txt changes,
# not on every code change, which keeps rebuilds fast during development)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8501

# Healthcheck so orchestrators (or just `docker ps`) can see if the app is actually up,
# not just that the container is running
HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
