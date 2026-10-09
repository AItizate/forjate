FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN useradd --create-home --uid 1000 app
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY prompts ./prompts
RUN pip install --no-cache-dir .
USER app
# The Job or Deployment sets the command: ["python", "-m", "support_copilot.<module>"]
CMD ["python", "-c", "print('set a command: python -m support_copilot.<api|orders_stub|seed|replay|verify>')"]
