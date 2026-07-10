'use strict';

const TRIAL_FLOW_START = 0x500e5c;
const TRIAL_FLOW_END = 0x507058;
let inspecting = false;

function mainOffset(address) {
  const main = Process.mainModule;
  if (address.compare(main.base) < 0 || address.compare(main.base.add(main.size)) >= 0) return null;
  return address.sub(main.base).toUInt32();
}

function pointerText(value) {
  if (value.isNull()) return '<nil>';
  try {
    return new ObjC.Object(value).toString();
  } catch (_) {
    return value.toString();
  }
}

function describeAddress(address) {
  const module = Process.findModuleByAddress(address);
  const symbol = DebugSymbol.fromAddress(address);
  if (module === null) return symbol.toString();
  return `${module.name}+0x${address.sub(module.base).toString(16)} ${symbol.name || ''}`.trim();
}

function printBacktrace(context, prefix) {
  const frames = Thread.backtrace(context, Backtracer.ACCURATE).slice(0, 20);
  console.log(`${prefix} backtrace:\n${frames.map(describeAddress).join('\n')}`);
}

function inspectReturn(value, offset) {
  if (value.isNull() || inspecting) return;
  inspecting = true;
  try {
    const object = new ObjC.Object(value);
    const className = object.$className;
    if (!/Array|Set|Dictionary/.test(className)) return;
    console.log(`[trial-result] caller=VBox+0x${offset.toString(16)} ptr=${value} class=${className} value=${object}`);
    if (object.allKeys !== undefined && object.objectForKey_ !== undefined) {
      const keys = object.allKeys();
      for (let index = 0; index < Math.min(Number(keys.count()), 64); index += 1) {
        const key = keys.objectAtIndex_(index);
        console.log(`[trial-result] key=${key} value=${object.objectForKey_(key)}`);
      }
    } else if (object.count !== undefined && object.objectAtIndex_ !== undefined) {
      const count = Number(object.count());
      console.log(`[trial-result] count=${count}`);
      for (let index = 0; index < Math.min(count, 64); index += 1) {
        const item = object.objectAtIndex_(index);
        console.log(`[trial-result] item[${index}] class=${item.$className || '<unknown>'} value=${item}`);
      }
    }
  } catch (error) {
    console.log(`[trial-result] caller=VBox+0x${offset.toString(16)} unreadable=${error}`);
  } finally {
    inspecting = false;
  }
}

if (!ObjC.available) throw new Error('Objective-C runtime is unavailable');

const retainReturn = Module.getGlobalExportByName('objc_retainAutoreleasedReturnValue');
Interceptor.attach(retainReturn, {
  onEnter(args) {
    if (inspecting) return;
    const offset = mainOffset(this.context.lr);
    if (offset === null || offset < TRIAL_FLOW_START || offset >= TRIAL_FLOW_END) return;
    inspectReturn(args[0], offset);
  },
});

const controller = ObjC.classes.UIAlertController['+ alertControllerWithTitle:message:preferredStyle:'];
Interceptor.attach(controller.implementation, {
  onEnter(args) {
    console.log(`[alert-controller] title=${pointerText(args[2])} message=${pointerText(args[3])}`);
    printBacktrace(this.context, '[alert-controller]');
  },
});

console.log(`[ready] trial-result hook installed; retain=${retainReturn}`);
