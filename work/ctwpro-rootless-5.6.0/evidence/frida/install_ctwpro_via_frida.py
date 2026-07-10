#!/Users/zest/.pyenv/versions/3.10.6/bin/python
"""Upload and install the CTW Pro deep-patch deb through the root ctwsrv process."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import frida


DEFAULT_DEB = Path(
    "/Users/zest/myworks/apt-ios-patch/patched/"
    "CTW_Pro企业级(无根版)_5.6.0-2_"
    "com.xxdevice.CTWPro.Rootless560_deep_nolicense_ustar.deb"
)
REMOTE_DEB = "/var/mobile/CTWPro.Rootless560_5.6.0-2.deb"
REMOTE_HASH_LOG = "/var/mobile/CTWPro.Rootless560_5.6.0-2.sha256.log"
REMOTE_INSTALL_LOG = "/var/mobile/CTWPro.Rootless560_5.6.0-2.install.log"
REMOTE_QUERY_LOG = "/var/mobile/CTWPro.Rootless560_5.6.0-2.query.log"


JAVASCRIPT = r"""
'use strict';

function address(name) {
  return Module.getGlobalExportByName(name);
}

const openFile = new NativeFunction(address('open'), 'int', ['pointer', 'int', 'int']);
const closeFile = new NativeFunction(address('close'), 'int', ['int']);
const writeFile = new NativeFunction(address('write'), 'long', ['int', 'pointer', 'ulong']);
const readFile = new NativeFunction(address('read'), 'long', ['int', 'pointer', 'ulong']);
const unlinkFile = new NativeFunction(address('unlink'), 'int', ['pointer']);
const getuid = new NativeFunction(address('getuid'), 'uint', []);
const geteuid = new NativeFunction(address('geteuid'), 'uint', []);
const spawn = new NativeFunction(
  address('posix_spawn'),
  'int',
  ['pointer', 'pointer', 'pointer', 'pointer', 'pointer', 'pointer']
);
const actionsInit = new NativeFunction(
  address('posix_spawn_file_actions_init'), 'int', ['pointer']
);
const actionsAddOpen = new NativeFunction(
  address('posix_spawn_file_actions_addopen'),
  'int',
  ['pointer', 'int', 'pointer', 'int', 'int']
);
const actionsAddDup2 = new NativeFunction(
  address('posix_spawn_file_actions_adddup2'),
  'int',
  ['pointer', 'int', 'int']
);
const actionsDestroy = new NativeFunction(
  address('posix_spawn_file_actions_destroy'), 'int', ['pointer']
);
const waitpid = new NativeFunction(address('waitpid'), 'int', ['int', 'pointer', 'int']);
const nsGetEnviron = new NativeFunction(address('_NSGetEnviron'), 'pointer', []);
const setenv = new NativeFunction(address('setenv'), 'int', ['pointer', 'pointer', 'int']);

const O_RDONLY = 0;
const O_WRONLY = 1;
const O_CREAT = 0x200;
const O_TRUNC = 0x400;
let uploadFd = -1;

function cString(value) {
  return Memory.allocUtf8String(value);
}

function pointerArray(values) {
  const strings = values.map(value => cString(value));
  const array = Memory.alloc((values.length + 1) * Process.pointerSize);
  strings.forEach((value, index) => {
    array.add(index * Process.pointerSize).writePointer(value);
  });
  array.add(values.length * Process.pointerSize).writePointer(ptr(0));
  return { array: array, strings: strings };
}

function spawnProcess(path, args, logPath, shouldWait) {
  const bootstrapPath = [
    '/var/jb/usr/local/sbin',
    '/var/jb/usr/local/bin',
    '/var/jb/usr/sbin',
    '/var/jb/usr/bin',
    '/var/jb/sbin',
    '/var/jb/bin',
    '/usr/sbin',
    '/usr/bin',
    '/sbin',
    '/bin'
  ].join(':');
  if (setenv(cString('PATH'), cString(bootstrapPath), 1) !== 0) {
    throw new Error('setenv PATH failed');
  }

  const actions = Memory.alloc(Process.pointerSize);
  actions.writePointer(ptr(0));
  let result = actionsInit(actions);
  if (result !== 0) throw new Error('posix_spawn_file_actions_init=' + result);
  try {
    result = actionsAddOpen(
      actions,
      1,
      cString(logPath),
      O_WRONLY | O_CREAT | O_TRUNC,
      420
    );
    if (result !== 0) throw new Error('posix_spawn_file_actions_addopen=' + result);
    result = actionsAddDup2(actions, 1, 2);
    if (result !== 0) throw new Error('posix_spawn_file_actions_adddup2=' + result);

    const pidPointer = Memory.alloc(4);
    const executablePath = cString(path);
    const argv = pointerArray(args);
    const environment = nsGetEnviron().readPointer();
    result = spawn(
      pidPointer,
      executablePath,
      actions,
      ptr(0),
      argv.array,
      environment
    );
    if (result !== 0) return { result: result, pid: -1, status: null };
    const pid = pidPointer.readS32();
    if (!shouldWait) return { result: 0, pid: pid, status: null };

    const statusPointer = Memory.alloc(4);
    const waited = waitpid(pid, statusPointer, 0);
    return {
      result: 0,
      pid: pid,
      waited: waited,
      status: statusPointer.readS32()
    };
  } finally {
    actionsDestroy(actions);
  }
}

