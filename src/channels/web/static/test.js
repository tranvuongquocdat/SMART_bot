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
const btnSend = $("btn-send");
const btnAddUser = $("btn-add-user");
const btnAddGroup = $("btn-add-group");
const btnAdmin = $("btn-admin");
const adminPane = $("admin-pane");
const adminUsersUl = $("admin-users");
const adminGroupsUl = $("admin-groups");
const chatHeader = $("chat-header").querySelector("h2");

// Detect `@bot` anywhere in the message (case-insensitive, word boundary).
// Replaces the old explicit checkbox — typing @bot naturally tags the bot.
const MENTION_BOT_RE = /(?:^|\s)@bot\b/i;

// Modals
const userModal = $("user-modal");
const userModalName = $("user-modal-name");
const userModalOk = $("user-modal-ok");
const userModalCancel = $("user-modal-cancel");
const groupModal = $("group-modal");
const groupModalName = $("group-modal-name");
const groupModalMembers = $("group-modal-members");
const groupModalOk = $("group-modal-ok");
const groupModalCancel = $("group-modal-cancel");

// IME composition state — prevent Enter from sending while user is mid-composition
// (Vietnamese Telex/VNI commit on space/enter, which previously fired send twice).
let isComposing = false;

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
      mention_bot: MENTION_BOT_RE.test(text),
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
msgInput.addEventListener("compositionstart", () => { isComposing = true; });
msgInput.addEventListener("compositionend", () => { isComposing = false; });
msgInput.addEventListener("keydown", (e) => {
  // Skip Enter while IME is composing (Vietnamese Telex/VNI),
  // and also when browser reports a composition keycode (Safari quirk).
  if (e.key === "Enter" && !e.shiftKey && !isComposing && !e.isComposing && e.keyCode !== 229) {
    e.preventDefault();
    send();
  }
});

// --- User create modal ---
function openUserModal() {
  userModalName.value = "";
  userModal.querySelectorAll('input[name="user-role"]').forEach(r => {
    r.checked = r.value === "employee";
  });
  userModal.classList.remove("hidden");
  setTimeout(() => userModalName.focus(), 0);
}
function closeUserModal() { userModal.classList.add("hidden"); }
async function submitUserModal() {
  const name = userModalName.value.trim();
  if (!name) { userModalName.focus(); return; }
  const role = userModal.querySelector('input[name="user-role"]:checked').value;
  await api("/api/users", { method: "POST", body: JSON.stringify({ name, is_boss: role === "boss" }) });
  closeUserModal();
  await loadUsers();
}
btnAddUser.onclick = openUserModal;
userModalCancel.onclick = closeUserModal;
userModalOk.onclick = submitUserModal;
userModalName.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !isComposing && !e.isComposing && e.keyCode !== 229) {
    e.preventDefault(); submitUserModal();
  } else if (e.key === "Escape") { closeUserModal(); }
});

// --- Group create modal ---
function openGroupModal() {
  groupModalName.value = "";
  groupModalMembers.innerHTML = state.users.length
    ? state.users.map(u => `
        <li class="flex items-center gap-2 px-2 py-1 hover:bg-gray-50">
          <input type="checkbox" value="${u.id}" id="gm-${u.id}" />
          <label for="gm-${u.id}" class="flex-1 cursor-pointer">${escapeHtml(u.name)}${u.is_boss ? " ★" : ""}</label>
        </li>
      `).join("")
    : '<li class="px-2 py-2 text-gray-400">Chưa có user nào — tạo user trước.</li>';
  groupModal.classList.remove("hidden");
  setTimeout(() => groupModalName.focus(), 0);
}
function closeGroupModal() { groupModal.classList.add("hidden"); }
async function submitGroupModal() {
  const name = groupModalName.value.trim();
  if (!name) { groupModalName.focus(); return; }
  const member_ids = [...groupModalMembers.querySelectorAll('input[type="checkbox"]:checked')]
    .map(c => c.value);
  await api("/api/groups", { method: "POST", body: JSON.stringify({ name, member_ids }) });
  closeGroupModal();
  await loadChats();
}
btnAddGroup.onclick = openGroupModal;
groupModalCancel.onclick = closeGroupModal;
groupModalOk.onclick = submitGroupModal;
groupModalName.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !isComposing && !e.isComposing && e.keyCode !== 229) {
    e.preventDefault(); submitGroupModal();
  } else if (e.key === "Escape") { closeGroupModal(); }
});

// --- Admin pane (user/group delete) ---
async function renderAdminPane() {
  // Users
  adminUsersUl.innerHTML = state.users.length
    ? state.users.map(u => `
        <li class="flex items-center justify-between px-2 py-1">
          <span class="truncate">${escapeHtml(u.name)}${u.is_boss ? " ★" : ""}</span>
          <button data-uid="${u.id}" class="admin-del-user text-red-600 hover:bg-red-50 px-2 rounded" title="Xoá user">×</button>
        </li>
      `).join("")
    : '<li class="px-2 py-1 text-gray-400">Chưa có user</li>';
  adminUsersUl.querySelectorAll(".admin-del-user").forEach(btn => {
    btn.onclick = async () => {
      const uid = btn.dataset.uid;
      const u = state.users.find(x => x.id === uid);
      if (!confirm(`Xoá user "${u?.name || uid}"?`)) return;
      try {
        await api(`/api/users/${encodeURIComponent(uid)}`, { method: "DELETE" });
      } catch (e) {
        alert(`Không xoá được: ${e.message}`);
        return;
      }
      if (state.asUid === uid) {
        state.asUid = "";
        history.replaceState(null, "", "/test/");
      }
      await loadUsers();
      await loadChats();
      await renderAdminPane();
    };
  });

  // Groups — list_groups returns [{id, name, members[]}]
  let groups = [];
  try {
    groups = await api("/api/groups");
  } catch (e) {
    groups = [];
  }
  adminGroupsUl.innerHTML = groups.length
    ? groups.map(g => `
        <li class="flex items-center justify-between px-2 py-1">
          <span class="truncate">${escapeHtml(g.name)}</span>
          <button data-gid="${g.id}" class="admin-del-group text-red-600 hover:bg-red-50 px-2 rounded" title="Xoá group">×</button>
        </li>
      `).join("")
    : '<li class="px-2 py-1 text-gray-400">Chưa có group</li>';
  adminGroupsUl.querySelectorAll(".admin-del-group").forEach(btn => {
    btn.onclick = async () => {
      const gid = btn.dataset.gid;
      const g = groups.find(x => x.id === gid);
      if (!confirm(`Xoá group "${g?.name || gid}"?`)) return;
      try {
        await api(`/api/groups/${encodeURIComponent(gid)}`, { method: "DELETE" });
      } catch (e) {
        alert(`Không xoá được: ${e.message}`);
        return;
      }
      await loadChats();
      await renderAdminPane();
    };
  });
}

btnAdmin.onclick = async () => {
  const opening = adminPane.classList.contains("hidden");
  adminPane.classList.toggle("hidden");
  if (opening) await renderAdminPane();
};

// Init
const params = new URLSearchParams(location.search);
state.asUid = params.get("as") || "";
loadUsers().then(loadChats).then(connectSSE);
