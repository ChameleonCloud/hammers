FROM python:3

COPY requirements.txt /etc/hammers/requirements.txt
RUN pip install -r /etc/hammers/requirements.txt

COPY . /etc/hammers
WORKDIR /etc/hammers

RUN python setup.py install
