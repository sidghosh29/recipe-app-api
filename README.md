# recipe-app-api

Recipe API Project

# Docker + Docker Compose setup

## 1. `docker-compose build`

A **Docker image** includes a minimal Linux userland (filesystem + tools) and all OS-level dependencies your project needs BUT it is not a full operating system with its own kernel.

The docker-compose build will create a docker image for you.

1. **Compose reads `docker-compose.yml`.**
   - Sees `build: context: .` and `args: - DEV=true`.
2. **Docker engine starts a build** using the Dockerfile found in `.`.
   - Dockerfile contains `ARG DEV=false`. That declares the build arg and a default.
   - Compose passes `DEV=true` which **overrides** the Dockerfile default for this build.
3. **Docker processes Dockerfile instructions in order**, creating one layer [A snapshot of filesystem changes produced by a single Dockerfile instruction (like RUN, COPY, ADD) that Docker can cache and reuse.] per instruction that changes the filesystem or metadata:
   - `FROM ...` → base image layer pulled (if not present locally).
   - `ENV ...`, `ARG ...`, `WORKDIR`, `EXPOSE` → metadata layers.
   - `COPY ./requirements.txt /tmp/requirements.txt` → new filesystem layer; invalidates cache if the file changed.
   - `COPY ./app /app` → copies app into image; invalidates later cache if any file inside `./app` changed.
   - `RUN ...` → executed inside ephemeral build container; produces a new layer with the virtualenv and installed packages.
4. **Conditional build-time logic runs now** (because `ARG` is available during build).
   - Example: `if [ "$DEV" = "true" ]; then pip install -r requirements.dev.txt; fi` runs at build-time only.
5. **When all steps finish** an immutable image is stored locally (tagged by Compose project/service).

---

## 2. What the image contains (post-build)

- OS filesystem (from `python:3.9-alpine3.13` image).
- Python 3.9 installed.
- Virtualenv at `/py` with packages installed (depending on `DEV`).
- `/app` directory containing the code snapshot as it was during build.
- `ENV` and metadata baked into the image.
- Non-root user created (if your Dockerfile adds one).
- The image is immutable — changes on the host after build do **not** affect the image.

---

## 3. `docker-compose up` vs `docker-compose run` vs `docker-compose exec`

- **`docker-compose up`**

  - Creates (or reuses) a container from the image.
  - Starts it with the `command:` defined in compose (overrides image `CMD`).
  - Applies `ports` mapping (host → container).
  - Applies `volumes` (host bind-mounts) at container start time.
  - Streams logs (or runs in detached mode with `-d`).

- **`docker-compose run --rm app <cmd>`**

  - Creates a temporary container (different from the long-running `up` container).
  - Runs `<cmd>` and then removes the container (`--rm`).
  - Useful for one-off tasks (migrations, lint, tests).

- **`docker-compose exec app <cmd>`**
  - Executes `<cmd>` **inside an already running** container created by `up`.
  - Does NOT create a new container.

---

## 4. Bind mount `volumes: - ./app:/app` (critical behavior)

- At container **runtime**, Docker bind-mounts `./app` from the host over `/app` inside the container.
- **This hides whatever was copied to `/app` during image build.**
  - If the host `./app` is empty, it shadows the image `/app`.
  - If you created files inside a container while the mount was present, they persist to the host.
- Consequence: For development, the bind mount gives live code changes inside the container. For production, you normally **do not** use bind mounts and rely on the image's snapshot.

---

## 5. `ARG` vs `ENV` vs runtime environment variables

- **`ARG`** (e.g., `ARG DEV=false`):
  - **Build-time only.**
  - Used to change image build behavior (conditional `RUN`, substitutions).
  - Not available at container run time (unless you also pass or set an `ENV`).
- **`ENV`** (e.g., `ENV PATH="/py/bin:$PATH"`):
  - Persisted into the final image.
  - Available at run-time in any container created from that image.
- If you need a variable available at runtime, set it with `environment:` in `docker-compose.yml` or `ENV` in Dockerfile.

---

## 6. PATH / virtualenv behavior in your Dockerfile

- You created a venv at `/py` and then:
  - `ENV PATH="/py/bin:$PATH"` → makes venv executables (python, pip) first in PATH at runtime.
