# ERakshak — container image (API + dashboard)
FROM python:3.11-slim

WORKDIR /app

# System deps for pdfplumber/reportlab (fonts, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libjpeg-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000 8501

# Default: run the API. Override command for the dashboard.
CMD ["uvicorn", "backend.app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
