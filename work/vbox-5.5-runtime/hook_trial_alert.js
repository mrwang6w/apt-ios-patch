'use strict';

const MAIN_HELPER_OFFSET = 0x12b00c;
const MAIN_HELPER_END_OFFSET = 0x12d6f8;
const TRIAL_FLOW_START_OFFSET = 0x500e5c;
const TRIAL_FLOW_END_OFFSET = 0x503000;
const TRIAL_HELPER_CLASS = 'oo0o0o0o00o0o00o0o0o0o0o000o000o0o0o0o0o0o000o0000000o00000o0o0o0ooo0o0oo00o0o0o0o0o0o0o0o0o0o0o00';
const TRIAL_HELPER_SELECTOR = 'o000oo0o0o000o0o000o000o0o0o0o0oo00o0o00o0o0o000o000000oo00000o0o0o0ooo0o0ooo0o0o0o0o0o0o0o0o0o0o0o00';

const activeHelperThreads = new Map();
let suppressHooks = 0;

function withSuppressedHooks(callback) {
  suppressHooks += 1;
  try {
    return callback();
  } finally {
    suppressHooks -= 1;
  }
}

function mainOffset(address) {
  const main = Process.mainModule;
  if (address.compare(main.base) < 0 || address.compare(main.base.add(main.size)) >= 0) {
    return null;
  }
  return address.sub(main.base).toUInt32();
}

function currentThreadIsRelevant(context) {
  if (activeHelperThreads.has(Process.getCurrentThreadId())) return true;
  const offset = mainOffset(context.lr);
  if (offset === null) return false;
  return (offset >= MAIN_HELPER_OFFSET && offset < MAIN_HELPER_END_OFFSET)
    || (offset >= TRIAL_FLOW_START_OFFSET && offset < TRIAL_FLOW_END_OFFSET);
}

function truncate(value, limit = 1200) {
  const text = String(value);
  return text.length <= limit ? text : `${text.slice(0, limit)}...<${text.length} chars>`;
}

function pointerText(value) {
  if (value.isNull()) return '<nil>';
  try {
    return new ObjC.Object(value).toString();
  } catch (_) {
    return value.toString();
  }
}

