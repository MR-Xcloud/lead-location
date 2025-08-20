# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Ensure service_account.json is copied
COPY service_account.json /app/service_account.json

# Create .env file from environment variables (will be overridden by docker-compose)
RUN echo "MONGO_URI=mongodb+srv://dbAdmin:admin%40123@cluster0.gcitgdq.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0" > .env && \
    echo "DB_NAME=client_meetings" >> .env

# Expose port 8040
EXPOSE 8040

# Command to run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8040"] 