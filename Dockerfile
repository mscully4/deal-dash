FROM mcr.microsoft.com/playwright/python:v1.50.0-noble

WORKDIR /var/task

COPY pyproject.toml .
COPY requirements.txt .
COPY src/ src/

RUN pip install --no-cache-dir awslambdaric -r requirements.txt

ENV PYTHONPATH=/var/task/src

ENTRYPOINT ["python", "-m", "awslambdaric"]
CMD ["deal_dash.lambdas.scrapers.rebel_savings.handler"]