function inspectObject(value, label) {
  if (value.isNull()) {
    console.log(`${label}=<nil>`);
    return;
  }

  withSuppressedHooks(() => {
    try {
      const object = new ObjC.Object(value);
      console.log(`${label} ptr=${value} class=${object.$className} value=${truncate(object.toString())}`);

      if (object.allKeys !== undefined && object.objectForKey_ !== undefined) {
        const keys = object.allKeys();
        const count = Math.min(Number(keys.count()), 32);
        for (let index = 0; index < count; index += 1) {
          const key = keys.objectAtIndex_(index);
          const item = object.objectForKey_(key);
          console.log(`${label}[${truncate(key.toString(), 200)}]=${truncate(item === null ? '<nil>' : item.toString())}`);
        }
        return;
      }

      if (object.count !== undefined && object.objectAtIndex_ !== undefined) {
        const count = Number(object.count());
        console.log(`${label}.count=${count}`);
        for (let index = 0; index < Math.min(count, 32); index += 1) {
          const item = object.objectAtIndex_(index);
          console.log(`${label}[${index}]=${truncate(item === null ? '<nil>' : item.toString())}`);
        }
      }

      if (object.timeIntervalSince1970 !== undefined) {
        console.log(`${label}.timeIntervalSince1970=${object.timeIntervalSince1970()}`);
      }
    } catch (error) {
      console.log(`${label} ptr=${value} non-ObjC-or-unreadable: ${error}`);
    }
  });
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

function attachExport(name, callbacks) {
  let address;
  try {
    address = Module.getGlobalExportByName(name);
  } catch (_) {
    return;
  }
  Interceptor.attach(address, callbacks);
}

function attachRelevantExport(name, callbacks) {
  attachExport(name, {
    onEnter(args) {
      this.relevant = suppressHooks === 0 && currentThreadIsRelevant(this.context);
      if (!this.relevant || callbacks.onEnter === undefined) return;
      callbacks.onEnter.call(this, args);
    },
    onLeave(retval) {
      if (!this.relevant || callbacks.onLeave === undefined) return;
      callbacks.onLeave.call(this, retval);
    },
  });
}

function hookTrialHelper() {
  const main = Process.mainModule;
  const helper = main.base.add(MAIN_HELPER_OFFSET);
  console.log(`[trial-helper] ${main.path}+0x${MAIN_HELPER_OFFSET.toString(16)} instruction=${Instruction.parse(helper)}`);
  const klass = ObjC.classes[TRIAL_HELPER_CLASS];
  const method = klass === undefined ? undefined : klass[`- ${TRIAL_HELPER_SELECTOR}`];
  if (method === undefined) {
    console.log('[trial-helper] Objective-C method lookup failed');
    return;
  }
  if (!method.implementation.equals(helper)) {
    throw new Error(`trial helper IMP mismatch: runtime=${method.implementation} expected=${helper}`);
  }

  const original = new NativeFunction(method.implementation, 'pointer', ['pointer', 'pointer']);
  method.implementation = ObjC.implement(method, (self, selector) => {
    const threadId = Process.getCurrentThreadId();
    activeHelperThreads.set(threadId, (activeHelperThreads.get(threadId) || 0) + 1);
    const startedAt = Date.now();
    console.log(`[trial-helper] enter thread=${threadId} self=${pointerText(self)} selector=${ObjC.selectorAsString(selector)}`);
    try {
      const retval = original(self, selector);
      console.log(`[trial-helper] leave elapsed=${Date.now() - startedAt}ms retval=${retval}`);
      inspectObject(retval, '[trial-helper] return');
      return retval;
    } finally {
      const depth = (activeHelperThreads.get(threadId) || 1) - 1;
      if (depth === 0) activeHelperThreads.delete(threadId);
      else activeHelperThreads.set(threadId, depth);
    }
  });
  console.log(`[trial-helper] method swizzled without patching VBox __TEXT; replacement=${method.implementation}`);
}

function hookDefaults() {
  const defaults = ObjC.classes.NSUserDefaults;
  if (defaults === undefined) return;

  const reads = [
    ['- objectForKey:', 2],
    ['- stringForKey:', 2],
    ['- arrayForKey:', 2],
    ['- dictionaryForKey:', 2],
    ['- dataForKey:', 2],
    ['- integerForKey:', 2],
    ['- doubleForKey:', 2],
    ['- boolForKey:', 2],
  ];
  const seenImplementations = new Set();
  for (const [selector, keyIndex] of reads) {
    const method = defaults[selector];
    if (method === undefined || seenImplementations.has(method.implementation.toString())) continue;
    seenImplementations.add(method.implementation.toString());
    Interceptor.attach(method.implementation, {
      onEnter(args) {
        this.relevant = suppressHooks === 0 && currentThreadIsRelevant(this.context);
        if (!this.relevant) return;
        this.key = pointerText(args[keyIndex]);
        console.log(`[defaults-read] selector=${selector} key=${this.key}`);
      },
      onLeave(retval) {
        if (!this.relevant) return;
        console.log(`[defaults-read] selector=${selector} key=${this.key} raw=${retval}`);
        if (selector.includes('object') || selector.includes('string') || selector.includes('array')
          || selector.includes('dictionary') || selector.includes('data')) {
          inspectObject(retval, '[defaults-read] value');
        }
      },
    });
  }

  const writes = [
    ['- setObject:forKey:', 2, 3],
    ['- setInteger:forKey:', 2, 3],
    ['- setDouble:forKey:', 2, 3],
    ['- setBool:forKey:', 2, 3],
    ['- removeObjectForKey:', null, 2],
  ];
  for (const [selector, valueIndex, keyIndex] of writes) {
    const method = defaults[selector];
    if (method === undefined) continue;
    Interceptor.attach(method.implementation, {
      onEnter(args) {
        if (suppressHooks !== 0 || !currentThreadIsRelevant(this.context)) return;
        const value = valueIndex === null ? '<removed>' : pointerText(args[valueIndex]);
        console.log(`[defaults-write] selector=${selector} key=${pointerText(args[keyIndex])} value=${value}`);
        printBacktrace(this.context, '[defaults-write]');
      },
    });
  }
}

function hookKeychain() {
  attachRelevantExport('SecItemCopyMatching', {
    onEnter(args) {
      inspectObject(args[0], '[keychain-copy] query');
      this.resultPointer = args[1];
    },
    onLeave(retval) {
      console.log(`[keychain-copy] status=${retval.toInt32()}`);
      if (!this.resultPointer.isNull()) {
        inspectObject(this.resultPointer.readPointer(), '[keychain-copy] result');
      }
    },
  });
  for (const name of ['SecItemAdd', 'SecItemUpdate', 'SecItemDelete']) {
    attachRelevantExport(name, {
      onEnter(args) {
        inspectObject(args[0], `[${name}] query`);
        if (name === 'SecItemUpdate') inspectObject(args[1], `[${name}] attributes`);
      },
      onLeave(retval) {
        console.log(`[${name}] status=${retval.toInt32()}`);
      },
    });
  }
}

function hookTimeSources() {
  attachRelevantExport('time', {
    onLeave(retval) {
      console.log(`[time] seconds=${retval.toString()}`);
    },
  });
  attachRelevantExport('gettimeofday', {
    onEnter(args) {
      this.timeval = args[0];
    },
    onLeave(retval) {
      if (retval.toInt32() !== 0 || this.timeval.isNull()) return;
      console.log(`[gettimeofday] sec=${this.timeval.readS64()} usec=${this.timeval.add(8).readS64()}`);
    },
  });
  attachRelevantExport('CFAbsoluteTimeGetCurrent', {
    onLeave() {
      console.log(`[CFAbsoluteTimeGetCurrent] d0=${this.context.d0}`);
    },
  });

  const date = ObjC.classes.NSDate;
  if (date === undefined) return;
  for (const selector of ['+ date', '+ dateWithTimeIntervalSinceNow:', '- timeIntervalSince1970', '- compare:', '- timeIntervalSinceDate:']) {
    const method = date[selector];
    if (method === undefined) continue;
    Interceptor.attach(method.implementation, {
      onEnter(args) {
        this.relevant = suppressHooks === 0 && currentThreadIsRelevant(this.context);
        if (!this.relevant) return;
        this.receiver = args[0];
        this.argument = args[2];
        console.log(`[NSDate] enter selector=${selector} receiver=${pointerText(args[0])} arg2=${args[2]}`);
      },
      onLeave(retval) {
        if (!this.relevant) return;
        console.log(`[NSDate] leave selector=${selector} raw=${retval}`);
        if (selector === '+ date' || selector === '+ dateWithTimeIntervalSinceNow:') {
          inspectObject(retval, '[NSDate] return');
        }
      },
    });
  }
}

function hookFoundationIO() {
  const hooks = [
    [ObjC.classes.NSFileManager, '- fileExistsAtPath:', 2],
    [ObjC.classes.NSFileManager, '- contentsAtPath:', 2],
    [ObjC.classes.NSData, '+ dataWithContentsOfFile:', 2],
    [ObjC.classes.NSString, '- initWithContentsOfFile:encoding:error:', 2],
  ];
  for (const [klass, selector, pathIndex] of hooks) {
    if (klass === undefined || klass[selector] === undefined) continue;
    Interceptor.attach(klass[selector].implementation, {
      onEnter(args) {
        if (suppressHooks !== 0 || !currentThreadIsRelevant(this.context)) return;
        console.log(`[foundation-io] selector=${selector} path=${pointerText(args[pathIndex])}`);
        printBacktrace(this.context, '[foundation-io]');
      },
    });
  }
}

function logRelevantModules() {
  for (const module of Process.enumerateModules()) {
    const value = `${module.name} ${module.path}`;
    if (/VBox|VBoc|zyyy|Substrate|ElleKit/i.test(value)) {
      console.log(`[module] ${module.name} ${module.path} base=${module.base} size=0x${module.size.toString(16)}`);
    }
  }
}

function inspectVBocPatchBytes() {
  const module = Process.findModuleByName('VBoc.dylib');
  if (module === null) {
    console.log('[patch] VBoc.dylib is not loaded');
    return;
  }

  const offsets = [
    0xb02c, 0xb700, 0xb894, 0xb8c8, 0xb920, 0xb99c, 0xbed0,
    0xbf6c, 0xbfac, 0xc170, 0xc600, 0xcac0, 0xcb8c, 0xcd50,
    0xe5a4, 0xe7f0, 0xe90c, 0xeb80, 0xef44,
  ];
  for (const offset of offsets) {
    const address = module.base.add(offset);
    try {
      console.log(`[patch] VBoc.dylib+0x${offset.toString(16)} ${Instruction.parse(address)}`);
    } catch (error) {
      console.log(`[patch] VBoc.dylib+0x${offset.toString(16)} unreadable: ${error}`);
    }
  }
}

function hookAlerts() {
  const controller = ObjC.classes.UIAlertController;
  const factory = controller['+ alertControllerWithTitle:message:preferredStyle:'];
  Interceptor.attach(factory.implementation, {
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
      try {
        const actions = viewController.actions();
        for (let index = 0; index < actions.count(); index += 1) {
          const item = actions.objectAtIndex_(index);
          console.log(`[present-alert] action[${index}]=${item.title()}`);
        }
      } catch (_) {
      }
      printBacktrace(this.context, '[present-alert]');
    },
  });
}

