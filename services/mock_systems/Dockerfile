FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir fastapi==0.115.6 uvicorn[standard]==0.34.0 httpx==0.28.1 python-multipart==0.0.20
COPY Assignment_02_Pack/06_invoice_review_data /app/pack
COPY services/mock_systems /app/services/mock_systems
COPY data/invoice_uploads /app/data/invoice_uploads
ENV INVOICE_UPLOADS_DIR=/app/data/invoice_uploads
WORKDIR /app/pack
EXPOSE 8090
CMD ["python", "/app/services/mock_systems/run_mocks_container.py"]
