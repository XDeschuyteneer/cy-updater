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
import re
import click
import datetime
import flask
import flask.cli
import subprocess
import shlex

do_not_update_file = "do_not_update.txt"
version_file = "version.txt"

app = flask.Flask(__name__)

devices = {}

FORMAT = '%(asctime)s %(message)s'
logger = logging.getLogger('cy-updater')


def get_os_version(ip):
    cmd = f"curl http://{ip}:8080/version.html"
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=True)
    stdout, stderr = process.communicate()
    version = stdout.decode("utf-8").split("</br>")[7].split(" ")[5]
    return version

def get_hw_version(serial):
    _, machine, batch, sid = serial.split('-')
    match machine:
        case "rcp":
            return "cy-rcp"
        case "nio":
            if batch == "22" and int(sid) <= 50:
                return "cy-nio"
            else:
                return "cy-nio-rev2"
        case "rio":
            if batch == "15" and int(sid) <= 50:
                return "cy-rio"
            else:
                return "cy-rio-rev2"
        case "vp4":
            return "cy-vp4"


def is_handled(serial):
    try:
        hw = get_hw_version(serial)
        return True
    except Exception as e:
        return False


def get_latest_version():
    url = "https://s3.eu-west-3.amazonaws.com/cy-binaries.cyanview.com/os/releases.json"
    response = urlopen(url)
    data_json = json.loads(response.read())
    v_latest = data_json['OS']['latest']
    v_stable = data_json['OS']['stable']
    try:
        with open(version_file) as f:
            v_type = f.readline().strip()
            match v_type:
                case "latest":
                    return v_latest
                case "stable":
                    return v_stable
                case other if re.match(r"\d+\.\d+\.\d+\S", other):
                    return v_type
                case _:
                    return v_latest
    except Exception as e:
        return v_latest


def get_device_info(socket):
    data, (ip, _) = socket.recvfrom(4096)
    serial = data.decode('utf-8').split(' ')[1]
    os_version = get_os_version(ip)
    return serial, ip, os_version


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
    logger.debug(f"downloading swu: {hw} - {version}")
    url = f"https://s3.eu-west-3.amazonaws.com/cy-binaries.cyanview.com/{version}/{hw}-cyanos-{version}.swu"
    filename = f"swu/{hw}-cyanos-{version}.swu"
    dir = os.path.dirname(filename)
    if not os.path.exists(dir):
        os.makedirs(dir)
    if not os.path.exists(filename):
        wget.download(url, filename)

def upload_file(filename, url, field):
    cmd = f"curl -F '{field}=@{filename}' '{url}'"
    process = subprocess.Popen(
        shlex.split(cmd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    return stdout, stderr

def upload_swu(serial, ip, version):
    logger.debug(f"uploading swu: {serial}")
    if not is_handled(serial):
        return False
    hw = get_hw_version(serial)
    filename = f"swu/{hw}-cyanos-{version}.swu"
    url = f'http://{ip}:8080/upload'
    upload_file(filename, url, 'file')

def update(serial, ip, version):
    if do_not_update(serial):
        logger.debug(f"skipping {serial}")
        return
    new_version = get_latest_version()
    logger.debug(f"updating {serial} to {new_version}")

    devices[serial]["lock"].acquire()

    if new_version != version:
        logger.debug(f"Updating {serial} from {version} to {new_version}")
        download_swu(serial, new_version)
        upload_swu(serial, ip, new_version)
    else:
        logger.debug(f"{serial} is up to date")

    devices[serial]["lock"].release()


def create_lock(serial):
    if serial not in devices:
        devices[serial] = {}
        devices[serial]["lock"] = Lock()


def update_device_info(serial, ip, os_version):
    if not is_handled(serial):
        return False
    create_lock(serial)
    devices[serial]["last_seen"] = datetime.datetime.now()
    devices[serial]["ip"] = ip
    devices[serial]["os_version"] = os_version


def print_devices():
    logger.info("-"*20)
    latest_version = get_latest_version()
    for serial, device in devices.items():
        now = datetime.datetime.now()
        if (now - device["last_seen"]).seconds < 60:
            if device["os_version"] != latest_version:
                txt = f"{serial} | {device['os_version']} => UPDATING"
            else:
                txt = f"{serial} | {device['os_version']} => OK"
            logger.info(txt)


@app.after_request
def add_header(r):
    r.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, public, max-age=0"
    r.headers["Pragma"] = "no-cache"
    r.headers["Expires"] = "0"
    return r


@app.route('/')
def index():
    global devices
    latest_version = get_latest_version()
    return flask.render_template(
        'index.html',
        devices=devices,
        latest_version=latest_version,
        now=datetime.datetime.now(),
    )


def discovery(port=3838):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        server_address = ('0.0.0.0', port)
        sock.bind(server_address)
        while True:
            try:
                serial, ip, os_version = get_device_info(sock)
                if is_handled(serial):
                    update_device_info(serial, ip, os_version)
                    print_devices()
                    thread = Thread(
                        target=update,
                        args=(serial, ip, os_version))
                    thread.start()
            except ValueError as e:
                pass
            except Exception as e:
                logger.exception(e)
    except Exception as e:
        logger.exception(e)
        sock.close()
    except KeyboardInterrupt:
        logger.debug("CTRL+C pressed, exiting")
        sock.close()


@click.command()
@click.option('--debug', is_flag=True, default=False, help='Enable debug mode')
@click.option('--port', default=8080, help='Set web server port')
def main(debug, port):
    flask.cli.show_server_banner = lambda *args: None
    app.logger.disabled = True
    for l in ("asyncio", "websockets.client", "werkzeug"):
        logging.getLogger(l).setLevel(logging.ERROR)
        logging.getLogger(l).disabled = True
    if debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    logger.info(f"Starting web server on port {port}")
    logger.info(f"Check status at http://localhost:{port}")
    t = Thread(target=app.run, kwargs={
        'host': '0.0.0.0', 'port': port, 'threaded': True})
    t.daemon = True
    t.start()
    discovery()


if __name__ == "__main__":
    main()
