'use strict';

const PROTECTION_SELECTOR = 'pGflauxabac';
const VIEW_DID_LOAD_CALL_MIN = 0x589700;
const VIEW_DID_LOAD_CALL_MAX = 0x589900;

function mainOffset(address) {
  const main = Process.mainModule;
  if (address.compare(main.base) < 0 || address.compare(main.base.add(main.size)) >= 0) return null;
  return address.sub(main.base).toUInt32();
}

if (!ObjC.available) throw new Error('Objective-C runtime unavailable');

const protectionSelector = ObjC.selector(PROTECTION_SELECTOR);
const benignSelector = ObjC.selector('hash');
const messageSend = Module.getGlobalExportByName('objc_msgSend');

Interceptor.attach(messageSend, {
  onEnter(args) {
    if (!args[1].equals(protectionSelector)) return;
    const offset = mainOffset(this.context.lr);
    if (offset === null || offset < VIEW_DID_LOAD_CALL_MIN || offset >= VIEW_DID_LOAD_CALL_MAX) return;
    console.log(`[pG-skip] caller=VBox+0x${offset.toString(16)} receiver=${new ObjC.Object(args[0]).$className}; selector -> hash`);
    args[1] = benignSelector;
  },
});

const controller = ObjC.classes.UIAlertController['+ alertControllerWithTitle:message:preferredStyle:'];
Interceptor.attach(controller.implementation, {
  onEnter(args) {
    const title = args[2].isNull() ? '<nil>' : new ObjC.Object(args[2]).toString();
    const message = args[3].isNull() ? '<nil>' : new ObjC.Object(args[3]).toString();
    console.log(`[alert] title=${title} message=${message}`);
  },
});

console.log('[ready] pGflauxabac viewDidLoad call redirect installed');
