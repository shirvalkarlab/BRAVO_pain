del -r C:\\Github\\BRAVO\\BRAVO\\static
python BRAVO\\manage.py make_staticfile

pyinstaller .\\BRAVO.spec --noconfirm

robocopy C:\\Github\\BRAVO\\Client\\build\\static C:\\Github\\BRAVO\\BRAVO\\static /E
copy .\\BRAVO\\.env .\\dist\\BRAVO\\_internal
