FROM ubuntu/nginx:1.24-24.04_beta

ENV DATASERVER_PATH=/usr/src/BRAVO/BRAVOStorage/

WORKDIR /usr/src/BRAVO
COPY ./Client/build /usr/share/nginx/html
COPY ./BRAVO/bravo_nginx.conf /etc/nginx/sites-enabled/default

COPY ./BRAVO .

RUN mkdir -p BRAVOStorage && \ 
    apt-get update && \
    apt-get install pkg-config python3 python3-pip libjpeg-dev libjpeg8-dev libpng-dev libmysqlclient-dev -y && \
    pip3 install -r requirements.txt --break-system-packages

EXPOSE 80
EXPOSE 27286
