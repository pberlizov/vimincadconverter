# ViminCADConverter API Reference

This document provides comprehensive API documentation for the ViminCADConverter mesh-to-CAD conversion service.

## Overview

ViminCADConverter provides both synchronous and asynchronous REST APIs for converting triangle meshes (STL/OBJ/PLY) and point clouds (XYZ/PTS/CSV/NPY) into parametric CAD programs using build123d.

## Base URL

```
http://localhost:8000  # Default
https://your-domain.com  # Production
```

## Authentication

If `MESH2CAD_API_KEYS` is configured, include an API key:

```bash
# Header method
X-API-Key: YOUR_API_KEY

# Bearer token method
Authorization: Bearer YOUR_API_KEY
```

## Rate Limiting

- **Default**: 120 requests per minute per IP
- **Burst limit**: 10 requests in 10 seconds
- **Hourly limit**: 1000 requests per hour
- **Daily limit**: 10000 requests per day

Rate limit headers are included in responses:

```
X-RateLimit-Limit-Minute: 120
X-RateLimit-Remaining-Minute: 119
X-RateLimit-Reset-Minute: 1640995200
```

## Error Handling

All errors return JSON with consistent structure:

```json
{
  "error": {
    "type": "ValidationError",
    "message": "Invalid input parameters",
    "details": {
      "field": "sample_count",
      "value": -1,
      "constraint": "must be positive"
    },
    "request_id": "req_123456789"
  }
}
```

### Error Types

- `ValidationError`: Invalid input parameters
- `FileUploadError`: File validation failed
- `MeshLoadError`: Mesh loading failed
- `GeometryError`: Geometry processing failed
- `CADGenerationError`: CAD generation failed
- `RateLimitError`: Rate limit exceeded
- `InsufficientResourcesError`: System resources insufficient

## API Endpoints

### Health Checks

#### GET /health

Check if the service is running.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2026-04-27T14:30:00Z",
  "version": "0.1.0"
}
```

#### GET /ready

Check if the service is ready to handle requests.

**Response:**
```json
{
  "status": "ready",
  "timestamp": "2026-04-27T14:30:00Z",
  "checks": {
    "database": "ok",
    "state_dir": "writable",
    "redis": "ok"  // If configured
  }
}
```

### Synchronous Processing

#### POST /v1/process

Process a mesh file synchronously and return results immediately.

**Request:**
```bash
curl -X POST "http://localhost:8000/v1/process" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@part.stl" \
  -F "build=true" \
  -F "sample_count=5000" \
  -F "include_script=true"
```

**Form Data:**
- `file` (required): Mesh or point cloud file
- `build` (optional, default: `true`): Execute CAD build
- `sample_count` (optional, default: `5000`): Surface sample count
- `simplify_target_faces` (optional): Target face count for simplification
- `auto_tune_sampling` (optional, default: `true`): Auto-tune sample count
- `align_surface_metrics` (optional, default: `true`): ICP alignment for validation
- `icp_iterations` (optional, default: `10`): ICP iteration count
- `icp_seed` (optional, default: `0`): ICP random seed
- `include_script` (optional, default: `true`): Include generated script
- `repair_component_index` (optional): Multi-body component index

**Response:**
```json
{
  "session_id": "sess_abc123",
  "status": "completed",
  "input_path": "/tmp/sess_abc123/input.stl",
  "detection_report": {
    "part_class": "prismatic",
    "primitive_kinds": ["plane", "cylinder"],
    "feature_kinds": ["base_extrude", "through_hole"]
  },
  "validation_report": {
    "rms_error": 0.001,
    "max_error": 0.005,
    "volume_delta_ratio": 0.02,
    "bbox_delta_ratio": 0.01
  },
  "build": {
    "script": "# Generated build123d script\n...",
    "metadata": {
      "volume": 1234.5,
      "bbox_extents": [10.0, 15.0, 5.0],
      "is_manifold": true,
      "is_watertight": true
    }
  },
  "artifacts": {
    "report": "/v1/process/artifacts/sess_abc123/report",
    "script": "/v1/process/artifacts/sess_abc123/script",
    "step": "/v1/process/artifacts/sess_abc123/step",
    "preview": "/v1/process/artifacts/sess_abc123/preview",
    "input": "/v1/process/artifacts/sess_abc123/input"
  },
  "warnings": [
    "Mesh contains some non-manifold edges"
  ],
  "processing_time_seconds": 12.3
}
```

#### POST /v1/process (JSON)

Process a file already on the server.

**Request Body:**
```json
{
  "input_path": "/path/to/existing/file.stl",
  "build": true,
  "sample_count": 5000,
  "include_script": true
}
```

**Response:** Same as multipart form upload, but without `session_id` or `artifacts`.

### Asynchronous Processing

#### POST /v1/jobs

Submit a job for asynchronous processing.

**Request:**
```bash
curl -X POST "http://localhost:8000/v1/jobs" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@part.stl" \
  -F "build=true" \
  -H "Idempotency-Key: unique-request-id"
