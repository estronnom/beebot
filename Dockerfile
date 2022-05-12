FROM python

WORKDIR /dockerbeebot

COPY requirements.txt requirements.txt

RUN pip3 install -r requirements.txt

COPY . .

RUN echo "Europe/Moscow" > /etc/timezone

RUN dpkg-reconfigure -f noninteractive tzdata

CMD ["python", "synchandler.py"]