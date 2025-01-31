# Set our current working directory as the SCRIPT_DIR
SCRIPT_DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

git pull
git submodule update --recursive

source $SCRIPT_DIR/venv/bin/activate
python3 manage.py migrate

sudo systemctl reload nginx
sudo systemctl restart bravo_server