del -r C:\\Github\\BRAVO\\BRAVO\\static
python BRAVO\\manage.py make_staticfile

robocopy C:\\Github\\BRAVO\\Client\\build\\static C:\\Github\\BRAVO\\BRAVO\\static /E
pyinstaller .\\BRAVO.spec --noconfirm
copy .\\BRAVO\\.env.production .\\dist\\BRAVO\\_internal\\.env
