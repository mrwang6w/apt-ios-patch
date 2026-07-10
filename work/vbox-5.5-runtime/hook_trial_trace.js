'use strict';

const OUTER_SELECTOR = 'o000oo0o0o000o0o000o000o0o0o0o0oo00o0o00o0o0o000o000000oo00000o0o0o0ooo0o0ooo0o0o0o0o0o0o0o0o0o0o0o00';
const HELPER_START = 0x12b00c;
const HELPER_END = 0x12d6f8;
const HELPER_CALL_RETURNS = new Set([0x501d48, 0x50223c]);

function mainOffset(address) {
  const main = Process.mainModule;
  if (address.compare(main.base) < 0 || address.compare(main.base.add(main.size)) >= 0) return null;
  return address.sub(main.base).toUInt32();
}

function objectText(value) {
  if (value.isNull()) return '<nil>';
  try {
    const object = new ObjC.Object(value);
    return `${object.$className}:${object.toString()}`;
  } catch (_) {
    return value.toString();
  }
}

if (!ObjC.available) throw new Error('Objective-C runtime unavailable');

const targetSelector = ObjC.selector(OUTER_SELECTOR);
const messageSend = Module.getGlobalExportByName('objc_msgSend');
Interceptor.attach(messageSend, {
  onEnter(args) {
    const caller = mainOffset(this.context.lr);
    this.matched = args[1].equals(targetSelector)
      && caller !== null
      && HELPER_CALL_RETURNS.has(caller);
    if (!this.matched) return;
    this.traceThreadId = Process.getCurrentThreadId();
    const traceBlocks = [];
    const traceCalls = [];
    this.traceBlocks = traceBlocks;
    this.traceCalls = traceCalls;
    console.log(`[outer] enter thread=${this.traceThreadId} caller=VBox+0x${caller.toString(16)} receiver=${objectText(args[0])}`);
    Stalker.follow(this.traceThreadId, {
      events: { call: true, ret: false, exec: false, block: true, compile: false },
      onReceive(events) {
        for (const event of Stalker.parse(events, { annotate: true, stringify: false })) {
          const type = event[0];
          const location = event[1];
          const offset = mainOffset(location);
          if (offset === null || offset < HELPER_START || offset >= HELPER_END) continue;
          if (type === 'block') traceBlocks.push([offset, mainOffset(event[2])]);
          else if (type === 'call') traceCalls.push([offset, event[2]]);
        }
      },
    });
  },
  onLeave(retval) {
    if (!this.matched) return;
    Stalker.unfollow(this.traceThreadId);
    Stalker.flush();
    const traceBlocks = this.traceBlocks;
    const traceCalls = this.traceCalls;
    console.log(`[outer] leave return=${objectText(retval)}`);
    setTimeout(() => {
      console.log(`[trace] blocks=${traceBlocks.length}`);
      console.log(traceBlocks.map((entry) => `0x${entry[0].toString(16)}-0x${entry[1].toString(16)}`).join('\n'));
      console.log(`[trace] calls=${traceCalls.length}`);
      console.log(traceCalls.map((entry) => `VBox+0x${entry[0].toString(16)} -> ${DebugSymbol.fromAddress(entry[1])}`).join('\n'));
    }, 250);
  },
});

const controller = ObjC.classes.UIAlertController['+ alertControllerWithTitle:message:preferredStyle:'];
Interceptor.attach(controller.implementation, {
  onEnter(args) {
    console.log(`[alert] ${objectText(args[2])} / ${objectText(args[3])}`);
  },
});

console.log(`[ready] outer selector=${targetSelector}`);
