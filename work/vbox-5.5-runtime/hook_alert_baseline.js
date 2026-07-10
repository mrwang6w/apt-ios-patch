'use strict';

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
  const frames = Thread.backtrace(context, Backtracer.ACCURATE).slice(0, 24);
  console.log(`${prefix} backtrace:\n${frames.map(describeAddress).join('\n')}`);
}

if (!ObjC.available) throw new Error('Objective-C runtime is unavailable');

const controller = ObjC.classes.UIAlertController['+ alertControllerWithTitle:message:preferredStyle:'];
Interceptor.attach(controller.implementation, {
  onEnter(args) {
    console.log(`[alert-controller] title=${pointerText(args[2])} message=${pointerText(args[3])}`);
    printBacktrace(this.context, '[alert-controller]');
  },
});

const action = ObjC.classes.UIAlertAction['+ actionWithTitle:style:handler:'];
Interceptor.attach(action.implementation, {
  onEnter(args) {
    console.log(`[alert-action] title=${pointerText(args[2])} style=${args[3].toInt32()}`);
    printBacktrace(this.context, '[alert-action]');
  },
});

const present = ObjC.classes.UIViewController['- presentViewController:animated:completion:'];
Interceptor.attach(present.implementation, {
  onEnter(args) {
    let viewController;
    try {
      viewController = new ObjC.Object(args[2]);
    } catch (_) {
      return;
    }
    if (viewController.$className !== 'UIAlertController') return;
    console.log(`[present-alert] title=${viewController.title()} message=${viewController.message()}`);
    printBacktrace(this.context, '[present-alert]');
  },
});

console.log('[ready] VBox baseline alert hooks installed');
