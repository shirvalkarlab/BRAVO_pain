#/bin/bash
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
$SCRIPT_DIR/PythonEnv/bin/python3 $SCRIPT_DIR/manage.py runserver 0:27286
