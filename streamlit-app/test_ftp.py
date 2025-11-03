from ftplib import FTP
from datetime import datetime

# Configuración del servidor FTP
FTP_HOST = '127.0.0.1'       # o la IP de tu host si estás en otra máquina
FTP_PORT = 21
FTP_USER = 'myuser'
FTP_PASS = 'mypassword'

# Ruta del archivo a subir
LOCAL_IMAGE_PATH = 'images/1.jpg'
REMOTE_FILENAME = '1.jpg'

# Crear conexión
print(datetime.now())
ftp = FTP()
ftp.connect(FTP_HOST, FTP_PORT)
ftp.login(FTP_USER, FTP_PASS)
print(datetime.now())

# Subir archivo
with open(LOCAL_IMAGE_PATH, 'rb') as file:
    ftp.storbinary(f'STOR {REMOTE_FILENAME}', file)

print("✅ Imagen subida con éxito.")

# Cerrar conexión
ftp.quit()
