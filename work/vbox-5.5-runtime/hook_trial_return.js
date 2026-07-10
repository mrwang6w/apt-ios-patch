'use strict';

const RETAIN_RETURN_SITES = new Set([0x501d50, 0x502244]);
const HELPER_START = 0x12b00c;
const HELPER_END = 0x12d6f8;

function mainOffset(address) {
  const main = Process.mainModule;
  if (address.compare(main.base) < 0 || address.compare(main.base.add(main.size)) >= 0) return null;
  return address.sub(main.base).toUInt32();
}

function helperCaller(context) {
  const offset = mainOffset(context.lr);
  return offset !== null && offset >= HELPER_START && offset < HELPER_END ? offset : null;
}

function text(value) {
  if (value.isNull()) return '<nil>';
  try {
    return new ObjC.Object(value).toString();
  } catch (_) {
    return value.toString();
  }
}

function inspect(value, label) {
  if (value.isNull()) {
    console.log(`${label}=<nil>`);
    return;
  }
  try {
    const object = new ObjC.Object(value);
    console.log(`${label} ptr=${value} class=${object.$className} value=${object.toString()}`);
    if (object.count !== undefined) console.log(`${label}.count=${object.count()}`);
    if (object.objectAtIndex_ !== undefined) {
      const count = Math.min(Number(object.count().toString()), 16);
      for (let index = 0; index < count; index += 1) {
        console.log(`${label}[${index}]=${object.objectAtIndex_(index)}`);
      }
    }
  } catch (error) {
    console.log(`${label} unreadable: ${error}`);
  }
}

function describe(address) {
  const module = Process.findModuleByAddress(address);
  if (module === null) return DebugSymbol.fromAddress(address).toString();
  return `${module.name}+0x${address.sub(module.base).toString(16)}`;
}

function backtrace(context, prefix) {
  const frames = Thread.backtrace(context, Backtracer.ACCURATE).slice(0, 16);
  console.log(`${prefix}\n${frames.map(describe).join('\n')}`);
}

function exportAddress(name) {
  try {
    return Module.getGlobalExportByName(name);
  } catch (_) {
    return null;
  }
}

function hookHelperExport(name, callbacks) {
  const address = exportAddress(name);
  if (address === null) return;
  Interceptor.attach(address, {
    onEnter(args) {
      this.offset = helperCaller(this.context);
      if (this.offset === null || callbacks.onEnter === undefined) return;
      callbacks.onEnter.call(this, args);
    },
    onLeave(retval) {
      if (this.offset === null || callbacks.onLeave === undefined) return;
      callbacks.onLeave.call(this, retval);
    },
  });
}

function hookHelperMethod(classes, selector, callbacks) {
  const implementations = new Set();
  for (const className of classes) {
    const klass = ObjC.classes[className];
    const method = klass === undefined ? undefined : klass[selector];
    if (method === undefined) continue;
    const key = method.implementation.toString();
    if (implementations.has(key)) continue;
    implementations.add(key);
    Interceptor.attach(method.implementation, {
      onEnter(args) {
        this.offset = helperCaller(this.context);
        if (this.offset === null || callbacks.onEnter === undefined) return;
        callbacks.onEnter.call(this, args);
      },
      onLeave(retval) {
        if (this.offset === null || callbacks.onLeave === undefined) return;
        callbacks.onLeave.call(this, retval);
      },
    });
  }
}

