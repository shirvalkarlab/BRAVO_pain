del -r C:\\Github\\BRAVO\\BRAVO\\static
python BRAVO\\manage.py make_staticfile

robocopy C:\\Github\\BRAVO\\Client\\build\\static C:\\Github\\BRAVO\\BRAVO\\static /E
pyinstaller .\\BRAVO.spec --noconfirm
copy .\\BRAVO\\.env.production .\\dist\\BRAVO\\_internal\\.env

robocopy .\\dist\\BRAVO\\ .\\dist\\BRAVO_Production\\ /E
copy .\\BRAVO\\.env .\\dist\\BRAVO_Production\\_internal\\.env
copy .\\BRAVO\\mysql.config .\\dist\\BRAVO_Production\\_internal\\mysql.config
