"use strict";

if (!ObjC.available) {
  console.log("ObjC runtime unavailable");
} else {
  function describe(pointer) {
    try {
      return new ObjC.Object(pointer).toString();
    } catch (_) {
      return "<" + pointer + ">";
    }
  }

  function backtrace(context) {
    return Thread.backtrace(context, Backtracer.ACCURATE)
      .map(DebugSymbol.fromAddress)
      .join("\n    ");
  }

  function hook(className, selector, callbacks) {
    const klass = ObjC.classes[className];
    if (!klass || !klass[selector]) {
      console.log("[miss] " + className + " " + selector);
      return;
    }
    Interceptor.attach(klass[selector].implementation, callbacks);
    console.log(
      "[hook] " + className + " " + selector + " @ " +
        klass[selector].implementation
    );
  }

  let generatorClass = null;
  Object.keys(ObjC.classes).some(function (className) {
    const klass = ObjC.classes[className];
    try {
      if (klass["- randomStringWithLength:"]) {
        generatorClass = className;
        return true;
      }
    } catch (_) {}
    return false;
  });

  console.log("[generator-class] " + generatorClass);
  if (generatorClass) {
    hook(generatorClass, "- randomStringWithLength:", {
      onEnter(args) {
        this.length = args[2].toInt32();
        this.callstack = backtrace(this.context);
      },
      onLeave(retval) {
        console.log(
          "\n[RANDOM] length=" + this.length + " value=" + describe(retval) +
            "\n    " + this.callstack
        );
      },
    });
  }

  hook("MainViewController", "- newMachine:", {
    onEnter(args) {
      console.log(
        "\n[NEW-MACHINE enter] self=" + describe(args[0]) +
          " sender=" + describe(args[2]) + "\n    " + backtrace(this.context)
      );
    },
    onLeave(retval) {
      console.log("[NEW-MACHINE leave] retval=" + retval);
    },
  });

  hook("MainViewController", "- setDictRandomInfo:", {
    onEnter(args) {
      console.log(
        "\n[SET-RANDOM-INFO] " + describe(args[2]) +
          "\n    " + backtrace(this.context)
      );
    },
  });

  hook("DeviceInfoViewController", "- setDictDeviceInfo:", {
    onEnter(args) {
      console.log(
        "\n[SET-DEVICE-INFO] " + describe(args[2]) +
          "\n    " + backtrace(this.context)
      );
    },
  });

  ["__NSDictionaryM", "__NSFrozenDictionaryM"].forEach(function (className) {
    [
      "- setObject:forKey:",
      "- setObject:forKeyedSubscript:",
      "- setValue:forKey:",
    ].forEach(function (selector) {
      hook(className, selector, {
        onEnter(args) {
          const key = describe(args[3]);
          if (key.toLowerCase().indexOf("devicetoken") !== -1) {
            console.log(
              "\n[DICT-WRITE] " + className + " " + selector +
                " key=" + key + " value=" + describe(args[2]) +
                "\n    " + backtrace(this.context)
            );
          }
        },
      });
    });
  });

  hook("NSUserDefaults", "- setObject:forKey:", {
    onEnter(args) {
      const key = describe(args[3]);
      if (key.toLowerCase().indexOf("devicetoken") !== -1) {
        console.log(
          "\n[DEFAULTS-WRITE] key=" + key + " value=" + describe(args[2]) +
            "\n    " + backtrace(this.context)
        );
      }
    },
  });

  console.log("[ready] click 创建实例");
}
