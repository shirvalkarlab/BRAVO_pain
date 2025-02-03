# Default Installation Script was created for Ubuntu 20.04 which is now outdated. This is a new installation script based on Ubuntu 24.04 Distribution

# Set our current working directory as the SCRIPT_DIR
SCRIPT_DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

cd $SCRIPT_DIR
git submodule update --init --recursive

# Install Dependencies with Apt
sudo apt-get update
sudo apt-get install pkg-config python3-pip python3-venv libjpeg-dev libjpeg8-dev libpng-dev nginx python3-virtualenv libmysqlclient-dev mysql-server libffi-dev -y

# Setup Redis Server on Docker for Django Channels
sudo apt-get install lsb-release curl gpg
curl -fsSL https://packages.redis.io/gpg | sudo gpg --dearmor -o /usr/share/keyrings/redis-archive-keyring.gpg
sudo chmod 644 /usr/share/keyrings/redis-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/redis-archive-keyring.gpg] https://packages.redis.io/deb $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/redis.list
sudo apt-get update
sudo apt-get install redis -y

# Create Virutal Environment for Python called "venv"
virtualenv $SCRIPT_DIR/venv
source $SCRIPT_DIR/venv/bin/activate

pip3 install -r requirements.txt

# Setup Script 
python3 manage.py SetupBRAVO
python3 manage.py makemigrations Backend
python3 manage.py migrate

# Build Clients 
sudo apt-get install npm -y
npm install --prefix $SCRIPT_DIR/../Client
npm run build --prefix $SCRIPT_DIR/../Client
python3 $SCRIPT_DIR/manage.py create_template
cp -r $SCRIPT_DIR/../Client/build/* /usr/share/nginx/html/
cp $SCRIPT_DIR/bravo_nginx.conf /etc/nginx/sites-enabled/default

sudo cp bravo_server.service /etc/systemd/system/bravo_server.service
sudo systemctl start bravo_server
sudo systemctl enable bravo_server 
