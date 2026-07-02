/**
 * Fake zca-js — stub module cho contract test của bridge.js.
 *
 * bridge.js chạy NGUYÊN BẢN; hijack.js redirect require('zca-js') về file này.
 * Kịch bản đọc từ $FAKE_ZCA_SCENARIO (JSON):
 *   {
 *     "own_id": "999",
 *     "messages": [ <raw zca-js message objects, emit sau listener.start()> ],
 *     "groups": { "<gid>": { "memVerList": ["<uid>_<ver>", ...] } },
 *     "listener_error": "reason"   // optional: fire onError sau khi emit messages
 *   }
 * Mọi API call phía stub ghi 1 dòng JSON vào $FAKE_ZCA_OUT để test assert
 * bridge gọi đúng API với đúng tham số.
 */

const fs = require('fs');

const ThreadType = { User: 0, Group: 1 };

function out(record) {
  const p = process.env.FAKE_ZCA_OUT;
  if (p) fs.appendFileSync(p, JSON.stringify(record) + '\n');
}

function loadScenario() {
  const p = process.env.FAKE_ZCA_SCENARIO;
  if (!p) return { own_id: '999', messages: [], groups: {} };
  return JSON.parse(fs.readFileSync(p, 'utf8'));
}

class FakeListener {
  constructor(sc) {
    this._sc = sc;
    this._onMessage = null;
    this._onError = null;
  }
  onMessage(cb) {
    this._onMessage = cb;
  }
  onError(cb) {
    this._onError = cb;
  }
  start() {
    out({ api: 'listener.start' });
    // Delay nhỏ để event 'ready' của bridge ra trước message — khớp thứ tự thật.
    setTimeout(() => {
      for (const m of this._sc.messages || []) {
        if (this._onMessage) this._onMessage(m);
      }
      if (this._sc.listener_error && this._onError) {
        this._onError(new Error(this._sc.listener_error));
      }
    }, 20);
  }
}

let sendSeq = 0;

class FakeApi {
  constructor(sc) {
    this._sc = sc;
    this.listener = new FakeListener(sc);
  }
  async getOwnId() {
    return this._sc.own_id || '999';
  }
  async sendMessage(payload, threadId, threadType) {
    out({
      api: 'sendMessage',
      msg: payload && payload.msg,
      threadId: String(threadId),
      thread_type: threadType,
    });
    if (this._sc.send_error) throw new Error(this._sc.send_error);
    sendSeq += 1;
    return { msgId: `sent-${sendSeq}` };
  }
  async getGroupInfo(ids) {
    out({ api: 'getGroupInfo', ids });
    const gridInfoMap = {};
    for (const gid of ids) {
      const g = (this._sc.groups || {})[gid];
      if (g) gridInfoMap[gid] = g;
    }
    return { gridInfoMap };
  }
}

class Zalo {
  constructor(opts) {
    out({ api: 'constructor', opt_keys: Object.keys(opts || {}).sort() });
  }
  async login(creds) {
    out({
      api: 'login',
      has_cookie: !!(creds && creds.cookie),
      imei: creds && creds.imei,
    });
    return new FakeApi(loadScenario());
  }
}

module.exports = { Zalo, ThreadType };
