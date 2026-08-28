FROM python:3.12-slim

# Install system dependencies: ffmpeg, fonts, curl, git
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fonts-dejavu-core \
    fonts-liberation \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Ensure upload/output directories exist
RUN mkdir -p uploads output

# Expose port (default 5000 or cloud )
ENV PORT=5000
EXPOSE 5000

# Start server via python app.py
CMD ["python", "app.py"]
