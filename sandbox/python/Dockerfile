FROM python:3.12-slim

# Create non-root unprivileged runner user
RUN groupadd -g 65534 nobody_grp || true && \
    useradd -u 65534 -g 65534 -s /bin/false nobody_usr || true

WORKDIR /work

USER 65534:65534

CMD ["python", "/work/main.py"]
