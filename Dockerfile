FROM python:3.8

COPY . /app
WORKDIR /app

RUN chmod +x start.sh

EXPOSE 8000

RUN pip install pipenv
RUN pipenv install --system --deploy

CMD ["./start.sh"]
