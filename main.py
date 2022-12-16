#!/usr/bin/env python3
import socket
import asyncio
import websockets
import json
from threading import Lock, Thread
from urllib.request import urlopen
import requests
import wget
import os
import logging

do_not_update_file = "do_not_update.txt"

devices = {}

FORMAT = '%(asctime)s %(message)s'
logging.basicConfig(format=FORMAT, encoding='utf-8', level=logging.INFO)
logger = logging.getLogger('Cyanview Updater')


async def get_os_version(ip):
    url = f"ws://{ip}/release"
    async with websockets.connect(url) as websocket:
        message = await websocket.recv()
        # parse message as json
        js = json.loads(message)
        return js['os_version'].split(' ')[1]


def get_hw_version(serial):
    sparts = serial.split('-')
    machine = f"{sparts[0]}-{sparts[1]}"
    batch = sparts[2]
    hw = machine if machine == "cy-rcp" else f"{machine}-rev2"
    return hw


def get_latest_version():
    url = "https://s3.eu-west-3.amazonaws.com/cy-binaries.cyanview.com/os/releases.json"
    response = urlopen(url)
    data_json = json.loads(response.read())
    return data_json['OS']['latest']


def do_not_update(serial):
    try:
        with open(do_not_update_file) as f:
            for line in f:
                if line.strip() == serial:
                    return True
    except Exception as e:
        logger.exception(e)
    return False


def download_swu(serial, version):
    hw = get_hw_version(serial)
    print(f"downloading swu: {hw} - {version}")
    url = f"https://s3.eu-west-3.amazonaws.com/cy-binaries.cyanview.com/{version}/{hw}-cyanos-{version}.swu"
    filename = f"swu/{hw}-cyanos-{version}.swu"
    dir = os.path.dirname(filename)
    if not os.path.exists(dir):
        os.makedirs(dir)
    if not os.path.exists(filename):
        wget.download(url, filename)


def upload_swu(serial, ip, version):
    logger.info(f"uploading swu: {serial}")
    hw = get_hw_version(serial)
    filename = f"swu/{hw}-cyanos-{version}.swu"
    url = f'http://{ip}:8080/upload'
    files = {'file': open(filename, 'rb')}
    return requests.post(url, files=files).status_code == 200


def update(serial, ip, version):
    if do_not_update(serial):
        logger.info(f"skipping {serial}")
        return
    new_version = get_latest_version()
    logger.info(f"updating {serial} to {new_version}")

    if serial not in devices:
        devices[serial] = Lock()

    devices[serial].acquire()

    if new_version != version:
        print(f"Updating {serial} from {version} to {new_version}")
        download_swu(serial, new_version)
        upload_swu(serial, ip, new_version)
    else:
        logger.info(f"{serial} is up to date")

    devices[serial].release()


def discovery(port=3838):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        server_address = ('0.0.0.0', port)
        sock.bind(server_address)
        while True:
            serial = ""
            try:
                data, address = sock.recvfrom(4096)
                serial = data.decode('utf-8').split(' ')[1]
                ip, _ = address
                os_version = asyncio.run(get_os_version(ip))
                logger.info(
                    f"serial : {serial}, ip: {ip}, os_version: {os_version}")
                thread = Thread(
                    target=update,
                    args=(serial, ip, os_version))
                thread.start()
            except Exception as e:
                pass
    except Exception as e:
        logger.exception(e)
        sock.close()
    except KeyboardInterrupt:
        logger.info("CTRL+C pressed, exiting")
        sock.close()


def main():
    discovery()


if __name__ == "__main__":
    main()
