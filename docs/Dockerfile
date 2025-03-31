FROM python:3.11-slim

# Zainstaluj make i zależności
RUN apt-get update && \
    apt-get install -y build-essential make && \
    pip install sphinx sphinx_rtd_theme && \
    apt-get clean

# Katalog roboczy
WORKDIR /docs

# Domyślna komenda
CMD ["make", "html"]

