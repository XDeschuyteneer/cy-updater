# cy-updater

This tool allows you to update automatically all devices visible on your network

## Installation

```
pip3 install -r requirements.txt
```

## Usage

```
./main.py
```

This will start the tool:
* Discover all devices on your network
* Check OS version
* Download the latest version (SWU file)
* Update the device

## Configuration

### Excluding devices

You can add serial numbers to exclude in do_not_udpate.txt file.
One serial per line.
All these devices will be skipped.

### Version to download

You can specify the version to download in the version.txt file.

Only the first line is used and can contain:
* `stable` : download the latest stable version
* `latest`: download the latest version (stable or beta)
* `X.Y.Z`: download the specified version (example : `22.3.1rc28` ou `22.12.1`)

If you put anything invalid, the latest stable version will be downloaded.