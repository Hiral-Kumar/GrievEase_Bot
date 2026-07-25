/**
 * Loads the REAL frontend/index.html into jsdom and drives it exactly like
 * a browser would (typing into inputs, clicking buttons), with `fetch`
 * mocked to return canned /api/chat responses instead of hitting a real
 * server. This catches DOM-wiring bugs (wrong element IDs, event listeners
 * not attached, state not updating) that a plain `node --check` syntax
 * check can't — while not depending on this sandbox's flaky localhost
 * networking.
 *
 * Run with: node frontend/test_widget.js
 */
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const html = fs.readFileSync(path.join(__dirname, "index.html"), "utf8");

let passed = 0, failed = 0;
function assert(cond, label) {
  if (cond) { passed++; console.log(`  OK   ${label}`); }
  else { failed++; console.log(`  FAIL ${label}`); }
}

async function run() {
  const fetchCalls = [];
  const dom = new JSDOM(html, {
    runScripts: "dangerously",
    resources: "usable",
    url: "http://localhost/",
  });
  const { window } = dom;

  // Mock fetch: simulate the real /api/chat behavior for the scenario we
  // drive below (greeting -> implicit complaint -> location -> email ->
  // confirm), without needing a live server.
  let turn = 0;
  const scriptedReplies = [
    { session_id: "sess-abc-123", reply: "Hi! I'm GrievEase Bot...", done: false, escalated: false, ticket_id: null },
    { session_id: "sess-abc-123", reply: "I'll file this under Hostel. Location?", done: false, escalated: false, ticket_id: null },
    { session_id: "sess-abc-123", reply: "Shall I submit this? (yes/no)", done: false, escalated: false, ticket_id: null },
    { session_id: "sess-abc-123", reply: "Your grievance has been submitted. Your Ticket ID is GBU-2026-999111.", done: true, escalated: false, ticket_id: "GBU-2026-999111" },
  ];

  window.fetch = async (url, options) => {
    const body = JSON.parse(options.body);
    fetchCalls.push({ url, body });
    const reply = scriptedReplies[Math.min(turn, scriptedReplies.length - 1)];
    turn++;
    return {
      ok: true,
      json: async () => reply,
      text: async () => JSON.stringify(reply),
    };
  };

  // Wait for the inline <script> to finish attaching listeners.
  await new Promise((resolve) => window.setTimeout(resolve, 50));

  const doc = window.document;
  const idInput = doc.getElementById("studentIdInput");
  const startBtn = doc.getElementById("startBtn");
  const messageInput = doc.getElementById("messageInput");
  const sendBtn = doc.getElementById("sendBtn");
  const idGate = doc.getElementById("idGate");
  const inputRow = doc.getElementById("inputRow");

  console.log("Scenario: enter student ID, greet, submit an implicit complaint\n");

  // --- Step 1: enter student ID and start ---
  idInput.value = "GBU2023CS101";
  startBtn.click();
  await new Promise((resolve) => window.setTimeout(resolve, 20));

  assert(fetchCalls.length === 1, "clicking Start triggers exactly one /api/chat call");
  assert(fetchCalls[0].body.message === "hi", "first call sends the greeting message 'hi'");
  assert(fetchCalls[0].body.student_id === "GBU2023CS101", "first call includes the entered student ID");
  assert(idGate.classList.contains("hidden"), "ID gate is hidden after starting");
  assert(inputRow.style.display === "flex", "chat input row is shown after starting");
  assert(doc.querySelectorAll(".bubble.bot").length === 1, "bot's greeting reply is rendered as a bubble");

  // --- Step 2: implicit complaint ---
  messageInput.value = "My hostel wifi has not worked for a week";
  sendBtn.click();
  await new Promise((resolve) => window.setTimeout(resolve, 20));

  assert(fetchCalls.length === 2, "sending a message triggers a second /api/chat call");
  assert(fetchCalls[1].body.session_id === "sess-abc-123", "second call reuses the session_id from the first response");
  assert(fetchCalls[1].body.message === "My hostel wifi has not worked for a week", "second call sends the typed message");
  assert(messageInput.value === "", "input box clears after sending");
  assert(doc.querySelectorAll(".bubble.user").length === 1, "user's message is rendered as a bubble");
  assert(doc.querySelectorAll(".bubble.bot").length === 2, "bot's second reply is rendered as a bubble");

  // --- Step 3: location ---
  messageInput.value = "Block C, Room 214";
  messageInput.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Enter" }));
  await new Promise((resolve) => window.setTimeout(resolve, 20));
  assert(fetchCalls.length === 3, "pressing Enter (not just clicking) also sends a message");
  assert(fetchCalls[2].body.session_id === "sess-abc-123", "third call still reuses the same session_id");

  // --- Step 4: confirm -> ticket created ---
  messageInput.value = "yes";
  sendBtn.click();
  await new Promise((resolve) => window.setTimeout(resolve, 20));

  const lastBubble = doc.querySelectorAll(".bubble.bot.ticket");
  assert(lastBubble.length === 1, "final reply with a ticket_id gets the 'ticket' styling class");
  assert(doc.querySelector(".badge.ticket").textContent.includes("GBU-2026-999111"),
    "ticket badge displays the actual ticket ID from the response");

  // --- Escalation styling check (separate quick scenario) ---
  fetchCalls.length = 0;
  turn = 0;
  scriptedReplies.length = 0;
  scriptedReplies.push({
    session_id: "sess-esc-1", reply: "Connecting you with staff.",
    done: true, escalated: true, ticket_id: null,
  });
  messageInput.value = "someone is harassing me";
  sendBtn.click();
  await new Promise((resolve) => window.setTimeout(resolve, 20));
  assert(doc.querySelectorAll(".bubble.bot.escalated").length === 1,
    "an escalated response gets the 'escalated' styling class");
  assert(doc.querySelector(".badge.escalated") !== null, "escalated badge is rendered");

  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed > 0 ? 1 : 0);
}

run();
