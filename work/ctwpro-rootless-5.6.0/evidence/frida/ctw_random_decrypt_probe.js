'use strict';

function out(kind, data) {
  console.log(JSON.stringify({ kind: kind, timestamp: Date.now(), data: data }));
}

function hex(address, length) {
  if (address === null || address.isNull() || length <= 0) return null;
  const bytes = new Uint8Array(address.readByteArray(length));
  return Array.from(bytes, function (value) {
    return value.toString(16).padStart(2, '0');
  }).join('');
}

function location(address) {
  const module = Process.findModuleByAddress(address);
  if (module === null) return address.toString();
  return module.name + '+0x' + address.sub(module.base).toString(16);
}

let cryptoIndex = 0;
const cryptoAddress = Module.getGlobalExportByName('CCCrypt');
Interceptor.attach(cryptoAddress, {
  onEnter(args) {
    this.index = cryptoIndex++;
    this.operation = args[0].toInt32();
    this.algorithm = args[1].toInt32();
    this.options = args[2].toInt32();
    this.key = args[3];
    this.keyLength = Number(args[4]);
    this.iv = args[5];
    this.input = args[6];
    this.inputLength = Number(args[7]);
    this.output = this.context.sp.readPointer();
    this.outputAvailable = Number(this.context.sp.add(Process.pointerSize).readPointer());
    this.outputMoved = this.context.sp.add(Process.pointerSize * 2).readPointer();
    this.caller = this.returnAddress;
    const blockSize = this.algorithm === 0 ? 16 : 8;
    out('cccrypt-enter', {
      index: this.index,
      operation: this.operation,
      algorithm: this.algorithm,
      options: this.options,
      keyLength: this.keyLength,
      keyHex: hex(this.key, Math.min(this.keyLength, 64)),
      ivHex: this.iv.isNull() ? null : hex(this.iv, blockSize),
      inputLength: this.inputLength,
      inputHeadHex: hex(this.input, Math.min(this.inputLength, 32)),
      caller: location(this.caller)
    });
  },
  onLeave(retval) {
    const status = retval.toInt32();
    let moved = 0;
    if (status === 0 && !this.outputMoved.isNull()) {
      moved = Number(this.outputMoved.readU64());
    }
    const event = {
      index: this.index,
      status: status,
      moved: moved,
      outputHeadHex: moved > 0 ? hex(this.output, Math.min(moved, 64)) : null
    };
    if (status === 0 && this.operation === 1 && moved >= 256) {
      const path = '/var/mobile/ctw-cccrypt-' + this.index + '.bin';
      const file = new File(path, 'wb');
      file.write(this.output.readByteArray(moved));
      file.flush();
      file.close();
      event.path = path;
    }
    out('cccrypt-leave', event);
  }
});
out('hook', { name: 'CCCrypt', address: cryptoAddress.toString() });

function buttonTitle(control) {
  try {
    if (!control.respondsToSelector_('titleForState:')) return null;
    const title = control.titleForState_(0);
    return title === null ? null : title.toString();
  } catch (_) {
    return null;
  }
}

function viewText(view) {
  try {
    if (!view.respondsToSelector_('text')) return null;
    const text = view.text();
    return text === null ? null : text.toString();
  } catch (_) {
    return null;
  }
}

function controlActions(control) {
  const values = [];
  try {
    const targets = control.allTargets().allObjects();
    for (let i = 0; i < Number(targets.count()); i++) {
      const target = targets.objectAtIndex_(i);
      values.push({
        target: target.$className,
        actions: control.actionsForTarget_forControlEvent_(
          target,
          0xffffffffffffffff
        ).toString()
      });
    }
  } catch (_) {}
  return values;
}

function scanView(view, matches, controls, texts, parentControl) {
  let currentControl = parentControl;
  if (view.isKindOfClass_(ObjC.classes.UIControl)) {
    currentControl = view;
    controls.push({
      className: view.$className,
      title: buttonTitle(view),
      actions: controlActions(view)
    });
  }
  const title = buttonTitle(view);
  if (title !== null && /随机生成/.test(title)) {
    matches.push(view);
  }
  const text = viewText(view);
  if (text !== null && /随机/.test(text)) {
    texts.push({
      className: view.$className,
      text: text,
      parentControl: currentControl === null ? null : currentControl.$className,
      parentActions: currentControl === null ? [] : controlActions(currentControl)
    });
    if (currentControl !== null && matches.indexOf(currentControl) === -1) {
      matches.push(currentControl);
    }
  }
  const children = view.subviews();
  const count = Number(children.count());
  for (let i = 0; i < count; i++) {
    scanView(children.objectAtIndex_(i), matches, controls, texts, currentControl);
  }
}

setTimeout(function () {
  if (!ObjC.available) {
    out('ui-error', 'Objective-C unavailable');
    return;
  }
  ObjC.schedule(ObjC.mainQueue, function () {
    const app = ObjC.classes.UIApplication.sharedApplication();
    const windows = app.windows();
    const matches = [];
    const controls = [];
    const texts = [];
    for (let i = 0; i < Number(windows.count()); i++) {
      scanView(windows.objectAtIndex_(i), matches, controls, texts, null);
    }
    out('controls', controls);
    out('random-texts', texts);
    out('random-controls', matches.map(function (control) {
      return {
        className: control.$className,
        title: buttonTitle(control),
        targets: control.allTargets().toString(),
        actions: controlActions(control)
      };
    }));
    matches.forEach(function (control) {
      out('random-control-trigger', { title: buttonTitle(control) });
      control.sendActionsForControlEvents_(1 << 6);
    });
  });
}, 6000);
