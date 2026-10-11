FROM cloudlab-api:1.0
USER root
WORKDIR /workspace
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_ROOT_USER_ACTION=ignore
COPY tests/requirements.txt /tmp/test-requirements.txt
RUN pip install --no-cache-dir -r /tmp/test-requirements.txt && chown 10001 /workspace
COPY pytest.ini ./
COPY tests/ tests/
COPY src/ src/
COPY scripts/ scripts/
USER 10001
CMD ["pytest", "-q"]
