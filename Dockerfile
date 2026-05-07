FROM mcr.microsoft.com/playwright/python:v1.50.0-noble

WORKDIR /var/task

COPY pyproject.toml .
COPY src/ src/

# awslambdaric provides the Lambda runtime interface; playwright + chromium already in base image
RUN pip install --no-cache-dir awslambdaric boto3 httpx pydantic zipcodes click "playwright==1.50.0"

ENV PYTHONPATH=/var/task/src

ENTRYPOINT ["python", "-m", "awslambdaric"]
CMD ["deal_dash.lambdas.scrapers.rebel_savings.handler"]
