# GitLab to NVFTP Container Transfer

This repository shows a working end-to-end workflow for building a Flask container image in [GitLab](https://gitlab-master.nvidia.com), exporting it as a `.tar.gz`, and uploading that artifact to [NVFTP](https://nvftp.nvidia.com/) over SFTP. The final version uses Docker-based GitLab CI, an existing shared runner, and a dedicated passwordless SSH key for CI uploads.

## What this pipeline does

The pipeline has three stages:

1. Build the Flask container image and push it to GitLab Container Registry.
2. Pull the image back and export it as a compressed `.tar.gz` artifact.
3. Upload the tarball to NVFTP using SFTP with a passwordless SSH key.



## Final setup decisions

A few adjustments were made along the way:

- Switched from Kaniko to Docker-based CI because GitLab documents the original Kaniko project as no longer maintained.
- Used an existing shared runner tagged `type/docker` and `os/linux` so the pipeline could run.
- Confirmed the image repository in GitLab Container Registry after the build completed successfully.
- Stored the SSH private key as a GitLab **File** variable because normal masked variables do not work well for multi-line SSH private keys.
- Used a passwordless CI-only RSA PEM SSH key for NVFTP because the earlier key format was not compatible with the Alpine/OpenSSH environment in GitLab CI.



## Repository contents



### `app.py`

```python
from flask import Flask

app = Flask(__name__)

@app.route("/")
def hello():
    return "Hello from sample GitLab-to-NVFTP container!\n"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
```



### `requirements.txt`

```txt
flask==3.0.3
```



### `Dockerfile`

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
EXPOSE 8080

CMD ["python", "app.py"]
```



## GitLab CI/CD variables

In **Project → Settings → CI/CD → Variables**, create:


| Variable            | Type     | Value                                                               |
| ------------------- | -------- | ------------------------------------------------------------------- |
| `NVFTP_USER`        | Variable | NVFTP-generated SSH username                                        |
| `NVFTP_PRIVATE_KEY` | File     | Full contents of the passwordless private key                       |
| `NVFTP_REMOTE_DIR`  | Variable | Destination directory in NVFTP, for example `/incoming/containers/` |


For `NVFTP_PRIVATE_KEY`, paste the full private key block:

```txt
-----BEGIN OPENSSH PRIVATE KEY-----
...
-----END OPENSSH PRIVATE KEY-----
```

Do not paste only the base64 body, and do not paste the public key that starts with `ssh-ed25519`.

## Runner requirements

The pipeline was run using a shared runner with tags:

- `type/docker`
- `os/linux`.



## `.gitlab-ci.yml`

```yaml
default:
  tags:
    - type/docker
    - os/linux

stages:
  - build
  - export
  - upload

variables:
  IMAGE_TAG: $CI_REGISTRY_IMAGE:$CI_COMMIT_SHORT_SHA
  TAR_NAME: flask-app-$CI_COMMIT_SHORT_SHA.tar.gz

build-image:
  stage: build
  image: docker:24.0.5-cli
  services:
    - docker:24.0.5-dind
  variables:
    DOCKER_HOST: tcp://docker:2376
    DOCKER_TLS_CERTDIR: "/certs"
  before_script:
    - echo "$CI_REGISTRY_PASSWORD" | docker login "$CI_REGISTRY" -u "$CI_REGISTRY_USER" --password-stdin
  script:
    - docker build -t "${IMAGE_TAG}" .
    - docker push "${IMAGE_TAG}"

export-image:
  stage: export
  image: docker:24.0.5-cli
  services:
    - docker:24.0.5-dind
  variables:
    DOCKER_HOST: tcp://docker:2376
    DOCKER_TLS_CERTDIR: "/certs"
  before_script:
    - echo "$CI_REGISTRY_PASSWORD" | docker login "$CI_REGISTRY" -u "$CI_REGISTRY_USER" --password-stdin
  script:
    - docker pull "${IMAGE_TAG}"
    - docker save "${IMAGE_TAG}" | gzip > "${TAR_NAME}"
    - ls -lh "${TAR_NAME}"
  artifacts:
    paths:
      - ${TAR_NAME}
    expire_in: 7 days

upload-to-nvftp:
  stage: upload
  image: alpine:latest
  needs:
    - job: export-image
      artifacts: true
  before_script:
    - apk add --no-cache openssh-client
    - mkdir -p ~/.ssh
    - cp "$NVFTP_PRIVATE_KEY" ~/.ssh/nvftp_key
    - chmod 600 ~/.ssh/nvftp_key
    - head -n 1 ~/.ssh/nvftp_key
    - tail -n 1 ~/.ssh/nvftp_key
    - ssh-keygen -y -f ~/.ssh/nvftp_key >/dev/null
  script:
    - |
      sftp -i ~/.ssh/nvftp_key \
        -o StrictHostKeyChecking=no \
        "${NVFTP_USER}@transfer.nvftp.nvidia.com" <<EOF
      cd ${NVFTP_REMOTE_DIR}
      put ${TAR_NAME}
      bye
      EOF

```

This pipeline builds the image, pushes it to the project registry, exports it as a tarball, and uploads the tarball to NVFTP over SFTP.

## NVFTP key setup

Use a dedicated passwordless SSH key for CI:

```bash
ssh-keygen -t rsa -b 4096 -m PEM -C "micheller@nvidia.com" -f ~/.ssh/nvftp_ci_gitlab -N ""
```

Upload the public key to NVFTP (go to workspace sections > SSH Keys > Add SSH Key ):

```bash
cat ~/.ssh/nvftp_ci_gitlab.pub
```

Store the private key in GitLab as the `NVFTP_PRIVATE_KEY` **File** variable:

```bash
cat ~/.ssh/nvftp_ci_gitlab
```

Grab the SSH username for the SSH Key you just stored from NVFTP. This will be your `NVFTP_USER` variable.

You can verify connectivity locally with:

```bash
sftp -i ~/.ssh/nvftp_ci_gitlab <NVFTP_USER>@transfer.nvftp.nvidia.com
```



## How to verify the workflow



### 1. Verify the image in GitLab

Open **Deploy → Container Registry**. You should see the `nvftp-sync` repository with at least one published tag if the image push succeeded.

### 2. Verify the artifact

After `export-image` completes, the job artifacts should include:

```txt
flask-app-<commit>.tar.gz
```



### 3. Verify the upload in NVFTP

After `upload-to-nvftp` completes, the `.tar.gz` should appear in your target NVFTP directory.

## Running the exported image later

After downloading the tarball from NVFTP:

```bash
gunzip -c flask-app-a1b2c3d.tar.gz | docker load
docker run --rm -p 8080:8080 gitlab-master.nvidia.com:5005/<group>/<project>:a1b2c3d
```

The sample app should then be reachable on port 8080.
```bash 
curl http://localhost:8080
Hello from sample GitLab-to-NVFTP container!
```
## Lessons learned

- A pending GitLab job usually means no eligible runner is attached.
- The Container Registry UI is enough to confirm that the image push succeeded.
- Multi-line SSH private keys should be stored as **File** variables in GitLab.
- If a local key prompts for a passphrase, it is not ideal for non-interactive CI use.
- A passwordless CI-only SSH key is the simplest reliable way to authenticate NVFTP uploads in GitLab CI.

---