```

**Response:**
```json
{
  "job_id": "job_def456",
  "status": "queued",
  "submitted_at": "2026-04-27T14:30:00Z",
  "estimated_completion": "2026-04-27T14:30:30Z"
}
```

#### GET /v1/jobs/{job_id}

Get job status and results.

**Response:**
```json
{
  "job_id": "job_def456",
  "status": "completed",
  "submitted_at": "2026-04-27T14:30:00Z",
  "started_at": "2026-04-27T14:30:05Z",
  "completed_at": "2026-04-27T14:30:17Z",
  "result": {
    // Same structure as synchronous response
  },
  "artifacts": {
    "report": "/v1/jobs/job_def456/artifacts/report",
    "script": "/v1/jobs/job_def456/artifacts/script",
    "step": "/v1/jobs/job_def456/artifacts/step",
    "preview": "/v1/jobs/job_def456/artifacts/preview"
  }
}
```

#### POST /v1/jobs/{job_id}/cancel

Cancel a running or queued job.

**Response:**
```json
{
  "job_id": "job_def456",
  "status": "cancelled",
  "cancelled_at": "2026-04-27T14:30:10Z"
}
```

#### POST /v1/jobs/{job_id}/retry

Retry a failed or cancelled job.

**Response:**
```json
{
  "job_id": "job_def456",
  "status": "queued",
  "retry_attempt": 1,
  "submitted_at": "2026-04-27T14:31:00Z"
}
```

#### GET /v1/jobs/{job_id}/events

Server-sent events for real-time job updates.

**Response:**
```
data: {"job_id": "job_def456", "status": "processing", "progress": 0.3}

data: {"job_id": "job_def456", "status": "completed", "progress": 1.0}
```

### Artifact Download

#### GET /v1/process/artifacts/{session_id}/{artifact_type}

Download artifacts from synchronous processing.

**Artifact Types:**
- `report`: JSON report (`report.json`)
- `script`: Generated Python script (`reconstruction.py`)
- `step`: STEP file (`model.step`)
- `preview`: Preview STL (`preview.stl`)
- `input`: Original input file

#### GET /v1/jobs/{job_id}/artifacts/{artifact_type}

Download artifacts from asynchronous processing.

Same artifact types as synchronous processing.

### Legacy Endpoints

The following legacy endpoints are maintained for backward compatibility:

- `POST /process` → `POST /v1/process`
- `POST /process/submit` → `POST /v1/jobs`
- `GET /process/jobs/{id}` → `GET /v1/jobs/{id}`

## Data Models

### DetectionReport

```json
{
  "part_class": "prismatic|rotational|unknown",
  "primitive_kinds": ["plane", "cylinder", "cone", "sphere"],
  "feature_kinds": [
    "base_extrude", "through_hole", "blind_hole", 
    "countersink", "counterbore", "boss", "pocket",
    "revolve_solid"
  ],
  "route": "prismatic|rotational",
  "confidence_scores": {
    "overall": 0.85,
    "primitives": 0.90,
    "features": 0.80
  }
}
```

### ValidationReport

```json
{
  "rms_error": 0.00123,
  "max_error": 0.00456,
  "volume_delta_ratio": 0.0234,
  "bbox_delta_ratio": 0.0123,
  "surface_area_ratio": 0.9876,
  "warnings": ["Mesh has thin walls"],
  "is_valid": true
}
```

### SynthesisResult

```json
{
  "script": "# Generated build123d script\n...",
  "metadata": {
    "volume": 1234.56,
    "surface_area": 890.12,
    "bbox_extents": [10.0, 15.0, 5.0],
    "is_manifold": true,
    "is_watertight": true,
    "has_valid_normals": true
  },
  "step_path": "/path/to/model.step",
  "preview_stl_path": "/path/to/preview.stl",
  "build_time_seconds": 2.3,
  "warnings": []
}
```

## Configuration

### Environment Variables

#### Core Settings
- `MESH2CAD_STATE_DIR`: Directory for uploads and job storage
- `MESH2CAD_JOB_TIMEOUT_SEC`: Job timeout (default: 900)
- `MESH2CAD_MAX_UPLOAD_MB`: Max upload size (default: 100)

#### Rate Limiting
- `MESH2CAD_RATE_LIMIT_PER_MINUTE`: Requests per minute (default: 120)
- `MESH2CAD_RATE_LIMIT_PER_HOUR`: Requests per hour (default: 1000)
- `MESH2CAD_RATE_LIMIT_PER_DAY`: Requests per day (default: 10000)
- `MESH2CAD_RATE_LIMIT_BURST`: Burst limit (default: 10)
- `MESH2CAD_RATE_LIMIT_BACKEND`: `memory` (default) or `redis`
- `MESH2CAD_REDIS_URL`: Redis URL for distributed rate limiting

#### Security
- `MESH2CAD_API_KEYS`: Comma-separated API keys
- `MESH2CAD_WEBHOOK_SECRET`: HMAC secret for webhooks
- `MESH2CAD_CORS_ORIGINS`: Comma-separated allowed origins
- `MESH2CAD_SECURE_COOKIES`: Set to `true` behind HTTPS

#### Performance
- `MESH2CAD_JOB_WORKERS`: Background job workers (default: 2)
- `MESH2CAD_JOB_BACKEND`: `thread` (default) or `rq`
- `MESH2CAD_USE_OPEN3D_METRICS`: Use Open3D for validation
- `MESH2CAD_USE_OPEN3D_CLOUD`: Use Open3D for point clouds

## SDK Examples

### Python

```python
import requests

