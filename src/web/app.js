"use strict";
const el = id => document.getElementById(id);
let cursor = null;
let loading = false;
function stamp(data) {
  if (data.instance) el("instance").textContent = data.instance;
  if (data.node) el("node").textContent = `节点：${data.node} · v${data.version}`;
}
async function api(path, options = {}) {
  const response = await fetch(`/api/${path}`, {...options, cache: "no-store"});
  const data = await response.json();
  stamp(data);
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "请检查输入内容后重试。");
  el("status").textContent = "服务已连接";
  el("status-dot").className = "ready";
  return data;
}
function fail(error) {
  el("notice").textContent = error.message || "网络连接失败，请稍后重试。";
  el("notice").className = "error";
  el("status").textContent = "请求失败";
  el("status-dot").className = "";
}
function message(item) {
  const article = document.createElement("article");
  article.className = "message";
  const head = document.createElement("div");
  head.className = "message-head";
  const avatar = document.createElement("span");
  avatar.className = "avatar";
  avatar.textContent = Array.from(item.author)[0];
  const author = document.createElement("span");
  author.className = "message-author";
  author.textContent = item.author;
  const time = document.createElement("time");
  time.dateTime = item.created_at;
  time.textContent = new Date(item.created_at).toLocaleString("zh-CN", {month:"short",day:"numeric",hour:"2-digit",minute:"2-digit"});
  head.append(avatar, author, time);
  const content = document.createElement("p");
  content.className = "message-content";
  content.textContent = item.content;
  const id = document.createElement("span");
  id.className = "message-id";
  id.textContent = `#${String(item.id).padStart(3,"0")}`;
  article.append(head, content, id);
  return article;
}
async function list(append = false) {
  if (loading) return;
  loading = true;
  el("refresh").disabled = el("load-more").disabled = true;
  try {
    const data = await api(`messages?limit=10${append && cursor ? `&before=${cursor}` : ""}`);
    if (!append) el("message-list").replaceChildren();
    el("total").textContent = data.total;
    if (!append && data.items.length === 0) {
      const empty = document.createElement("p");
      empty.className = "empty";
      const title = document.createElement("strong");
      title.textContent = "你好，新的一页。";
      empty.append(title, "写下第一条留言，让这里热闹起来。");
      el("message-list").append(empty);
    }
    data.items.forEach(item => el("message-list").append(message(item)));
    cursor = data.next_cursor;
    el("load-more").hidden = !cursor;
  } catch (error) { fail(error); }
  finally { loading = false; el("refresh").disabled = el("load-more").disabled = false; }
}
el("content").addEventListener("input", () => { el("char-count").textContent = `${el("content").value.length} / 300`; });
el("message-form").addEventListener("submit", async event => {
  event.preventDefault();
  const author = el("author").value.trim(), content = el("content").value.trim();
  if (!author || !content) { fail(new Error("名字和留言内容不能只包含空格。")); return; }
  el("submit").disabled = true;
  try {
    await api("messages", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({author,content})});
    el("content").value = "";
    el("char-count").textContent = "0 / 300";
    el("notice").className = "";
    el("notice").textContent = "留言已发布。谢谢你的分享！";
    await list();
  } catch (error) { fail(error); }
  finally { el("submit").disabled = false; }
});
el("refresh").addEventListener("click", () => list());
el("load-more").addEventListener("click", () => list(true));
el("refresh-instance").addEventListener("click", () => api("whoami").catch(fail));
(async () => {
  try {
    const data = await api("whoami");
    document.title = el("title").textContent = data.title;
    const visit = await api("visits", {method:"POST"});
    el("visits").textContent = visit.count;
  } catch (error) { fail(error); }
  await list();
})();
