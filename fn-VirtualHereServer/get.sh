#!/usr/bin/env bash
#
# Copyright (C) 2022 Ing <https://github.com/wjz304>
#
# This is free software, licensed under the MIT License.
# See /LICENSE for more information.
#

ARCH=$(uname -m)
WORKDIR="$(
  cd "$(dirname "$0")"
  pwd
)"
#
rm -rf "${WORKDIR}/app/server"
mkdir -p "${WORKDIR}/app/server" >/dev/null 2>&1 || true
for a in i386 x86_64 arm arm64 mips mipsel riscv64; do
  curl -skL "https://www.virtualhere.com/sites/default/files/usbserver/vhusbd${a}" -o "${WORKDIR}/app/server/vhusbd${a}"
  [ $? -ne 0 ] && {
    echo "ERROR: Failed to download vhusbd${a}"
    exit 1
  }
done

V=$("${WORKDIR}/app/server/vhusbd${ARCH}" -h | head -n1 | awk '{print $2}' | sed 's/v//')
echo "VirtualHere Server version: ${V}"
sed -i "s/^\(version.*= \).*$/\1${V}/" "${WORKDIR}/manifest"
echo "Done"
