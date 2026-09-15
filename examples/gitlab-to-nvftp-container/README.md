# Example GitLab-to-NVFTP container

This directory is a self-contained demonstration workload for the outbound synchronization pipeline. It is not part of the synchronization framework and does not prescribe the application layout of an NVIS OVA repository.

The repository defaults point the outbound pipeline at this directory so the foundation project can exercise the complete build, export, and upload path.

NVIS OVA repositories should override:

```text
OUTBOUND_BUILD_CONTEXT=.
OUTBOUND_DOCKERFILE=Dockerfile
OUTBOUND_ARCHIVE_NAME=<repository-name>.tar.gz
```

The example starts a small Flask service on port 8080. After loading the exported image, verify it with:

```bash
docker run --rm -p 8080:8080 <image-tag>
curl http://localhost:8080
```
