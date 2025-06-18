# pip install qrcode[pil]
import json
import zlib
import qrcode
from qreader import QReader
import cv2


def decode_and_decompress(encoded_data):
    # Decode base64 and decompress the data
    compressed_data = bytes.fromhex(encoded_data)
    json_str = zlib.decompress(compressed_data).decode('utf-8')

    # Convert the JSON string back to a Python object
    decoded_data = json.loads(json_str)

    return decoded_data


def read_qrcode(img_path):
    # Create a QReader instance
    qreader = QReader()

    # Get the image that contains the QR code
    image = cv2.cvtColor(cv2.imread(img_path), cv2.COLOR_BGR2RGB)

    # Use the detect_and_decode function to get the decoded QR data
    decoded_text = qreader.detect_and_decode(image=image)

    return decoded_text


if __name__ == "__main__":
    # Leemos el QR generado
    # qr_string = read_qrcode('qrcode.png')
    qr_string = read_qrcode('IMG_20250521_185356657.jpg')
    print('QR Leido: '+ qr_string[0])
    decoded_string = decode_and_decompress(qr_string[0])
    print("QR Decodificado:", decoded_string)