'use strict';

function text(value) {
  if (value.isNull()) return '<nil>';
  try {
    return new ObjC.Object(value).toString();
  } catch (_) {
    return value.toString();
  }
}

function describe(address) {
  const module = Process.findModuleByAddress(address);
  if (module === null) return DebugSymbol.fromAddress(address).toString();
  return `${module.name}+0x${address.sub(module.base).toString(16)}`;
}

function backtrace(context, prefix) {
  const frames = Thread.backtrace(context, Backtracer.ACCURATE).slice(0, 20);
  console.log(`${prefix}\n${frames.map(describe).join('\n')}`);
}

if (!ObjC.available) throw new Error('Objective-C runtime unavailable');

const controller = ObjC.classes.UIAlertController['+ alertControllerWithTitle:message:preferredStyle:'];
Interceptor.attach(controller.implementation, {
  onEnter(args) {
    console.log(`[alert] title=${text(args[2])} message=${text(args[3])}`);
    backtrace(this.context, '[alert] backtrace:');
  },
});

const action = ObjC.classes.UIAlertAction['+ actionWithTitle:style:handler:'];
Interceptor.attach(action.implementation, {
  onEnter(args) {
    console.log(`[action] title=${text(args[2])} style=${args[3].toInt32()}`);
    backtrace(this.context, '[action] backtrace:');
  },
});

console.log('[ready] alert-only control hooks installed');