function readText(path, limit) {
  const fd = openFile(cString(path), O_RDONLY, 0);
  if (fd < 0) return null;
  try {
    const output = [];
    const buffer = Memory.alloc(65536);
    let total = 0;
    while (total < limit) {
      const wanted = Math.min(65536, limit - total);
      const count = Number(readFile(fd, buffer, wanted));
      if (count <= 0) break;
      output.push(buffer.readUtf8String(count));
      total += count;
    }
    return output.join('');
  } finally {
    closeFile(fd);
  }
}

rpc.exports = {
  info() {
    return { uid: getuid(), euid: geteuid() };
  },
  begin(path) {
    if (uploadFd >= 0) closeFile(uploadFd);
    unlinkFile(cString(path));
    uploadFd = openFile(cString(path), O_WRONLY | O_CREAT | O_TRUNC, 420);
    if (uploadFd < 0) throw new Error('open upload path failed: ' + path);
    return uploadFd;
  },
  chunk(data) {
    if (uploadFd < 0) throw new Error('upload is not open');
    const length = data.byteLength;
    const buffer = Memory.alloc(length);
    buffer.writeByteArray(data);
    let offset = 0;
    while (offset < length) {
      const count = Number(writeFile(uploadFd, buffer.add(offset), length - offset));
      if (count <= 0) throw new Error('write failed at offset ' + offset);
      offset += count;
    }
    return offset;
  },
  finish() {
    if (uploadFd < 0) return false;
    const result = closeFile(uploadFd);
    uploadFd = -1;
    return result === 0;
  },
  run(path, args, logPath, shouldWait) {
    return spawnProcess(path, args, logPath, shouldWait);
  },
  read(path, limit) {
    return readText(path, limit);
  }
};
"""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def attach_root_host(device: frida.core.Device) -> tuple[frida.core.Session, object]:
    process = next(
        (
            process
            for process in device.enumerate_processes()
            if process.name == "frida-server"
        ),
        None,
    )
    if process is None:
        raise RuntimeError("frida-server is not running")
    session = device.attach(process.pid)
    script = session.create_script(JAVASCRIPT)
    script.load()
    info = script.exports_sync.info()
    if info.get("uid") != 0 or info.get("euid") != 0:
        session.detach()
        raise RuntimeError(f"frida-server is not root: {info!r}")
    return session, script


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("deb", nargs="?", type=Path, default=DEFAULT_DEB)
    parser.add_argument("--chunk-size", type=int, default=512 * 1024)
    parser.add_argument("--wait", type=float, default=18.0)
    args = parser.parse_args()

    deb = args.deb.resolve()
    if not deb.is_file():
        raise SystemExit(f"deb is missing: {deb}")
    local_hash = sha256(deb)
    device = frida.get_usb_device(timeout=5)
    session, script = attach_root_host(device)
    api = script.exports_sync

    print(json.dumps({"deb": str(deb), "size": deb.stat().st_size, "sha256": local_hash}))
    api.begin(REMOTE_DEB)
    uploaded = 0
    with deb.open("rb") as handle:
        while chunk := handle.read(args.chunk_size):
            written = api.chunk(chunk)
            if written != len(chunk):
                raise RuntimeError(f"short remote write: {written} != {len(chunk)}")
            uploaded += written
            print(f"uploaded {uploaded}/{deb.stat().st_size}", flush=True)
    if not api.finish():
        raise RuntimeError("remote close failed")

    hash_result = api.run(
        "/var/jb/usr/bin/sha256sum",
        ["sha256sum", REMOTE_DEB],
        REMOTE_HASH_LOG,
        True,
    )
    hash_log = api.read(REMOTE_HASH_LOG, 4096) or ""
    print(json.dumps({"remote_hash_result": hash_result, "remote_hash_log": hash_log}))
    if hash_result.get("status") != 0 or not hash_log.startswith(local_hash + " "):
        raise RuntimeError("remote deb SHA256 differs from the local artifact")

    install_result = api.run(
        "/var/jb/usr/bin/dpkg",
        ["dpkg", "-i", REMOTE_DEB],
        REMOTE_INSTALL_LOG,
        True,
    )
    print(json.dumps({"install_spawn": install_result}))
    if install_result.get("status") != 0:
        install_log = api.read(REMOTE_INSTALL_LOG, 128 * 1024) or ""
        raise RuntimeError(f"dpkg failed: {install_result!r}\n{install_log}")

    time.sleep(min(args.wait, 2.0))
    install_log = api.read(REMOTE_INSTALL_LOG, 128 * 1024) or ""
    print("-- install log --")
    print(install_log.rstrip())

    query_result = api.run(
        "/var/jb/usr/bin/dpkg-query",
        [
            "dpkg-query",
            "-W",
            "-f=${Package} ${Version} ${Architecture}\\n",
            "com.xxdevice.ctwpro.rootless560",
        ],
        REMOTE_QUERY_LOG,
        True,
    )
    query_log = api.read(REMOTE_QUERY_LOG, 4096) or ""
    print(json.dumps({"query_result": query_result, "query_log": query_log}))
    if query_result.get("status") != 0 or " 5.6.0-2 " not in query_log:
        raise RuntimeError("device package version did not advance to 5.6.0-2")

    uicache_result = api.run(
        "/var/jb/usr/bin/uicache",
        ["uicache", "-p", "/var/jb/Applications/CTW Pro.app"],
        "/var/mobile/CTWPro.Rootless560_5.6.0-2.uicache.log",
        True,
    )
    print(json.dumps({"uicache_result": uicache_result}))
    session.detach()


if __name__ == "__main__":
    main()
