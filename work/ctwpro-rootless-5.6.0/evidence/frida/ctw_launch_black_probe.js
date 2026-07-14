'use strict';

function out(kind, data) {
  console.log(JSON.stringify({ kind: kind, timestamp: Date.now(), data: data }));
}

function location(address) {
  if (address === null || address === undefined) return null;
  const module = Process.findModuleByAddress(address);
  const symbol = DebugSymbol.fromAddress(address);
  return {
    address: address.toString(),
    module: module === null ? null : module.name,
    offset: module === null ? null : '0x' + address.sub(module.base).toString(16),
    symbol: symbol === null ? null : symbol.toString()
  };
}

function register(context, name) {
  const value = context[name];
  return value === undefined ? null : location(value);
}

function sampleThreads(label) {
  const threads = Process.enumerateThreads();
  out('thread-sample', {
    label: label,
    count: threads.length,
    threads: threads.map(function (thread, index) {
      return {
        index: index,
        id: thread.id,
        name: thread.name || null,
        state: thread.state,
        pc: register(thread.context, 'pc'),
        lr: register(thread.context, 'lr'),
        sp: thread.context.sp === undefined ? null : thread.context.sp.toString()
      };
    })
  });
}

function dumpImp(className, selector) {
  if (!ObjC.available) return;
  const cls = ObjC.classes[className];
  if (cls === undefined) {
    out('imp', { className: className, selector: selector, implementation: null });
    return;
  }
  const method = cls['- ' + selector] || cls['+ ' + selector];
  out('imp', {
    className: className,
    selector: selector,
    implementation: method === undefined ? null : location(method.implementation)
  });
}

Process.attachModuleObserver({
  onAdded(module) {
    if (/CTW|fix\.dylib|0CTW\.dylib/i.test(module.name + ' ' + module.path)) {
      out('module-added', {
        name: module.name,
        path: module.path,
        base: module.base.toString(),
        size: module.size
      });
    }
  }
});

out('probe-loaded', { processId: Process.id });

[2000, 5000, 10000].forEach(function (delay) {
  setTimeout(function () {
    sampleThreads(String(delay) + 'ms');
    dumpImp('ViewController', 'viewDidLoad');
    dumpImp('ViewController', 'updateUITimer');
    if (ObjC.available) {
      out('main-queue-scheduled', { delay: delay });
      ObjC.schedule(ObjC.mainQueue, function () {
        out('main-queue-ran', { delay: delay });
      });
    }
  }, delay);
});
