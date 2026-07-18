'use strict';

function locationOf(implementation) {
  const address = implementation instanceof NativePointer
    ? implementation
    : ptr(implementation);
  const module = Process.findModuleByAddress(address);
  if (module === null) {
    return address.toString();
  }
  return `${module.name}+${address.sub(module.base)}`;
}

function dumpMethods(className, names) {
  const cls = ObjC.classes[className];
  if (cls === undefined) {
    console.log(JSON.stringify({ kind: 'class-missing', className }));
    return;
  }

  const wanted = new Set(names);
  for (const selector of cls.$ownMethods) {
    if (!wanted.has(selector)) {
      continue;
    }
    const method = cls[selector];
    console.log(JSON.stringify({
      kind: 'method',
      className,
      selector,
      types: method.types,
      implementation: locationOf(method.implementation)
    }));
  }
}

function titleOf(control) {
  try {
    if (control.isKindOfClass_(ObjC.classes.UIButton)) {
      const title = control.currentTitle();
      return title === null ? null : title.toString();
    }
  } catch (_) {
  }
  return null;
}

function dumpControls(view) {
  if (view === null) {
    return;
  }

  try {
    if (view.isKindOfClass_(ObjC.classes.UIControl)) {
      const targets = view.allTargets().allObjects();
      for (let index = 0; index < targets.count(); index += 1) {
        const target = targets.objectAtIndex_(index);
        const actions = view.actionsForTarget_forControlEvent_(target, 0xffffffff);
        if (actions === null) {
          continue;
        }
        for (let actionIndex = 0; actionIndex < actions.count(); actionIndex += 1) {
          console.log(JSON.stringify({
            kind: 'control',
            controlClass: view.$className,
            title: titleOf(view),
            targetClass: target.$className,
            action: actions.objectAtIndex_(actionIndex).toString()
          }));
        }
      }
    }

    const subviews = view.subviews();
    for (let index = 0; index < subviews.count(); index += 1) {
      dumpControls(subviews.objectAtIndex_(index));
    }
  } catch (error) {
    console.log(JSON.stringify({ kind: 'control-error', error: String(error) }));
  }
}

ObjC.schedule(ObjC.mainQueue, function () {
  dumpMethods('MachinePreferences', [
    'viewDidLoad',
    'nativePreferences:',
    'randomPreferences:',
    'isNative',
    'setIsNative:'
  ]);
  dumpMethods('ViewController', [
    'performeMachineStub',
    'performeMachine:',
    'nativeMachine:',
    'randomSwitch',
    'updateUITimer'
  ]);
  dumpMethods('LKVdConfig', ['randomConfig', 'getCurrentConfigData']);
  dumpMethods('LKDeviceConfig', [
    'sharedInstance',
    'defaultConfig',
    'writeCachedConfigString:',
    'setConfig:',
    'setDevice_updated:'
  ]);

  const windows = ObjC.classes.UIApplication.sharedApplication().windows();
  for (let index = 0; index < windows.count(); index += 1) {
    dumpControls(windows.objectAtIndex_(index));
  }
  console.log(JSON.stringify({ kind: 'done' }));
});
