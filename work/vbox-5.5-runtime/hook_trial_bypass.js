'use strict';

const TARGET_RETURN_SITE = 0x502244;

function mainOffset(address) {
  const main = Process.mainModule;
  if (address.compare(main.base) < 0 || address.compare(main.base.add(main.size)) >= 0) return null;
  return address.sub(main.base).toUInt32();
}

if (!ObjC.available) throw new Error('Objective-C runtime unavailable');

let marker = null;
let replacement = null;

function ensureReplacement() {
  if (replacement !== null) return;
  marker = ObjC.classes.NSString.stringWithString_('VBoxTrialCompatibility');
  marker.retain();
  replacement = ObjC.classes.NSArray.arrayWithObject_(marker);
  replacement.retain();
}

const retain = Module.getGlobalExportByName('objc_retainAutoreleasedReturnValue');
Interceptor.attach(retain, {
  onEnter(args) {
    const offset = mainOffset(this.context.lr);
    this.matched = offset === TARGET_RETURN_SITE;
    if (!this.matched) return;
    ensureReplacement();
    const original = new ObjC.Object(args[0]);
    console.log(`[trial-bypass] original class=${original.$className} count=${original.count()}`);
    args[0] = replacement.handle;
  },
  onLeave(retval) {
    if (!this.matched) return;
    retval.replace(replacement.handle);
    console.log(`[trial-bypass] replacement class=${replacement.$className} count=${replacement.count()} value=${replacement}`);
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

console.log(`[ready] trial compatibility return override installed at VBox+0x${TARGET_RETURN_SITE.toString(16)}`);
