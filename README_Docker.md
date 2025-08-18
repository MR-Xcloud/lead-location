# Docker Setup for Loan Lead Backend

This document explains how to run the Loan Lead Backend application using Docker.

## Prerequisites

- Docker installed on your system
- Docker Compose installed on your system

## Quick Start

1. **Build and run the application:**
   ```bash
   docker-compose up --build
   ```

2. **Run in detached mode (background):**
   ```bash
   docker-compose up -d --build
   ```

3. **Stop the application:**
   ```bash
   docker-compose down
   ```

## Configuration

The application is configured to run on port **8040** and will be accessible at:
- `http://localhost:8040` - Main API
- `http://localhost:8040/docs` - FastAPI documentation

## Environment Variables

The following environment variables are set in the docker-compose.yml:
- `MONGO_URI`: MongoDB connection string
- `DB_NAME`: Database name

## Important Notes

- The `service_account.json` file is mounted as a volume to maintain Google Sheets integration
- The application includes health checks to ensure it's running properly
- The container will restart automatically unless manually stopped

## Troubleshooting

1. **Check container logs:**
   ```bash
   docker-compose logs loan-lead-backend
   ```

2. **Check container status:**
   ```bash
   docker-compose ps
   ```

3. **Rebuild without cache:**
   ```bash
   docker-compose build --no-cache
   docker-compose up
   ```

## API Endpoints

Once running, the following endpoints will be available:
- `GET /` - Health check
- `POST /signup` - User registration
- `POST /login` - User authentication
- `POST /meetings` - Create meeting entry
- `GET /meetings` - Get meetings
- `GET /image/{meeting_id}` - Get meeting image 