# Synchronous processing
with open('part.stl', 'rb') as f:
    response = requests.post(
        'http://localhost:8000/v1/process',
        files={'file': f},
        data={'build': True, 'sample_count': 5000},
        headers={'X-API-Key': 'your-key'}
    )
    
result = response.json()
print(f"Detected features: {result['detection_report']['feature_kinds']}")

# Asynchronous processing
job_response = requests.post(
    'http://localhost:8000/v1/jobs',
    files={'file': open('part.stl', 'rb')},
    headers={'X-API-Key': 'your-key', 'Idempotency-Key': 'unique-id'}
)

job_id = job_response.json()['job_id']

# Poll for completion
while True:
    status = requests.get(
        f'http://localhost:8000/v1/jobs/{job_id}',
        headers={'X-API-Key': 'your-key'}
    ).json()
    
    if status['status'] in ['completed', 'failed']:
        break
    
    time.sleep(1)
```

### JavaScript

```javascript
// Synchronous processing
const formData = new FormData();
formData.append('file', fileInput.files[0]);
formData.append('build', 'true');
formData.append('sample_count', '5000');

const response = await fetch('/v1/process', {
  method: 'POST',
  body: formData,
  headers: {
    'X-API-Key': 'your-key'
  }
});

const result = await response.json();
console.log('Features detected:', result.detection_report.feature_kinds);

// Asynchronous processing with events
const jobResponse = await fetch('/v1/jobs', {
  method: 'POST',
  body: formData,
  headers: {
    'X-API-Key': 'your-key',
    'Idempotency-Key': 'unique-id'
  }
});

const { job_id } = await jobResponse.json();

// Server-sent events
const eventSource = new EventSource(`/v1/jobs/${job_id}/events`);

eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Job status:', data.status);
  
  if (data.status === 'completed') {
    // Download results
    window.open(`/v1/jobs/${job_id}/artifacts/step`);
  }
};
```

## Webhooks

Configure webhooks to receive job completion notifications:

```bash
# Set webhook URL
curl -X POST "http://localhost:8000/v1/webhooks" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "url": "https://your-app.com/webhook",
    "events": ["job.completed", "job.failed"],
    "secret": "webhook-secret"
  }'
```

**Webhook Payload:**
```json
{
  "event": "job.completed",
  "job_id": "job_def456",
  "timestamp": "2026-04-27T14:30:17Z",
  "signature": "sha256=abc123...",
  "data": {
    "status": "completed",
    "result": { /* job result */ }
  }
}
```

Verify webhook signature:
```python
import hmac
import hashlib

def verify_webhook(payload: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(f"sha256={expected}", signature)
```

## Troubleshooting

### Common Issues

1. **File upload fails**
   - Check file size limits
   - Verify supported file formats
   - Ensure file is not corrupted

2. **Rate limit exceeded**
   - Check `X-RateLimit-*` headers
   - Implement exponential backoff
   - Consider API key for higher limits

3. **Job processing fails**
   - Check job status for error details
   - Verify input mesh quality
   - Review system resources

4. **CAD generation fails**
   - Ensure build123d is installed
   - Check mesh is manifold
   - Review feature inference results

### Debug Headers

All responses include debug headers:

```
X-Request-ID: req_123456789
X-Processing-Time: 12.345
X-Mesh2CAD-Version: 0.1.0
```

Include the request ID in support requests for faster debugging.

## Performance Optimization

### Client Side

- Use appropriate sample counts (5000-10000 for most parts)
- Enable `auto_tune_sampling` for optimal performance
- Use asynchronous processing for large files
- Implement proper error handling and retries

### Server Side

- Configure Redis for distributed rate limiting
- Use external job queue for high load
- Monitor system resources and job queues
- Implement proper caching and cleanup

## Support

For API support:
- Include request IDs from error responses
- Provide input file samples for reproduction
- Share relevant configuration details
- Check system status at `/health` endpoint
