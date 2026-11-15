FROM python:3.12-slim
RUN useradd --create-home --uid 1000 app
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .
USER app
CMD ["python", "-c", "print('set a command: python -m parcel_claims.<module>')"]
