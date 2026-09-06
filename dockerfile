FROM node:22-bookworm AS client-build

WORKDIR /usr/src/Client
COPY ./Client/package.json ./Client/package-lock.json ./
RUN npm ci
COPY ./Client .
RUN npm run build

FROM ubuntu/nginx:1.24-24.04_beta AS server-deps

ENV DATASERVER_PATH=/usr/src/BRAVO/BRAVOStorage/

WORKDIR /usr/src/BRAVO
RUN mkdir -p BRAVOStorage /static

RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install --no-install-recommends -y \
        build-essential \
        pkg-config \
        python3 \
        python3-dev \
        python3-pip \
        libjpeg-dev \
        libjpeg8-dev \
        libpng-dev \
        libmysqlclient-dev && \
    rm -rf /var/lib/apt/lists/*

COPY ./BRAVO/requirements.txt ./requirements.txt
RUN pip3 install -r requirements.txt --break-system-packages

# Prasad's mixed-effects validation uses embedded R; keep it in the appliance.
# Install after the existing Python stack so Debian's numpy does not replace it.
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install --no-install-recommends -y \
        python3-rpy2 r-cran-lme4 r-cran-lmertest r-cran-emmeans && \
    rm -rf /var/lib/apt/lists/* && \
    pip3 install --break-system-packages --no-deps pymer4==0.8.2 seaborn==0.13.2

FROM server-deps AS server

COPY ./BRAVO .
COPY ./BRAVO/bravo_nginx.conf /etc/nginx/sites-enabled/default
COPY --from=client-build /usr/src/Client/build /usr/src/Client/build
RUN python3 manage.py create_template
COPY --from=client-build /usr/src/Client/build /usr/share/nginx/html

EXPOSE 80
EXPOSE 27286
