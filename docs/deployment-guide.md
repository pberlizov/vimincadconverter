# ViminCADConverter Deployment Guide

This comprehensive guide covers deploying ViminCADConverter in various environments, from development to production.

## Table of Contents

1. [System Requirements](#system-requirements)
2. [Development Setup](#development-setup)
3. [Docker Deployment](#docker-deployment)
4. [Kubernetes Deployment](#kubernetes-deployment)
5. [Cloud Deployment](#cloud-deployment)
6. [Production Configuration](#production-configuration)
7. [Monitoring and Logging](#monitoring-and-logging)
8. [Security Hardening](#security-hardening)
9. [Performance Tuning](#performance-tuning)
10. [Backup and Recovery](#backup-and-recovery)

## System Requirements

### Minimum Requirements
- **CPU**: 2 cores
- **RAM**: 4GB
- **Storage**: 20GB
- **OS**: Linux (Ubuntu 20.04+, CentOS 8+, RHEL 8+)

### Recommended Requirements
- **CPU**: 4+ cores
- **RAM**: 8GB+
- **Storage**: 100GB+ SSD
- **OS**: Linux with Docker support

### Software Dependencies
- Python 3.11+
- Docker 20.10+ (for containerized deployment)
- Node.js 18+ (for UI development)

## Development Setup

### Local Development

1. **Clone and Setup**
```bash
git clone https://github.com/your-org/ViminCADConverter.git
cd ViminCADConverter

# Create virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev,api,full]"
```

2. **Environment Configuration**
```bash
# Create .env file
cat > .env << EOF
MESH2CAD_STATE_DIR=./tmp_state
MESH2CAD_LOG_LEVEL=DEBUG
MESH2CAD_BIND_HOST=127.0.0.1
MESH2CAD_BIND_PORT=8000
EOF
```

3. **Run Services**
```bash
# Start API server
mesh2cad-api

# Start UI (in separate terminal)
mesh2cad-ui

# Run CLI
mesh2cad example.stl --output-dir ./output
```

### Development with Docker

```bash
# Build development image
docker build -t mesh2cad:dev .

# Run with volume mount
docker run -it --rm \
  -v $(pwd)/tmp_state:/app/state \
  -v $(pwd):/app/src \
  -p 8000:8000 \
  mesh2cad:dev
```

## Docker Deployment

### Single Container Deployment

1. **Build Image**
```bash
docker build -t mesh2cad:latest .
```

2. **Create Environment File**
```bash
cat > .env << EOF
MESH2CAD_STATE_DIR=/app/state
MESH2CAD_LOG_LEVEL=INFO
MESH2CAD_BIND_HOST=0.0.0.0
MESH2CAD_BIND_PORT=8000
MESH2CAD_API_KEYS=your-secret-api-key
MESH2CAD_SECURE_COOKIES=true
EOF
```

3. **Run Container**
```bash
docker run -d \
  --name mesh2cad \
  --env-file .env \
  -v mesh2cad_state:/app/state \
  -p 8000:8000 \
  --restart unless-stopped \
  mesh2cad:latest
```

### Docker Compose Deployment

1. **Basic Setup**
```yaml
# docker-compose.yml
version: '3.8'

services:
  mesh2cad:
    build: .
    ports:
      - "8000:8000"
    environment:
      - MESH2CAD_STATE_DIR=/app/state
      - MESH2CAD_LOG_LEVEL=INFO
      - MESH2CAD_API_KEYS=${MESH2CAD_API_KEYS}
    volumes:
      - mesh2cad_state:/app/state
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

volumes:
  mesh2cad_state:
```

2. **With Redis Queue**
```yaml
# docker-compose.queue.yml
version: '3.8'

services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    restart: unless-stopped

  mesh2cad-api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - MESH2CAD_STATE_DIR=/app/state
      - MESH2CAD_REDIS_URL=redis://redis:6379/0
      - MESH2CAD_JOB_BACKEND=rq
      - MESH2CAD_RATE_LIMIT_BACKEND=redis
    volumes:
      - mesh2cad_state:/app/state
    depends_on:
      - redis
    restart: unless-stopped

  mesh2cad-worker:
    build: .
    command: mesh2cad-rq-worker
    environment:
      - MESH2CAD_STATE_DIR=/app/state
      - MESH2CAD_REDIS_URL=redis://redis:6379/0
      - MESH2CAD_JOB_BACKEND=rq
    volumes:
      - mesh2cad_state:/app/state
    depends_on:
      - redis
    restart: unless-stopped
    deploy:
      replicas: 2

volumes:
  mesh2cad_state:
  redis_data:
```

3. **Deploy**
```bash
# Basic deployment
docker-compose up -d --build

# With queue
docker-compose -f docker-compose.yml -f docker-compose.queue.yml up -d --build
```

## Kubernetes Deployment

### Namespace and Configuration

```yaml
# k8s/namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: mesh2cad
---
# k8s/configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: mesh2cad-config
  namespace: mesh2cad
data:
  MESH2CAD_LOG_LEVEL: "INFO"
  MESH2CAD_BIND_HOST: "0.0.0.0"
  MESH2CAD_BIND_PORT: "8000"
  MESH2CAD_JOB_BACKEND: "rq"
  MESH2CAD_RATE_LIMIT_BACKEND: "redis"
---
# k8s/secret.yaml
apiVersion: v1
kind: Secret
metadata:
  name: mesh2cad-secrets
  namespace: mesh2cad
type: Opaque
data:
  MESH2CAD_API_KEYS: <base64-encoded-api-keys>
  MESH2CAD_REDIS_URL: <base64-encoded-redis-url>
```

### Redis Deployment

```yaml
# k8s/redis.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: redis
  namespace: mesh2cad
spec:
  replicas: 1
  selector:
    matchLabels:
      app: redis
  template:
    metadata:
      labels:
        app: redis
    spec:
      containers:
      - name: redis
        image: redis:7-alpine
        ports:
        - containerPort: 6379
        resources:
          requests:
            memory: "256Mi"
            cpu: "100m"
          limits:
            memory: "512Mi"
            cpu: "200m"
        volumeMounts:
        - name: redis-data
          mountPath: /data
      volumes:
      - name: redis-data
        persistentVolumeClaim:
          claimName: redis-pvc
---
apiVersion: v1
kind: Service
metadata:
  name: redis
  namespace: mesh2cad
spec:
  selector:
    app: redis
  ports:
  - port: 6379
    targetPort: 6379
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: redis-pvc
  namespace: mesh2cad
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 1Gi
```

### Application Deployment

```yaml
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mesh2cad-api
  namespace: mesh2cad
spec:
  replicas: 2
  selector:
    matchLabels:
      app: mesh2cad-api
  template:
    metadata:
      labels:
        app: mesh2cad-api
    spec:
      containers:
      - name: mesh2cad-api
        image: mesh2cad:latest
        ports:
        - containerPort: 8000
        env:
        - name: MESH2CAD_STATE_DIR
          value: "/app/state"
        - name: MESH2CAD_LOG_LEVEL
          valueFrom:
            configMapKeyRef:
              name: mesh2cad-config
              key: MESH2CAD_LOG_LEVEL
        - name: MESH2CAD_API_KEYS
          valueFrom:
            secretKeyRef:
              name: mesh2cad-secrets
              key: MESH2CAD_API_KEYS
        - name: MESH2CAD_REDIS_URL
          valueFrom:
            secretKeyRef:
              name: mesh2cad-secrets
              key: MESH2CAD_REDIS_URL
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "2Gi"
            cpu: "1000m"
        volumeMounts:
        - name: mesh2cad-state
          mountPath: /app/state
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
      volumes:
      - name: mesh2cad-state
        persistentVolumeClaim:
          claimName: mesh2cad-pvc
---
apiVersion: v1
kind: Service
metadata:
  name: mesh2cad-api
  namespace: mesh2cad
spec:
  selector:
    app: mesh2cad-api
  ports:
  - port: 8000
    targetPort: 8000
  type: ClusterIP
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: mesh2cad-pvc
  namespace: mesh2cad
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
```

### Worker Deployment

```yaml
# k8s/worker.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mesh2cad-worker
  namespace: mesh2cad
spec:
  replicas: 3
  selector:
    matchLabels:
      app: mesh2cad-worker
  template:
    metadata:
      labels:
        app: mesh2cad-worker
    spec:
      containers:
      - name: mesh2cad-worker
        image: mesh2cad:latest
        command: ["mesh2cad-rq-worker"]
        env:
        - name: MESH2CAD_STATE_DIR
          value: "/app/state"
        - name: MESH2CAD_REDIS_URL
          valueFrom:
            secretKeyRef:
              name: mesh2cad-secrets
              key: MESH2CAD_REDIS_URL
        resources:
          requests:
            memory: "1Gi"
            cpu: "500m"
          limits:
            memory: "4Gi"
            cpu: "2000m"
        volumeMounts:
        - name: mesh2cad-state
          mountPath: /app/state
      volumes:
      - name: mesh2cad-state
        persistentVolumeClaim:
          claimName: mesh2cad-pvc
```

### Ingress Configuration

```yaml
# k8s/ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: mesh2cad-ingress
  namespace: mesh2cad
  annotations:
    kubernetes.io/ingress.class: nginx
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/proxy-body-size: "100m"
spec:
  tls:
  - hosts:
    - api.yourdomain.com
    secretName: mesh2cad-tls
  rules:
  - host: api.yourdomain.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: mesh2cad-api
            port:
              number: 8000
```

### Deploy to Kubernetes

```bash
# Apply all configurations
kubectl apply -k k8s/

# Check deployment status
kubectl get pods -n mesh2cad
kubectl get services -n mesh2cad
kubectl get ingress -n mesh2cad

# View logs
kubectl logs -f deployment/mesh2cad-api -n mesh2cad
kubectl logs -f deployment/mesh2cad-worker -n mesh2cad
```

## Cloud Deployment

### AWS ECS Deployment

1. **Create ECR Repository**
```bash
aws ecr create-repository --repository-name mesh2cad
```

2. **Build and Push Image**
```bash
# Build image
docker build -t mesh2cad:latest .

# Tag for ECR
aws ecr get-login-password --region us-west-2 | docker login --username AWS --password-stdin <account-id>.dkr.ecr.us-west-2.amazonaws.com
docker tag mesh2cad:latest <account-id>.dkr.ecr.us-west-2.amazonaws.com/mesh2cad:latest

# Push to ECR
docker push <account-id>.dkr.ecr.us-west-2.amazonaws.com/mesh2cad:latest
```

3. **ECS Task Definition**
```json
{
  "family": "mesh2cad",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "1024",
  "memory": "2048",
  "executionRoleArn": "arn:aws:iam::<account-id>:role/ecsTaskExecutionRole",
  "taskRoleArn": "arn:aws:iam::<account-id>:role/ecsTaskRole",
  "containerDefinitions": [
    {
      "name": "mesh2cad",
      "image": "<account-id>.dkr.ecr.us-west-2.amazonaws.com/mesh2cad:latest",
      "portMappings": [
        {
          "containerPort": 8000,
          "protocol": "tcp"
        }
      ],
      "environment": [
        {
          "name": "MESH2CAD_LOG_LEVEL",
          "value": "INFO"
        }
      ],
      "secrets": [
        {
          "name": "MESH2CAD_API_KEYS",
          "valueFrom": "arn:aws:secretsmanager:us-west-2:<account-id>:secret:mesh2cad/api-keys"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/mesh2cad",
          "awslogs-region": "us-west-2",
          "awslogs-stream-prefix": "ecs"
        }
      },
      "healthCheck": {
        "command": ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"],
        "interval": 30,
        "timeout": 5,
        "retries": 3
      }
    }
  ]
}
```

### Google Cloud Run

1. **Build and Deploy**
```bash
# Build with Cloud Build
gcloud builds submit --tag gcr.io/your-project/mesh2cad

# Deploy to Cloud Run
gcloud run deploy mesh2cad \
  --image gcr.io/your-project/mesh2cad \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 1 \
  --max-instances 10 \
  --set-env-vars MESH2CAD_LOG_LEVEL=INFO \
  --set-secrets MESH2CAD_API_KEYS=mesh2cad-api-keys:latest
```

### Azure Container Instances

```bash
# Create resource group
az group create --name mesh2cad-rg --location eastus

# Deploy container
az container create \
  --resource-group mesh2cad-rg \
  --name mesh2cad \
  --image your-registry/mesh2cad:latest \
  --cpu 2 \
  --memory 4 \
  --ports 8000 \
  --environment-variables MESH2CAD_LOG_LEVEL=INFO \
  --secure-environment-variables MESH2CAD_API_KEYS=your-key
```

## Production Configuration

### Environment Variables

```bash
# Core settings
MESH2CAD_STATE_DIR=/app/state
MESH2CAD_LOG_LEVEL=INFO
MESH2CAD_LOG_JSON=true
MESH2CAD_BIND_HOST=0.0.0.0
MESH2CAD_BIND_PORT=8000

# Performance
MESH2CAD_JOB_WORKERS=4
MESH2CAD_JOB_TIMEOUT_SEC=1800
MESH2CAD_MAX_UPLOAD_MB=200

# Security
MESH2CAD_API_KEYS=key1,key2,key3
MESH2CAD_SECURE_COOKIES=true
MESH2CAD_CORS_ORIGINS=https://yourdomain.com,https://app.yourdomain.com

# Rate limiting
MESH2CAD_RATE_LIMIT_PER_MINUTE=60
MESH2CAD_RATE_LIMIT_PER_HOUR=500
MESH2CAD_RATE_LIMIT_PER_DAY=5000
MESH2CAD_RATE_LIMIT_BACKEND=redis
MESH2CAD_REDIS_URL=redis://redis:6379/0

# Monitoring
MESH2CAD_METRICS_ENABLED=true
MESH2CAD_WEBHOOK_SECRET=webhook-secret
```

### Performance Tuning

1. **Database Optimization**
```bash
# SQLite optimization
export MESH2CAD_SQLITE_JOURNAL_MODE=WAL
export MESH2CAD_SQLITE_SYNCHRONOUS=NORMAL
export MESH2CAD_SQLITE_CACHE_SIZE=2000
```

2. **Worker Configuration**
```yaml
# docker-compose.yml
services:
  mesh2cad-worker:
    deploy:
      replicas: 4
      resources:
        limits:
          cpus: '2.0'
          memory: 4G
        reservations:
          cpus: '1.0'
          memory: 2G
```

3. **Resource Limits**
```bash
# System limits
ulimit -n 65536  # File descriptors
ulimit -u 4096   # User processes

# Container limits
docker run --memory=4g --cpus=2.0 mesh2cad:latest
```

## Monitoring and Logging

### Prometheus Metrics

```yaml
# prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'mesh2cad'
    static_configs:
      - targets: ['mesh2cad:8000']
    metrics_path: /metrics
    scrape_interval: 30s
```

### Grafana Dashboard

```json
{
  "dashboard": {
    "title": "ViminCADConverter Metrics",
    "panels": [
      {
        "title": "Request Rate",
        "type": "graph",
        "targets": [
          {
            "expr": "rate(mesh2cad_requests_total[5m])",
            "legendFormat": "{{method}} {{endpoint}}"
          }
        ]
      },
      {
        "title": "Processing Time",
        "type": "graph",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rate(mesh2cad_request_duration_seconds_bucket[5m]))",
            "legendFormat": "95th percentile"
          }
        ]
      },
      {
        "title": "Job Queue Length",
        "type": "singlestat",
        "targets": [
          {
            "expr": "mesh2cad_job_queue_length"
          }
        ]
      }
    ]
  }
}
```

### Log Aggregation

```yaml
# filebeat.yml
filebeat.inputs:
- type: container
  paths:
    - '/var/lib/docker/containers/*/*.log'
  processors:
    - add_docker_metadata:
        host: "unix:///var/run/docker.sock"

output.elasticsearch:
  hosts: ["elasticsearch:9200"]
  index: "mesh2cad-%{+yyyy.MM.dd}"

setup.kibana:
  host: "kibana:5601"
```

### Health Checks

```bash
# Comprehensive health check script
#!/bin/bash

check_health() {
    local endpoint=$1
    local response=$(curl -s -o /dev/null -w "%{http_code}" "$endpoint")
    
    if [ "$response" = "200" ]; then
        echo "✓ $endpoint is healthy"
        return 0
    else
        echo "✗ $endpoint returned $response"
        return 1
    fi
}

check_health "http://localhost:8000/health"
check_health "http://localhost:8000/ready"
check_health "http://localhost:8000/metrics"
```

## Security Hardening

### SSL/TLS Configuration

```nginx
# nginx.conf
server {
    listen 443 ssl http2;
    server_name api.yourdomain.com;
    
    ssl_certificate /etc/ssl/certs/mesh2cad.crt;
    ssl_certificate_key /etc/ssl/private/mesh2cad.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512;
    ssl_prefer_server_ciphers off;
    
    client_max_body_size 100M;
    
    location / {
        proxy_pass http://mesh2cad:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Container Security

```dockerfile
# Multi-stage build for smaller image
FROM python:3.11-slim as builder
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

FROM python:3.11-slim
RUN adduser --disabled-password --gecos '' mesh2cad
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /app/src /app/src
COPY --from=builder /app/pyproject.toml /app/
USER mesh2cad
EXPOSE 8000
CMD ["mesh2cad-api"]
```

### Network Security

```yaml
# docker-compose.security.yml
version: '3.8'

services:
  mesh2cad:
    build: .
    networks:
      - frontend
      - backend
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 4G
    
  nginx:
    image: nginx:alpine
    networks:
      - frontend
    ports:
      - "443:443"
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./ssl:/etc/ssl

  redis:
    image: redis:7-alpine
    networks:
      - backend
    command: redis-server --requirepass ${REDIS_PASSWORD}

networks:
  frontend:
    driver: bridge
  backend:
    driver: bridge
    internal: true
```

## Backup and Recovery

### Data Backup Script

```bash
#!/bin/bash
# backup-mesh2cad.sh

BACKUP_DIR="/backup/mesh2cad"
STATE_DIR="/app/state"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/mesh2cad_backup_$DATE.tar.gz"

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Backup state directory
tar -czf "$BACKUP_FILE" -C "$(dirname "$STATE_DIR")" "$(basename "$STATE_DIR")"

# Upload to S3 (optional)
if [ -n "$AWS_S3_BUCKET" ]; then
    aws s3 cp "$BACKUP_FILE" "s3://$AWS_S3_BUCKET/backups/"
fi

# Clean old backups (keep last 7 days)
find "$BACKUP_DIR" -name "mesh2cad_backup_*.tar.gz" -mtime +7 -delete

echo "Backup completed: $BACKUP_FILE"
```

### Recovery Script

```bash
#!/bin/bash
# recover-mesh2cad.sh

BACKUP_FILE=$1
STATE_DIR="/app/state"

if [ -z "$BACKUP_FILE" ]; then
    echo "Usage: $0 <backup_file>"
    exit 1
fi

# Stop services
docker-compose down

# Clear current state
rm -rf "$STATE_DIR"/*
mkdir -p "$STATE_DIR"

# Restore from backup
tar -xzf "$BACKUP_FILE" -C "$(dirname "$STATE_DIR")"

# Start services
docker-compose up -d

echo "Recovery completed from: $BACKUP_FILE"
```

### Automated Backup

```yaml
# k8s/backup-cronjob.yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: mesh2cad-backup
  namespace: mesh2cad
spec:
  schedule: "0 2 * * *"  # Daily at 2 AM
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: backup
            image: mesh2cad:latest
            command:
            - /bin/bash
            - -c
            - |
              tar -czf /backup/mesh2cad_$(date +%Y%m%d_%H%M%S).tar.gz /app/state
              aws s3 cp /backup/mesh2cad_$(date +%Y%m%d_%H%M%S).tar.gz s3://backup-bucket/
            env:
            - name: AWS_ACCESS_KEY_ID
              valueFrom:
                secretKeyRef:
                  name: aws-credentials
                  key: access-key-id
            - name: AWS_SECRET_ACCESS_KEY
              valueFrom:
                secretKeyRef:
                  name: aws-credentials
                  key: secret-access-key
            volumeMounts:
            - name: mesh2cad-state
              mountPath: /app/state
            - name: backup-storage
              mountPath: /backup
          volumes:
          - name: mesh2cad-state
            persistentVolumeClaim:
              claimName: mesh2cad-pvc
          - name: backup-storage
            emptyDir: {}
          restartPolicy: OnFailure
```

## Troubleshooting

### Common Issues

1. **High Memory Usage**
```bash
# Check memory usage
docker stats mesh2cad

# Monitor with Prometheus
curl http://localhost:8000/metrics | grep memory
```

2. **Slow Processing**
```bash
# Check worker status
curl http://localhost:8000/v1/jobs/stats

# Monitor queue length
redis-cli llen mesh2cad
```

3. **Database Issues**
```bash
# Check SQLite integrity
sqlite3 /app/state/mesh2cad.db "PRAGMA integrity_check;"

# Rebuild indexes
sqlite3 /app/state/mesh2cad.db "REINDEX;"
```

### Debug Commands

```bash
# Check service health
curl http://localhost:8000/health

# View detailed metrics
curl http://localhost:8000/metrics

# Check rate limiting status
curl -H "X-API-Key: your-key" http://localhost:8000/v1/rate-limit/status

# Test file upload
curl -X POST -F "file=@test.stl" http://localhost:8000/v1/process
```

This deployment guide provides comprehensive coverage for deploying ViminCADConverter in various environments. Adjust configurations based on your specific requirements and infrastructure.
