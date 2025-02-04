#!/bin/bash
git pull

python3 manage.py migrate

# Build Clients 
npm install --prefix $SCRIPT_DIR/../Client
npm run build --prefix $SCRIPT_DIR/../Client
python3 $SCRIPT_DIR/manage.py create_template
rm -r /usr/share/nginx/html/*
cp -r $SCRIPT_DIR/../Client/build/* /usr/share/nginx/html/
cp $SCRIPT_DIR/bravo_nginx.conf /etc/nginx/sites-enabled/default

sudo systemctl restart bravo_server 