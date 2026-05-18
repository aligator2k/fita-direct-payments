# Use Python 3.12 because Python 3.14 (your local version) doesn't have
# pre-built wheels for all dependencies yet.
FROM python:3.12-slim

# Don't write .pyc files, flush stdout immediately so logs appear in real time.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Set working directory inside the container.
WORKDIR /app

# Install only what's needed for mysql-connector-python and matplotlib.
# A few system libs are required even by slim Python images.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first, separately from copying the code.
# This way, code changes don't invalidate the dependency layer cache.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Now copy the rest of the project.
COPY schema_extractor.py plan_generator.py report_builder.py gemini_client.py main.py ./

# Default command: run the full pipeline.
CMD ["python", "main.py"]