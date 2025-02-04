#!/bin/bash
git pull

SCRIPT_DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

cd $SCRIPT_DIR
source $SCRIPT_DIR/venv/bin/activate
python3 manage.py migrate

# Build Clients 
npm install --prefix $SCRIPT_DIR/../Client
npm run build --prefix $SCRIPT_DIR/../Client
python3 $SCRIPT_DIR/manage.py create_template
rm -r /usr/share/nginx/html/*
sudo cp -r $SCRIPT_DIR/../Client/build/* /usr/share/nginx/html/

sudo systemctl restart bravo_server 