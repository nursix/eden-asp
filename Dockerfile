FROM python:3.11-slim

# Install make and dependencies
RUN apt-get update && \
    apt-get install -y build-essential make && \
    pip install sphinx sphinx_rtd_theme && \
    apt-get clean

# Working directory
WORKDIR /docs

# Default command
CMD ["make", "html"]

