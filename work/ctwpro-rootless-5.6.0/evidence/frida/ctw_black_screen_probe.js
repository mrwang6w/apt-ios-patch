'use strict';

function out(kind, data) {
  console.log(JSON.stringify({ kind: kind, data: data }));
}

function safe(fn, fallback) {
  try {
    return fn();
  } catch (error) {
    return fallback === undefined ? '<error: ' + error + '>' : fallback;
  }
}

function describe(object) {
  if (object === null || object === undefined) return null;
  return safe(function () { return object.toString(); }, '<description failed>');
}

function frame(view) {
  return safe(function () {
    const value = view.frame();
    return {
      x: value.origin.x,
      y: value.origin.y,
      width: value.size.width,
      height: value.size.height
    };
  }, null);
}

function className(object) {
  return safe(function () { return object.$className; }, '<unknown>');
}

function dumpView(view, depth) {
  if (view === null || view === undefined || depth > 3) return null;
  const result = {
    className: className(view),
    frame: frame(view),
    bounds: safe(function () {
      const value = view.bounds();
      return {
        x: value.origin.x,
        y: value.origin.y,
        width: value.size.width,
        height: value.size.height
      };
    }, null),
    hidden: safe(function () { return !!view.isHidden(); }, null),
    alpha: safe(function () { return Number(view.alpha()); }, null),
    opaque: safe(function () { return !!view.isOpaque(); }, null),
    window: safe(function () { return describe(view.window()); }, null),
    subviews: []
  };
  const children = safe(function () { return view.subviews(); }, null);
  const count = children === null ? 0 : safe(function () { return Number(children.count()); }, 0);
  result.subviewCount = count;
  for (let i = 0; i < Math.min(count, 30); i++) {
    result.subviews.push(dumpView(children.objectAtIndex_(i), depth + 1));
  }
  if (count > 30) result.subviewsTruncated = count - 30;
  return result;
}

function dumpController(controller, depth) {
  if (controller === null || controller === undefined || depth > 5) return null;
  const result = {
    className: className(controller),
    description: describe(controller),
    title: safe(function () { return describe(controller.title()); }, null),
    viewLoaded: safe(function () { return !!controller.isViewLoaded(); }, null),
    view: safe(function () { return dumpView(controller.view(), 0); }, null),
    presented: null,
    children: []
  };
  const presented = safe(function () { return controller.presentedViewController(); }, null);
  if (presented !== null) result.presented = dumpController(presented, depth + 1);
  const children = safe(function () { return controller.childViewControllers(); }, null);
  const count = children === null ? 0 : safe(function () { return Number(children.count()); }, 0);
  for (let i = 0; i < Math.min(count, 12); i++) {
    result.children.push(dumpController(children.objectAtIndex_(i), depth + 1));
  }
  return result;
}

function location(address) {
  if (address === null || address === undefined) return null;
  const module = Process.findModuleByAddress(address);
  if (module === null) return address.toString();
  return module.name + '+0x' + address.sub(module.base).toString(16);
}

function dumpMethods(classNameValue, selectors) {
  const cls = ObjC.classes[classNameValue];
  if (cls === undefined) {
    out('class-missing', classNameValue);
    return;
  }
  const methods = {};
  selectors.forEach(function (selector) {
    const method = cls['- ' + selector] || cls['+ ' + selector];
    methods[selector] = method === undefined ? null : location(method.implementation);
  });
  out('method-imps', { className: classNameValue, methods: methods });
}

if (!ObjC.available) {
  out('fatal', 'Objective-C runtime is unavailable');
} else {
  dumpMethods('ViewController', [
    'viewDidLoad',
    'viewDidAppear:',
    'updateUITimer',
    'recharge:',
    'lockUI:',
    'isInNetwork',
    'writeCTWCacheEnv',
    'performeMachineStub',
    'handleAppWillEnterForeground'
  ]);

  const delegateClassNames = ['AppDelegate', 'SceneDelegate'];
  delegateClassNames.forEach(function (name) {
    dumpMethods(name, [
      'application:didFinishLaunchingWithOptions:',
      'applicationDidBecomeActive:',
      'scene:willConnectToSession:options:',
      'sceneDidBecomeActive:'
    ]);
  });

  out('main-queue-scheduled', { processId: Process.id });
  ObjC.schedule(ObjC.mainQueue, function () {
    const app = ObjC.classes.UIApplication.sharedApplication();
    const delegate = safe(function () { return app.delegate(); }, null);
    const windows = safe(function () { return app.windows(); }, null);
    const count = windows === null ? 0 : safe(function () { return Number(windows.count()); }, 0);
    const snapshot = {
      applicationState: safe(function () { return Number(app.applicationState()); }, null),
      delegateClass: delegate === null ? null : className(delegate),
      keyWindow: safe(function () { return describe(app.keyWindow()); }, null),
      windowCount: count,
      windows: []
    };
    for (let i = 0; i < count; i++) {
      const window = windows.objectAtIndex_(i);
      const root = safe(function () { return window.rootViewController(); }, null);
      snapshot.windows.push({
        index: i,
        className: className(window),
        description: describe(window),
        key: safe(function () { return !!window.isKeyWindow(); }, null),
        hidden: safe(function () { return !!window.isHidden(); }, null),
        alpha: safe(function () { return Number(window.alpha()); }, null),
        level: safe(function () { return Number(window.windowLevel()); }, null),
        frame: frame(window),
        rootViewController: root === null ? null : dumpController(root, 0)
      });
    }
    out('ui-snapshot', snapshot);
    out('main-queue-completed', { processId: Process.id });
  });
}
