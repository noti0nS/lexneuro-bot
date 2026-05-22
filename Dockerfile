FROM python:3.13-slim

ARG DEBIAN_FRONTEND=noninteractive

WORKDIR /app

COPY pyproject.toml uv.lock .
RUN apt-get update && apt-get install -y wget \
    && wget https://github.com/jgm/pandoc/releases/download/3.2.1/pandoc-3.2.1-1-amd64.deb \
    && dpkg -i pandoc-3.2.1-1-amd64.deb && rm pandoc-3.2.1-1-amd64.deb \
    && apt-get purge -y wget && apt-get autoremove -y && apt-get clean
RUN apt-get update && apt-get install -y \
    texlive-xetex texlive-latex-recommended texlive-fonts-recommended \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv \
    && uv export --no-dev --no-hashes --format requirements.txt -o requirements.txt \
    && pip install --no-cache-dir -r requirements.txt \
    && pip uninstall uv -y

COPY main.py .
COPY src/ src/

CMD ["python", "main.py"]
