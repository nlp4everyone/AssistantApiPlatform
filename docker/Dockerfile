FROM python:3.9-slim

# Set workdir
WORKDIR /workspace

# Install uv
RUN pip install uv

RUN apt-get update && apt-get install -y \
      gcc \
      libpq-dev \
      curl \
      git

# Copy pyproject.toml and install dependencies
COPY pyproject.toml .
# Install dependencies with uv
RUN uv pip compile pyproject.toml --output-file requirements.txt
RUN uv pip install --system -r requirements.txt

# Copy the rest
COPY . /workspace

EXPOSE 8005