
FROM python:3.12


WORKDIR /code


COPY ./requirements.txt /code/requirements.txt

RUN pip install torch torchvision --index-url https://download.pytorch.org/whl/cu126

RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt


COPY ./app /code/app

COPY .env .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]