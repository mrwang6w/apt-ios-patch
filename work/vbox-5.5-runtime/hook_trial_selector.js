'use strict';

const SELECTOR_NAME = 'o0000o0o0o000o0o0o0o0o0o0o0o0o000o00o0o0o0o000o0000000o00000o0o0o0ooo0o0ooo0o0o0o0o0o0o0o0o0o0o0o00::';
const RETAIN_RETURN_SITES = new Set([0x501d50, 0x502244]);

function mainOffset(address) {
  const main = Process.mainModule;
  if (address.compare(main.base) < 0 || address.compare(main.base.add(main.size)) >= 0) return null;
  return address.sub(main.base).toUInt32();
}

function text(value) {
  if (value.isNull()) return '<nil>';
  try {
    const object = new ObjC.Object(value);
    return `${object.$className}:${object.toString()}`;
  } catch (_) {
    return value.toString();
  }
}

function bytes(value) {
  if (value.isNull()) return '<nil>';
  try {
    return hexdump(value, { offset: 0, length: 96, header: false, ansi: false });
  } catch (error) {
    return `<unreadable: ${error}>`;
  }
}

if (!ObjC.available) throw new Error('Objective-C runtime unavailable');

const targetSelector = ObjC.selector(SELECTOR_NAME);
const messageSend = Module.getGlobalExportByName('objc_msgSend');
Interceptor.attach(messageSend, {
  onEnter(args) {
    this.matched = args[1].equals(targetSelector);
    if (!this.matched) return;
    const offset = mainOffset(this.context.lr);
    console.log(`[trial-selector] caller=${offset === null ? this.context.lr : `VBox+0x${offset.toString(16)}`}`);
    console.log(`[trial-selector] receiver=${text(args[0])}`);
    console.log(`[trial-selector] arg1=${text(args[2])}`);
    console.log(`[trial-selector] arg2=${args[3]}\n${bytes(args[3])}`);
  },
  onLeave(retval) {
    if (!this.matched) return;
    console.log(`[trial-selector] return raw=${retval} bool=${retval.toInt32() & 1}`);
  },
});

const retain = Module.getGlobalExportByName('objc_retainAutoreleasedReturnValue');
Interceptor.attach(retain, {
  onEnter(args) {
    const offset = mainOffset(this.context.lr);
    if (offset === null || !RETAIN_RETURN_SITES.has(offset)) return;
    const object = new ObjC.Object(args[0]);
    console.log(`[trial-return] site=VBox+0x${offset.toString(16)} class=${object.$className} value=${object} count=${object.count()}`);
  },
});

const controller = ObjC.classes.UIAlertController['+ alertControllerWithTitle:message:preferredStyle:'];
Interceptor.attach(controller.implementation, {
  onEnter(args) {
    console.log(`[alert] title=${text(args[2])} message=${text(args[3])}`);
  },
});

console.log(`[ready] selector=${SELECTOR_NAME} address=${targetSelector}`);
