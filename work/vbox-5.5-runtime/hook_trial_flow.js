'use strict';

const OUTER_SELECTOR = 'o000oo0o0o000o0o000o000o0o0o0o0oo00o0o00o0o0o000o000000oo00000o0o0o0ooo0o0ooo0o0o0o0o0o0o0o0o0o0o0o00';
const HELPER_CALL_RETURNS = new Set([0x501d48, 0x50223c]);
const activeThreads = new Map();

function mainOffset(address) {
  const main = Process.mainModule;
  if (address.compare(main.base) < 0 || address.compare(main.base.add(main.size)) >= 0) return null;
  return address.sub(main.base).toUInt32();
}

function className(value) {
  if (value.isNull()) return '<nil>';
  try {
    return new ObjC.Object(value).$className;
  } catch (_) {
    return '<non-ObjC>';
  }
}

function inspectReturn(value) {
  if (value.isNull()) return '<nil>';
  try {
    const object = new ObjC.Object(value);
    const count = object.count === undefined ? '' : ` count=${object.count()}`;
    return `${object.$className}:${object}${count}`;
  } catch (_) {
    return value.toString();
  }
}

function isActive() {
  return activeThreads.has(Process.getCurrentThreadId());
}

function exportAddress(name) {
  try {
    return Module.getGlobalExportByName(name);
  } catch (_) {
    return null;
  }
}

function hookActiveExport(name, callbacks) {
  const address = exportAddress(name);
  if (address === null) return;
  Interceptor.attach(address, {
    onEnter(args) {
      this.active = isActive();
      if (this.active && callbacks.onEnter !== undefined) callbacks.onEnter.call(this, args);
    },
    onLeave(retval) {
      if (this.active && callbacks.onLeave !== undefined) callbacks.onLeave.call(this, retval);
    },
  });
}

if (!ObjC.available) throw new Error('Objective-C runtime unavailable');

const targetSelector = ObjC.selector(OUTER_SELECTOR);
const messageSend = Module.getGlobalExportByName('objc_msgSend');
Interceptor.attach(messageSend, {
  onEnter(args) {
    const threadId = Process.getCurrentThreadId();
    const caller = mainOffset(this.context.lr);
    if (args[1].equals(targetSelector)
      && caller !== null
      && HELPER_CALL_RETURNS.has(caller)) {
      this.kind = 'outer';
      this.threadIdValue = threadId;
      activeThreads.set(threadId, (activeThreads.get(threadId) || 0) + 1);
      console.log(`[outer] enter thread=${threadId} caller=VBox+0x${caller.toString(16)} receiverClass=${className(args[0])}`);
      return;
    }

    if (!activeThreads.has(threadId)) return;
    this.kind = 'inner';
    this.selectorName = ObjC.selectorAsString(args[1]);
    console.log(`[objc] caller=${caller === null ? this.context.lr : `VBox+0x${caller.toString(16)}`} receiverClass=${className(args[0])} selector=${this.selectorName} arg1=${args[2]} arg2=${args[3]}`);
  },
  onLeave(retval) {
    if (this.kind === 'inner') {
      console.log(`[objc] return selector=${this.selectorName} raw=${retval}`);
      return;
    }
    if (this.kind !== 'outer') return;
    const depth = (activeThreads.get(this.threadIdValue) || 1) - 1;
    if (depth === 0) activeThreads.delete(this.threadIdValue);
    else activeThreads.set(this.threadIdValue, depth);
    console.log(`[outer] leave ${inspectReturn(retval)}`);
  },
});

hookActiveExport('objc_alloc', {
  onEnter(args) {
    this.allocatedClass = className(args[0]);
  },
  onLeave(retval) {
    console.log(`[objc_alloc] class=${this.allocatedClass} return=${retval}`);
  },
});

hookActiveExport('time', {
  onLeave(retval) {
    console.log(`[time] ${retval}`);
  },
});

hookActiveExport('gettimeofday', {
  onEnter(args) {
    this.timeval = args[0];
  },
  onLeave(retval) {
    if (retval.toInt32() === 0 && !this.timeval.isNull()) {
      console.log(`[gettimeofday] sec=${this.timeval.readS64()} usec=${this.timeval.add(8).readS64()}`);
    }
  },
});

hookActiveExport('clock_gettime', {
  onEnter(args) {
    this.clockId = args[0].toInt32();
    this.timespec = args[1];
  },
  onLeave(retval) {
    if (retval.toInt32() === 0 && !this.timespec.isNull()) {
      console.log(`[clock_gettime] id=${this.clockId} sec=${this.timespec.readS64()} nsec=${this.timespec.add(8).readS64()}`);
    }
  },
});

hookActiveExport('CFAbsoluteTimeGetCurrent', {
  onEnter() {
    console.log('[CFAbsoluteTimeGetCurrent] called');
  },
});

for (const name of ['open', 'fopen', 'stat', 'lstat', 'access', 'opendir']) {
  hookActiveExport(name, {
    onEnter(args) {
      try {
        console.log(`[${name}] path=${args[0].readUtf8String()}`);
      } catch (_) {
        console.log(`[${name}] path=<unreadable:${args[0]}>`);
      }
    },
  });
}

hookActiveExport('SecItemCopyMatching', {
  onEnter(args) {
    console.log(`[SecItemCopyMatching] queryClass=${className(args[0])}`);
  },
  onLeave(retval) {
    console.log(`[SecItemCopyMatching] status=${retval.toInt32()}`);
  },
});

hookActiveExport('sqlite3_open', {
  onEnter(args) {
    console.log(`[sqlite3_open] path=${args[0].readUtf8String()}`);
  },
  onLeave(retval) {
    console.log(`[sqlite3_open] status=${retval.toInt32()}`);
  },
});

hookActiveExport('sqlite3_exec', {
  onEnter(args) {
    console.log(`[sqlite3_exec] sql=${args[1].readUtf8String()}`);
  },
  onLeave(retval) {
    console.log(`[sqlite3_exec] status=${retval.toInt32()}`);
  },
});

const controller = ObjC.classes.UIAlertController['+ alertControllerWithTitle:message:preferredStyle:'];
Interceptor.attach(controller.implementation, {
  onEnter(args) {
    const title = new ObjC.Object(args[2]);
    const message = new ObjC.Object(args[3]);
    console.log(`[alert] title=${title} message=${message}`);
  },
});

console.log(`[ready] thread-scoped trial flow hooks installed; selector=${targetSelector}`);
