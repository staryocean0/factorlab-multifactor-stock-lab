FROM python:3.11-slim-bookworm@sha256:528257d48c1da0dcecc2e725d1ae34498d60c965f1241e39cd6a85a8859bdf84
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
RUN pip install --no-cache-dir torch==2.11.0+cpu --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt /runtime-requirements.txt
RUN pip install --no-cache-dir -r /runtime-requirements.txt
COPY run_in_container.py /run_in_container.py
WORKDIR /work
ENTRYPOINT ["python", "/run_in_container.py"]
