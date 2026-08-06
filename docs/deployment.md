# Deployment

Deployment is intentionally delayed until the core indexing engine is useful.

The expected deployment target is AWS EC2 with Docker and Docker Compose.

## Current Position

No deployment infrastructure is included in Phase 1.

## Future Deployment Shape

```text
EC2 Instance
  |
  +-- FastAPI container
  +-- PostgreSQL container or managed PostgreSQL
```

Redis is not part of the deployment unless a concrete cache, queue, or coordination need appears.

S3 is not part of the deployment unless raw HTML snapshots provide measurable debugging, replay, or audit value.