function hookStateFiles() {
  attachExport('open', {
    onEnter(args) {
      this.path = args[0].readUtf8String();
      if (this.path === null || !/(sa\.conf|\/Preferences\/AMG\/)/.test(this.path)) return;
      console.log(`[open] ${this.path}`);
      printBacktrace(this.context, '[open]');
    },
  });

  attachExport('openat', {
    onEnter(args) {
      this.path = args[1].readUtf8String();
      if (this.path === null || !/(sa\.conf|\/Preferences\/AMG\/)/.test(this.path)) return;
      console.log(`[openat] ${this.path}`);
      printBacktrace(this.context, '[openat]');
    },
  });

  attachExport('fopen', {
    onEnter(args) {
      this.path = args[0].readUtf8String();
      if (this.path === null || !/(sa\.conf|\/Preferences\/AMG\/)/.test(this.path)) return;
      console.log(`[fopen] ${this.path}`);
      printBacktrace(this.context, '[fopen]');
    },
  });
}

function hookNetwork() {
  const requestClass = ObjC.classes.NSMutableURLRequest;
  if (requestClass !== undefined) {
    const setURL = requestClass['- setURL:'];
    Interceptor.attach(setURL.implementation, {
      onEnter(args) {
        const url = pointerText(args[2]);
        if (!/(amg456|rauti|rauth)/i.test(url)) return;
        console.log(`[request-url] ${url}`);
        printBacktrace(this.context, '[request-url]');
      },
    });
  }
}

if (!ObjC.available) {
  throw new Error('Objective-C runtime is unavailable');
}

logRelevantModules();
inspectVBocPatchBytes();
hookTrialHelper();
hookDefaults();
hookKeychain();
hookTimeSources();
hookFoundationIO();
hookAlerts();
hookStateFiles();
hookNetwork();
console.log('[ready] VBox trial-alert hooks installed');
