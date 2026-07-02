/**
 * Preload hook: redirect require('zca-js') về fake_zca/index.js.
 *
 * Dùng: node --require <path>/hijack.js bridge.js
 * Cách này để bridge.js chạy nguyên bản mà không cần zca-js thật trong
 * node_modules (NODE_PATH không override được node_modules cạnh bridge.js).
 */

const Module = require('module');
const path = require('path');

const fakePath = path.join(__dirname, 'index.js');
const origResolve = Module._resolveFilename;

Module._resolveFilename = function (request, ...args) {
  if (request === 'zca-js') return fakePath;
  return origResolve.call(this, request, ...args);
};