function hookHelperState() {
  const mutableArrays = ['__NSArrayM', 'NSMutableArray'];
  hookHelperMethod(mutableArrays, '- addObject:', {
    onEnter(args) {
      console.log(`[array-add] caller=VBox+0x${this.offset.toString(16)} array=${text(args[0])} object=${text(args[2])}`);
    },
  });
  hookHelperMethod(mutableArrays, '- insertObject:atIndex:', {
    onEnter(args) {
      console.log(`[array-insert] caller=VBox+0x${this.offset.toString(16)} index=${args[3]} object=${text(args[2])}`);
    },
  });
  for (const selector of ['- removeAllObjects', '- removeLastObject', '- removeObject:', '- removeObjectAtIndex:']) {
    hookHelperMethod(mutableArrays, selector, {
      onEnter(args) {
        console.log(`[array-remove] caller=VBox+0x${this.offset.toString(16)} selector=${selector} arg=${args[2]}`);
      },
    });
  }

  const dictionaries = ['__NSDictionaryI', '__NSDictionaryM', '__NSCFDictionary', 'NSDictionary', 'NSMutableDictionary'];
  for (const selector of ['- objectForKey:', '- objectForKeyedSubscript:']) {
    hookHelperMethod(dictionaries, selector, {
      onEnter(args) {
        this.key = text(args[2]);
      },
      onLeave(retval) {
        console.log(`[dictionary-read] caller=VBox+0x${this.offset.toString(16)} selector=${selector} key=${this.key} value=${text(retval)}`);
      },
    });
  }

  const defaults = ['NSUserDefaults'];
  for (const selector of ['- objectForKey:', '- stringForKey:', '- integerForKey:', '- doubleForKey:', '- boolForKey:']) {
    hookHelperMethod(defaults, selector, {
      onEnter(args) {
        this.key = text(args[2]);
      },
      onLeave(retval) {
        console.log(`[defaults-read] caller=VBox+0x${this.offset.toString(16)} selector=${selector} key=${this.key} raw=${retval}`);
      },
    });
  }
  for (const selector of ['- setObject:forKey:', '- setInteger:forKey:', '- setDouble:forKey:', '- setBool:forKey:']) {
    hookHelperMethod(defaults, selector, {
      onEnter(args) {
        console.log(`[defaults-write] caller=VBox+0x${this.offset.toString(16)} selector=${selector} key=${text(args[3])} value=${text(args[2])}`);
      },
    });
  }

  const dates = ['NSDate', '__NSDate', '__NSTaggedDate'];
  for (const selector of ['+ date', '+ dateWithTimeIntervalSince1970:', '+ dateWithTimeIntervalSinceNow:', '- timeIntervalSince1970', '- compare:', '- timeIntervalSinceDate:']) {
    hookHelperMethod(dates, selector, {
      onEnter(args) {
        console.log(`[date] enter caller=VBox+0x${this.offset.toString(16)} selector=${selector} receiver=${text(args[0])} arg=${args[2]}`);
      },
      onLeave(retval) {
        console.log(`[date] leave caller=VBox+0x${this.offset.toString(16)} selector=${selector} raw=${retval}`);
        if (selector.startsWith('+ date')) inspect(retval, '[date] return');
      },
    });
  }

  const fileManager = ['NSFileManager'];
  for (const selector of ['- fileExistsAtPath:', '- contentsAtPath:', '- contentsOfDirectoryAtPath:error:', '- enumeratorAtPath:']) {
    hookHelperMethod(fileManager, selector, {
      onEnter(args) {
        console.log(`[file-manager] caller=VBox+0x${this.offset.toString(16)} selector=${selector} path=${text(args[2])}`);
      },
      onLeave(retval) {
        console.log(`[file-manager] caller=VBox+0x${this.offset.toString(16)} selector=${selector} result=${text(retval)}`);
      },
    });
  }

  hookHelperExport('time', {
    onLeave(retval) {
      console.log(`[time] caller=VBox+0x${this.offset.toString(16)} seconds=${retval}`);
    },
  });
  hookHelperExport('gettimeofday', {
    onEnter(args) {
      this.timeval = args[0];
    },
    onLeave(retval) {
      if (retval.toInt32() === 0 && !this.timeval.isNull()) {
        console.log(`[gettimeofday] caller=VBox+0x${this.offset.toString(16)} sec=${this.timeval.readS64()} usec=${this.timeval.add(8).readS64()}`);
      }
    },
  });
  hookHelperExport('CFAbsoluteTimeGetCurrent', {
    onEnter() {
      console.log(`[CFAbsoluteTimeGetCurrent] caller=VBox+0x${this.offset.toString(16)}`);
    },
  });

  hookHelperExport('open', {
    onEnter(args) {
      console.log(`[open] caller=VBox+0x${this.offset.toString(16)} path=${args[0].readUtf8String()}`);
    },
  });
  hookHelperExport('fopen', {
    onEnter(args) {
      console.log(`[fopen] caller=VBox+0x${this.offset.toString(16)} path=${args[0].readUtf8String()} mode=${args[1].readUtf8String()}`);
    },
  });

  hookHelperExport('SecItemCopyMatching', {
    onEnter(args) {
      inspect(args[0], '[keychain] query');
      this.output = args[1];
    },
    onLeave(retval) {
      console.log(`[keychain] caller=VBox+0x${this.offset.toString(16)} status=${retval.toInt32()}`);
      if (!this.output.isNull()) inspect(this.output.readPointer(), '[keychain] result');
    },
  });
}

if (!ObjC.available) throw new Error('Objective-C runtime unavailable');

hookHelperState();

const retain = Module.getGlobalExportByName('objc_retainAutoreleasedReturnValue');
Interceptor.attach(retain, {
  onEnter(args) {
    const offset = mainOffset(this.context.lr);
    this.matched = offset !== null && RETAIN_RETURN_SITES.has(offset);
    if (!this.matched) return;
    this.offset = offset;
    this.value = args[0];
    console.log(`[trial-return] site=VBox+0x${offset.toString(16)}`);
    inspect(this.value, '[trial-return] value');
    backtrace(this.context, '[trial-return] backtrace:');
  },
  onLeave(retval) {
    if (!this.matched) return;
    console.log(`[trial-return] retained=${retval}`);
  },
});

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
  },
});

console.log('[ready] trial-return hooks installed');
