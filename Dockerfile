FROM python:3.12-slim

# Install system dependencies: ffmpeg, fonts, curl, git
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fonts-dejavu-core \
    fonts-liberation \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set up non-root user with UID 1000 (Hugging Face Spaces standard)
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PORT=7860

WORKDIR $HOME/app

# Install Python requirements
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Copy application files
COPY --chown=user . .

# Ensure upload/output directories exist
RUN mkdir -p uploads output

EXPOSE 7860

CMD ["python", "app.py"]
