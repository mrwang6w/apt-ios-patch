'use strict';

const HELPER_OFFSET = 0x12b00c;
const EXPECTED_PREFIX = 'fc6fbaa9fa6701a9';

function bytesToHex(buffer) {
  return Array.from(new Uint8Array(buffer), byte => byte.toString(16).padStart(2, '0')).join('');
}

function inspectResult(value) {
  if (value.isNull()) {
    console.log('[helper] result=<nil>');
    return 0;
  }

  try {
    const object = new ObjC.Object(value);
    const className = object.$className;
    console.log(`[helper] result=${value} class=${className}`);
    if (object.count === undefined || object.objectAtIndex_ === undefined) {
      console.log(`[helper] value=${object}`);
      return -1;
    }

    const count = Number(object.count());
    console.log(`[helper] count=${count}`);
    for (let index = 0; index < Math.min(count, 128); index += 1) {
      const item = object.objectAtIndex_(index);
      console.log(`[helper] item[${index}] class=${item.$className || '<unknown>'} value=${item}`);
    }
    return count;
  } catch (error) {
    console.log(`[helper] unreadable=${error}`);
    return -1;
  }
}

if (!ObjC.available) throw new Error('Objective-C runtime is unavailable');

const main = Process.mainModule;
const helper = main.base.add(HELPER_OFFSET);
const prefix = bytesToHex(helper.readByteArray(8));
console.log(`[ready] main=${main.name} base=${main.base} size=0x${main.size.toString(16)} path=${main.path}`);
console.log(`[ready] helper=${helper} offset=0x${HELPER_OFFSET.toString(16)} prefix=${prefix} instruction=${Instruction.parse(helper)}`);
if (prefix !== EXPECTED_PREFIX) {
  throw new Error(`helper byte mismatch: got ${prefix}, expected ${EXPECTED_PREFIX}`);
}

let invocation = 0;
Interceptor.attach(helper, {
  onEnter() {
    invocation += 1;
    this.invocation = invocation;
    this.startedAt = Date.now();
    this.caller = this.context.lr;
  },
  onLeave(retval) {
    const caller = this.caller.compare(main.base) >= 0 && this.caller.compare(main.base.add(main.size)) < 0
      ? `VBox+0x${this.caller.sub(main.base).toString(16)}`
      : this.caller.toString();
    console.log(`[helper] leave #${this.invocation} thread=${Process.getCurrentThreadId()} elapsed=${Date.now() - this.startedAt}ms caller=${caller} raw=${retval}`);
    inspectResult(retval);
  },
});
