FROM python:3.10

WORKDIR /bot

COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt

COPY . .

CMD ["python", "-u", "main.py"]

