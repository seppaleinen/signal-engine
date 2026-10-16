# Signal Engine Docker image
# Usage:
#   docker build -t signal-engine .
#   docker run --rm \
#     -v $(pwd)/data:/app/data \
#     -v $(pwd)/digests:/app/digests \
#     -e LITELLM_BASE_URL=... \
#     -e LITELLM_API_KEY=... \
#     signal-engine --run

FROM python:3.13-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /uv
ENV PATH="/uv:$PATH"

WORKDIR /app

# Copy project files
COPY pyproject.toml uv.lock .python-version ./
COPY src/ ./src/
COPY PROFILE.md ./
COPY README.md ./

# Install dependencies and the signal-engine package itself
RUN /uv venv && \
    /uv pip install --system httpx python-dotenv && \
    /uv pip install --system -e .

# Create data and digests directories
RUN mkdir -p /app/data /app/digests

# Default command: run the engine
ENTRYPOINT ["/uv", "run", "signal-engine"]