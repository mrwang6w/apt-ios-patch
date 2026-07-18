'use strict';

const invokeLocalRandom = __INVOKE_LOCAL_RANDOM__;
const loadTweaks = __LOAD_TWEAKS__;

if (loadTweaks) {
  for (const path of [
    '/var/jb/Library/MobileSubstrate/DynamicLibraries/CTW.dylib',
    '/var/jb/Library/MobileSubstrate/DynamicLibraries/0CTW.dylib'
  ]) {
    try {
      const module = Module.load(path);
      send({ kind: 'module-loaded', path: path, base: module.base.toString() });
    } catch (error) {
      send({ kind: 'module-load-error', path: path, error: String(error) });
    }
  }
}

function exported(name, returnType, argumentTypes) {
  const address = Module.findGlobalExportByName(name);
  if (address === null) throw new Error('missing export: ' + name);
  return new NativeFunction(address, returnType, argumentTypes);
}

const objcGetClass = exported('objc_getClass', 'pointer', ['pointer']);
const selRegisterName = exported('sel_registerName', 'pointer', ['pointer']);
const objcMsgSend0 = exported('objc_msgSend', 'pointer', ['pointer', 'pointer']);
const objcMsgSend1 = exported('objc_msgSend', 'pointer', ['pointer', 'pointer', 'pointer']);
const objcMsgSendLength = exported('objc_msgSend', 'ulong', ['pointer', 'pointer']);

function cString(value) {
  return Memory.allocUtf8String(value);
}

function getClass(name) {
  return objcGetClass(cString(name));
}

function selector(name) {
  return selRegisterName(cString(name));
}

function call0(receiver, name) {
  return objcMsgSend0(receiver, selector(name));
}

function sendNSData(kind, data) {
  if (data.isNull()) {
    send({ kind: kind, missing: true });
    return;
  }
  const length = Number(objcMsgSendLength(data, selector('length')));
  const bytes = call0(data, 'bytes');
  send({ kind: kind, length: length }, bytes.readByteArray(length));
}

function sendObject(kind, object) {
  if (object.isNull()) {
    send({ kind: kind, missing: true });
    return;
  }
  const description = call0(object, 'description');
  const data = objcMsgSend1(
    description,
    selector('dataUsingEncoding:'),
    ptr('4')
  );
  sendNSData(kind, data);
}

let classProbeAttempts = 0;

function run() {
  const deviceClass = getClass('LKDeviceConfig');
  const vdClass = getClass('LKVdConfig');
  classProbeAttempts += 1;
  if ((deviceClass.isNull() || vdClass.isNull()) && classProbeAttempts < 160) {
    setTimeout(run, 250);
    return;
  }
  send({
    kind: 'classes',
    LKDeviceConfig: deviceClass.toString(),
    LKVdConfig: vdClass.toString(),
    attempts: classProbeAttempts
  });

  if (!deviceClass.isNull()) {
    const instance = call0(deviceClass, 'sharedInstance');
    for (const method of [
      'config',
      'activedConfig',
      'defaultConfig',
      'readCachedConfigString',
      'configCachePath',
      'original_host',
      'replaced_host'
    ]) {
      try {
        sendObject('device-' + method, call0(instance, method));
      } catch (error) {
        send({ kind: 'device-' + method + '-error', error: String(error) });
      }
    }
    if (invokeLocalRandom) {
      try {
        sendObject('device-localRandomConfig', call0(instance, 'makeRandomConfig'));
        sendObject('device-config-after-local-random', call0(instance, 'config'));
        sendObject(
          'device-cached-after-local-random',
          call0(instance, 'readCachedConfigString')
        );
      } catch (error) {
        send({ kind: 'device-local-random-error', error: String(error) });
      }
    }
  }

  if (!vdClass.isNull()) {
    try {
      sendNSData('vd-getCurrentConfigData', call0(vdClass, 'getCurrentConfigData'));
    } catch (error) {
      send({ kind: 'vd-getCurrentConfigData-error', error: String(error) });
    }
  }
  send({ kind: 'complete' });
}

setTimeout(run, 250);
