FROM centos:7

RUN yum install -y epel-release
RUN yum install -y python-pip python-devel gcc mardiadb-devel mysql-devel

COPY . /etc/hammers
RUN pip install -r /etc/hammers/requirements.txt

WORKDIR /etc/hammers
RUN python setup.py install