- This means running `python` or `pip` inside the container uses the venv installed binaries.

---

## 7. User & file permission implications

- `adduser ... django-user` + `USER django-user`:
  - Runs processes as non-root inside the container (good practice).
  - **Bind-mounted files keep host uid/gid**, so the container user may not own them — can cause permission errors when writing files.
  - Solutions:
    - Chown host files to match container uid.
    - Create container user with same uid as host user.
    - Use entrypoint script to adjust permissions at container start.

---

## 8. Networking basics in Compose

- Services are attached to a default network created by Compose.
- Services can reach each other by service name (e.g., `postgres:5432`).
- `ports` expose container ports to the host; they do not change inter-service connectivity.

---

## 9. Image & layer caching — practical notes

- Docker caches layers. Cache invalidation happens when inputs to an instruction change (e.g., files copied).
- **Best practice to maximize cache reuse**:
  1. `COPY requirements.txt /tmp/requirements.txt`
  2. `RUN pip install -r /tmp/requirements.txt`
  3. `COPY ./app /app`
- This way, editing code in `./app` doesn't force re-running `pip install`.
- Use `.dockerignore` to reduce context size and avoid unnecessary cache busting (exclude `.git`, `node_modules`, local venv, large artifacts).

---

## 10. What your commands actually did (in your sequence)

1. `docker-compose build`

   - Built the image using `DEV=true` (Compose arg override).
   - Installed dev dependencies at build-time because the `RUN` conditional saw `DEV=true`.

2. `docker-compose run --rm app sh -c "flake8"`

   - Started a temporary container and ran `flake8`.
   - Because of `volumes: - ./app:/app`, flake8 linted the host files in `./app`.

3. `docker-compose run --rm app sh -c "django-admin startproject app ."`

   - Created Django project files inside the temporary container; they appeared on host due to bind mount.

4. `docker-compose up`
   - Started long-running container running `python manage.py runserver 0.0.0.0:8000`.
   - Accessible at `http://localhost:8000` because of `ports: - "8000:8000"`.

---

## 11. Common gotchas & recommendations (concise)

- **Gotcha — bind mount hides image content.**
  - If you expect pre-copied files from image to be present, they may be shadowed by an empty host directory.
- **Recommendation — optimize Dockerfile layer ordering:**
  - Copy requirements & install first, then copy app sources.
  - Use `/py/bin/pip install --no-cache-dir -r /tmp/requirements.txt` to reduce image layer size.
- **Use `.dockerignore`** to exclude unnecessary files from build context.
- **Alpine caveat:** `python:3.9-alpine` uses musl libc and may require build deps for certain wheels. If you see build errors, consider `python:3.9-slim`.
- **Use an entrypoint script** for pre-start tasks (migrations, waiting for DB).
- **Migrations & one-offs:** prefer `docker-compose run --rm app python manage.py migrate` or `exec` into a running container.

---

## 12. Example optimized Dockerfile (development-oriented)

```Dockerfile
# Use an explicit base
FROM python:3.9-slim

LABEL maintainer="Siddharth Ghosh"
ENV PYTHONUNBUFFERED=1
ARG DEV=false

# Create working dir early
WORKDIR /app

# Install system deps (if any) - keep minimal for layer caching
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements first to leverage cache
COPY requirements.txt /tmp/requirements.txt
COPY requirements.dev.txt /tmp/requirements.dev.txt

# Create virtualenv and install requirements
RUN python -m venv /py \
    && /py/bin/pip install --upgrade pip \
    && /py/bin/pip install --no-cache-dir -r /tmp/requirements.txt \
    && if [ "$DEV" = "true" ]; then /py/bin/pip install --no-cache-dir -r /tmp/requirements.dev.txt; fi \
    && rm -rf /tmp

ENV PATH="/py/bin:$PATH"

# Copy source after installing deps
COPY ./app /app

# Security: non-root user
RUN adduser --disabled-password --gecos "" django-user \
    && chown -R django-user:django-user /app
USER django-user

EXPOSE 8000
CMD ["sh", "-c", "python manage.py runserver 0.0.0.0:8000"]

```
