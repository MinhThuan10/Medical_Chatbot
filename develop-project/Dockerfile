
FROM python:3.12


WORKDIR /app


COPY ./requirements.txt /code/requirements.txt

RUN pip install torch torchvision --index-url https://download.pytorch.org/whl/cu126

RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

COPY ./app /app/app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]