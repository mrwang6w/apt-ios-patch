'use strict';

function location(address) {
  const module = Process.findModuleByAddress(address);
  const symbol = DebugSymbol.fromAddress(address);
  return {
    address: address.toString(),
    module: module === null ? null : module.name,
    offset: module === null ? null : '0x' + address.sub(module.base).toString(16),
    symbol: symbol === null ? null : symbol.toString()
  };
}

const threads = Process.enumerateThreads();
const thread = threads[0];
let frames = [];
let error = null;
try {
  frames = Thread.backtrace(thread.context, Backtracer.FUZZY)
    .slice(0, 48)
    .map(location);
} catch (exception) {
  error = String(exception);
}
console.log(JSON.stringify({
  kind: 'main-thread',
  data: {
    threadCount: threads.length,
    id: thread.id,
    name: thread.name || null,
    state: thread.state,
    error: error,
    frames: frames
  }
}));
