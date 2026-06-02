// State
let state = {
  asUid: "",
  activeChatId: "",
  users: [],
  chats: [],
  messagesByChat: {},  // chatId -> [{kind, sender_id, sender_name, text, ts}]
  eventSource: null,
};

// --- DOM refs ---
const $ = (id) => document.getElementById(id);
const asSelect = $("as-select");
const chatList = $("chat-list");
const messages = $("messages");
const msgInput = $("msg-input");
const mentionBot = $("mention-bot");
const btnSend = $("btn-send");
const btnAddUser = $("btn-add-user");
const btnAddGroup = $("btn-add-group");
const btnAdmin = $("btn-admin");
const adminPane = $("admin-pane");
const chatHeader = $("chat-header").querySelector("h2");

// --- HTTP helpers ---
async function api(path, opts = {}) {
  const r = await fetch(`/test${path}`, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.status === 204 ? null : r.json();
}

// --- Render ---
function renderUsers() {
  asSelect.innerHTML = '<option value="">-- chọn user --</option>' +
    state.users.map(u => `<option value="${u.id}" ${u.id === state.asUid ? "selected" : ""}>${u.name}${u.is_boss ? " ★" : ""}</option>`).join("");
}

function renderChats() {
  chatList.innerHTML = state.chats.map(c => `
    <li class="chat-item px-3 py-2 cursor-pointer hover:bg-gray-50 ${c.chat_id === state.activeChatId ? "active" : ""}"
        data-id="${c.chat_id}">
      ${c.kind === "dm" ? "☆" : "#"} ${c.name}
    </li>
  `).join("");
  chatList.querySelectorAll(".chat-item").forEach(li => {
    li.onclick = () => selectChat(li.dataset.id);
  });
}

function renderMessages() {
  const msgs = state.messagesByChat[state.activeChatId] || [];
  messages.innerHTML = msgs.map(m => {
    const klass = m.sender_kind === "bot" ? "bubble-bot"
      : m.sender_id === state.asUid ? "bubble-self" : "bubble-other";
    return `
      <li class="flex flex-col">
        <div class="${klass} max-w-[70%] px-3 py-2 rounded inline-block">
          <div class="text-xs text-gray-500">${m.sender_name || "?"}</div>
          <div>${escapeHtml(m.text || "")}</div>
        </div>
      </li>
    `;
  }).join("");
  messages.scrollTop = messages.scrollHeight;
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}

// --- Actions ---
async function loadUsers() {
  state.users = await api("/api/users");
  renderUsers();
}

async function loadChats() {
  if (!state.asUid) { state.chats = []; renderChats(); return; }
  state.chats = await api(`/api/chats?as=${state.asUid}`);
  renderChats();
}

async function selectChat(chatId) {
  state.activeChatId = chatId;
  const chat = state.chats.find(c => c.chat_id === chatId);
  chatHeader.textContent = chat ? `${chat.kind === "dm" ? "☆" : "#"} ${chat.name}` : "—";
  // Replay
  const msgs = await api(`/api/chats/${encodeURIComponent(chatId)}/messages?limit=50`);
  state.messagesByChat[chatId] = msgs.map(m => ({
    sender_kind: m.kind === "out" ? "bot" : "user",
    sender_id: m.sender_id,
    sender_name: m.sender_name,
    text: m.text,
    ts: m.ts,
  }));
  renderChats();
  renderMessages();
}

async function send() {
  const text = msgInput.value.trim();
  if (!text || !state.asUid || !state.activeChatId) return;
  msgInput.value = "";
  await api("/api/send", {
    method: "POST",
    body: JSON.stringify({
      as: state.asUid,
      chat_id: state.activeChatId,
      text,
      mention_bot: mentionBot.checked,
    }),
  });
  // Don't optimistic-append — wait for SSE echo via fanout/adapter
}

function connectSSE() {
  if (state.eventSource) { state.eventSource.close(); }
  if (!state.asUid) return;
  state.eventSource = new EventSource(`/test/stream?as=${state.asUid}`);
  state.eventSource.onmessage = (ev) => {
    const data = JSON.parse(ev.data);
    if (data.kind !== "message") return;
    const list = state.messagesByChat[data.chat_id] || (state.messagesByChat[data.chat_id] = []);
    list.push(data);
    if (data.chat_id === state.activeChatId) renderMessages();
  };
}

// --- Setup ---
asSelect.onchange = async () => {
  state.asUid = asSelect.value;
  history.replaceState(null, "", state.asUid ? `?as=${state.asUid}` : "/test/");
  state.activeChatId = "";
  await loadChats();
  connectSSE();
};

btnSend.onclick = send;
msgInput.onkeydown = (e) => { if (e.key === "Enter") send(); };

btnAddUser.onclick = async () => {
  const name = prompt("Tên user:");
  if (!name) return;
  const isBoss = confirm("Là boss?");
  await api("/api/users", { method: "POST", body: JSON.stringify({ name, is_boss: isBoss }) });
  await loadUsers();
};

btnAddGroup.onclick = async () => {
  const name = prompt("Tên group:");
  if (!name) return;
  const memberCsv = prompt("CSV web_user_id thành viên (vd: u-aaa,u-bbb):") || "";
  const member_ids = memberCsv.split(",").map(s => s.trim()).filter(Boolean);
  await api("/api/groups", { method: "POST", body: JSON.stringify({ name, member_ids }) });
  await loadChats();
};

btnAdmin.onclick = () => { adminPane.classList.toggle("hidden"); };

// Init
const params = new URLSearchParams(location.search);
state.asUid = params.get("as") || "";
loadUsers().then(loadChats).then(connectSSE);
