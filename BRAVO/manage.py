#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys
from pathlib import Path

def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'BRAVO.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


def processInput(argv):
    if len(argv) > 1:
        if argv[1] == "create_template":
            # Build paths inside the project like this: BASE_DIR / 'subdir'.
            BASE_DIR = Path(__file__).resolve().parent
            with open(BASE_DIR / "Server/templates/index.html", "w+") as fileout:
                with open(BASE_DIR / "../Client/build/index.html", "r+") as filein:
                    for line in filein:
                        fileout.write(line.replace('</head><body>', '</head>{% csrf_token %}<body>'))

            return True

if __name__ == '__main__':
    if not processInput(sys.argv):
        main()
