FROM apache/airflow:3.3.1-python3.12

COPY requirements-docker.txt /requirements-docker.txt

RUN pip install --no-cache-dir \
    "apache-airflow==3.3.1" \
    -r /requirements-docker.txt
