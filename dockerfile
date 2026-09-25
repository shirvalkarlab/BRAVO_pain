FROM ubuntu/nginx:1.24-24.04_beta

ENV DATASERVER_PATH=/usr/src/BRAVO/BRAVOStorage/

WORKDIR /usr/src/BRAVO
COPY ./Client/build /usr/share/nginx/html
COPY ./BRAVO/bravo_nginx.conf /etc/nginx/sites-enabled/default

COPY ./BRAVO .

# R and the three R packages the mixed-effects fits need (pymer4/rpy2's `glmer`, the heat maps'
# stability test): read off the running server container 2026-09-25 (pending item P-17 --
# rebuilding this image before now would have shipped no R at all, silently losing those
# fits). rpy2 itself comes from the apt package, not pip: `requirements.txt` explains why
# (the PyPI sdist fails to link its C extension in this image). Versions pinned to what is
# live; if the exact build has aged out of the Ubuntu 24.04 (noble) archive, install the
# closest available version and update this comment and requirements.txt's dated note.
RUN mkdir -p BRAVOStorage && \
    apt-get update && \
    apt-get install pkg-config python3 python3-pip libjpeg-dev libjpeg8-dev libpng-dev libmysqlclient-dev \
        r-base-core=4.3.3-2build2 \
        r-cran-lme4=1.1-35.1-4 \
        r-cran-lmertest=3.1-3-2 \
        r-cran-emmeans=1.10.0+dfsg-1 \
        python3-rpy2=3.5.15-1 \
        -y && \
    pip3 install -r requirements.txt --break-system-packages

EXPOSE 80
EXPOSE 27286
