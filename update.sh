#!/usr/bin/env bash

set -e
set -E

function usage() {
    echo "Usage: $0 [-f file] [-i ip]"
    echo "Example: $0 -f cy-rio-rev2-cyanos-23.5.1b11.swu cy-vp4-cyanos-23.1.1.swu -i 10.192.50.22"
    exit 1
}

while getopts "f:i:" options; do
    case "${options}" in
        f)
            filename=${OPTARG}
            ;;
        i)
            ip=${OPTARG}
            ;;
        h|*)
            usage
            ;;
    esac
done

if test -z "${filename}" || test -z "${ip}"; then
    usage
fi

count=0
delay=20
timeout=300

field="file"
url="http://${ip}:8080/upload"

function wait_device_swupdate_available {
    _ip="${1}"
    _timeout="${2}"
    while (( ${_timeout} > 0 )); do
        curl -m ${2} -s "http://${_ip}:8080" > /dev/null
        if [ $? -eq 0 ]; then
            sleep ${delay}
            return 0
        fi
        _timeout=$((timeout - 1))
        sleep 1
    done
    return 1    
}

function wait_device {
    _ip="${1}"
    _timeout="${2}"
    _logic="${3}"
    while (( ${_timeout} > 0 )); do
        ping -c 1 -W 1 "${_ip}" &> /dev/null
        if [ ${logic} $? -eq 0 ]; then
            sleep ${delay}
            return 0
        fi
        _timeout=$((timeout - 1))
        sleep 1
    done
    return 1

}

function wait_device_boot {
    _ip="${1}"
    _timeout="${2}"
    _logic=""
    wait_device "${_ip}" "${_timeout}" "${_logic}"
}

function wait_device_shutdown {
    _ip="${1}"
    _timeout="${2}"
    _logic="!"
    wait_device "${_ip}" "${_timeout}" "${_logic}"
}

printf "updating ${ip} with ${filename}\n"
printf "Waiting for device...\n"
wait_device_boot "${ip}" ${timeout} || (echo "device not present" && exit 1)
wait_device_swupdate_available "${ip}" ${timeout} || (echo "device not present" && exit 1)
printf "Updating device...\n"
curl -F "${field}=@${filename}" "${url}"
echo "curl output: $?"
printf "Waiting for device to reboot...\n"
wait_device_shutdown "${ip}" ${timeout} || (echo "device not rebooted" && exit 1)
printf "Device rebooted\n"