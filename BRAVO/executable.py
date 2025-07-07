import os
from django.core.management import execute_from_command_line
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'BRAVO.settings')

from waitress import serve
    
from BRAVO.wsgi import application

if __name__ == "__main__":
    execute_from_command_line(["manage.py", "migrate"])
    serve(application, port='80')
    