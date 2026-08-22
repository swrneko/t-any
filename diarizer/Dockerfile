# The only image in this repository that carries model weights machinery.
# Built locally rather than published: torch alone is over two gigabytes, and
# the compose profile that uses it is off by default.
FROM python:3.13-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*

# CPU wheels by default: an image that pulls the CUDA stack is ten gigabytes,
# and most people trying this out have no GPU to spend it on. Rebuild with
# --build-arg TORCH_INDEX=https://download.pytorch.org/whl/cu124 if you do.
ARG TORCH_INDEX=https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir --index-url ${TORCH_INDEX} torch torchaudio

RUN pip install --no-cache-dir \
      "pyannote.audio>=3.1" \
      "fastapi>=0.115" \
      "uvicorn[standard]>=0.32" \
      "python-multipart>=0.0.9"

# Weights land here, so mounting a volume means downloading them once.
ENV HF_HOME=/models
RUN useradd --create-home --uid 1000 app && mkdir -p /models && chown app /models
USER app

WORKDIR /srv
COPY app.py .

EXPOSE 9000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9000"]
