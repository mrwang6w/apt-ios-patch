#!/usr/bin/env python3
import frida, sys, time, json, traceback
APP_ID = sys.argv[1] if len(sys.argv) > 1 else 'Razer'
WAIT = float(sys.argv[2]) if len(sys.argv) > 2 else 12.0
js = r'''
'use strict';
function log(s) { send({type:'log', text:String(s)}); }
function bt(ctx) {
  try { return Thread.backtrace(ctx, Backtracer.ACCURATE).map(DebugSymbol.fromAddress).join('\n'); }
  catch (e) { return 'bt-error: ' + e; }
}
function hookExport(name, retlog) {
  var p = Module.findGlobalExportByName(name);
  if (!p) { log('export not found: ' + name); return; }
  log('hook ' + name + ' @ ' + p);
  Interceptor.attach(p, {
    onEnter: function(args) {
      log('ENTER ' + name + '\n' + bt(this.context));
      if (name === 'dlopen' || name === 'dlopen_from') {
        try { log(name + ' path=' + args[0].readCString()); } catch (e) {}
      }
    },
    onLeave: function(retval) { if (retlog) log('LEAVE ' + name + ' => ' + retval); }
  });
}
['abort','exit','_exit','kill','pthread_kill','objc_exception_throw','dlopen'].forEach(function(n){ hookExport(n, n === 'dlopen'); });
// dyld4 private symbol usually not exported as global; enumerate dyld symbols for dlopen_from.
try {
  Process.enumerateModules().forEach(function(m) {
    if (m.name === 'dyld') {
      m.enumerateSymbols().forEach(function(s) {
        if (s.name.indexOf('dlopen_from') !== -1) {
          log('hook dyld symbol ' + s.name + ' @ ' + s.address);
          Interceptor.attach(s.address, { onEnter: function(args){ log('ENTER '+s.name+'\n'+bt(this.context)); try{log('dlopen_from path='+args[0].readCString());}catch(e){} } });
        }
      });
    }
  });
} catch (e) { log('dyld enumerate error: ' + e); }
setImmediate(function() {
  log('Frida probe loaded; arch=' + Process.arch + ' pid=' + Process.id);
  try {
    Process.enumerateModules().forEach(function(m) {
      if (/Razer|razer|ElleKit|Substrate|TweakInject|systemhook|inject/i.test(m.name + ' ' + m.path)) {
        log('module ' + m.name + ' base=' + m.base + ' size=' + m.size + ' path=' + m.path);
      }
    });
  } catch (e) { log('module list error: ' + e); }
});
'''
logs=[]
def on_message(message, data):
    ts=time.strftime('%Y-%m-%d %H:%M:%S')
    if message.get('type') == 'send':
        payload=message.get('payload')
        line=f"[{ts}] {payload.get('text') if isinstance(payload, dict) else payload}"
    else:
        line=f"[{ts}] MESSAGE {json.dumps(message, ensure_ascii=False)}"
    print(line, flush=True)
    logs.append(line)

def on_detached(reason, crash):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] DETACHED reason={reason} crash={crash}", flush=True)

try:
    dev = frida.get_usb_device(timeout=5)
    print(f"device={dev}", flush=True)
    pid = dev.spawn([APP_ID])
    print(f"spawned {APP_ID} pid={pid}", flush=True)
    sess = dev.attach(pid)
    sess.on('detached', on_detached)
    script = sess.create_script(js)
    script.on('message', on_message)
    script.load()
    print('resume', flush=True)
    dev.resume(pid)
    t0=time.time()
    while time.time()-t0 < WAIT:
        time.sleep(0.25)
    print('done-wait', flush=True)
    try: sess.detach()
    except Exception as e: print('detach-error', e, flush=True)
except Exception as e:
    print('PYERROR', repr(e), flush=True)
    traceback.print_exc()
    sys.exit(2)
