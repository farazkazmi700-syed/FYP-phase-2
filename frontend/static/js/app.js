'use strict';

// Network calls: send chat messages and check server health.
const api = {
  async sendMessage(content, sessionId) {
    const res = await fetch('/chat/send', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ content, session_id: sessionId }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || `HTTP ${res.status}`);
    }
    return res.json();
  },

  async checkHealth() {
    const res = await fetch('/api/health', { credentials: 'include' });
    return res.json();
  },
};

// Rendering helpers: escape user text, format times, and draw chat messages.
const ui = {
  escapeHtml(value) {
    return String(value)
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#039;');
  },

  formatTime(iso) {
    if (!iso) return '';
    return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  },

  appendMessage(role, content, messageId, timestamp) {
    document.getElementById('welcome-message')?.remove();

    const container = document.getElementById('messages-container');
    const message = document.createElement('div');
    message.className = `message ${role}`;
    if (messageId) message.dataset.msgId = messageId;

    const isAssistant = role === 'assistant';
    message.innerHTML = `
      <div class="msg-avatar">${isAssistant ? '🤖' : 'You'}</div>
      <div class="msg-content">
        <div class="msg-bubble">${ui.escapeHtml(content).replaceAll('\n', '<br>')}</div>
        <div class="msg-meta">
          <span>${ui.formatTime(timestamp)}</span>
          ${isAssistant && messageId ? `<button class="btn-feedback-trigger" data-id="${messageId}">Feedback</button>` : ''}
        </div>
      </div>
    `;

    message.querySelector('.btn-feedback-trigger')?.addEventListener('click', event => {
      feedback.open(event.currentTarget.dataset.id);
    });

    container.appendChild(message);
    container.scrollTop = container.scrollHeight;
  },

  renderWelcome() {
    document.getElementById('messages-container').innerHTML = `
      <div class="welcome-message" id="welcome-message">
        <div class="welcome-icon">🤖</div>
        <h2>New Chat</h2>
        <p>Ask me anything. This page keeps only the current conversation.</p>
        <div class="suggestion-chips">
          <button class="chip" onclick="app.sendSuggestion('Explain machine learning in simple terms')">Machine learning</button>
          <button class="chip" onclick="app.sendSuggestion('Write a Python hello world program')">Python code</button>
          <button class="chip" onclick="app.sendSuggestion('Give me 3 tips for better writing')">Writing tips</button>
        </div>
      </div>
    `;
  },

  // Typing indicator: shown while waiting for the backend response.
  showTyping() {
    const container = document.getElementById('messages-container');
    const typing = document.createElement('div');
    typing.className = 'message assistant typing-indicator';
    typing.id = 'typing-indicator';
    typing.innerHTML = `
      <div class="msg-avatar">🤖</div>
      <div class="msg-content">
        <div class="msg-bubble">
          <span class="typing-dot"></span>
          <span class="typing-dot"></span>
          <span class="typing-dot"></span>
        </div>
      </div>
    `;
    container.appendChild(typing);
    container.scrollTop = container.scrollHeight;
  },

  hideTyping() {
    document.getElementById('typing-indicator')?.remove();
  },

  setConnectionStatus(online, text) {
    const dot = document.querySelector('.status-dot');
    const label = document.querySelector('.status-text');
    dot.className = `status-dot ${online ? 'online' : 'offline'}`;
    label.textContent = text;
  },
};

// Feedback action: opens the dedicated feedback page for one assistant message.
const feedback = {
  open(messageId) {
    const sessionParam = app.currentSessionId ? `&session_id=${encodeURIComponent(app.currentSessionId)}` : '';
    window.location.href = `/feedback?message_id=${encodeURIComponent(messageId)}${sessionParam}`;
  },
};

// Page controller: binds UI events and manages the active in-page conversation.
const app = {
  currentSessionId: null,
  isLoading: false,

  async init() {
    app.bindEvents();
    await app.checkConnection();
    app.autoResizeInput();
  },

  // Register button, keyboard, logout, and input-resize actions.
  bindEvents() {
    document.getElementById('btn-send').addEventListener('click', app.handleSend);
    document.getElementById('btn-new-chat').addEventListener('click', app.startNewChat);
    document.getElementById('btn-logout')?.addEventListener('click', app.handleLogout);
    document.getElementById('message-input').addEventListener('keydown', event => {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        app.handleSend();
      }
    });
  },

  autoResizeInput() {
    const input = document.getElementById('message-input');
    input.addEventListener('input', () => {
      input.style.height = 'auto';
      input.style.height = `${Math.min(input.scrollHeight, 160)}px`;
    });
  },

  // Send the user's message, render the reply, and keep the current session id.
  async handleSend() {
    const input = document.getElementById('message-input');
    const content = input.value.trim();
    if (!content || app.isLoading) return;

    app.isLoading = true;
    input.value = '';
    input.style.height = 'auto';
    document.getElementById('btn-send').disabled = true;
    ui.appendMessage('user', content, null, new Date().toISOString());
    ui.showTyping();

    try {
      const result = await api.sendMessage(content, app.currentSessionId);
      app.currentSessionId = result.session_id;
      ui.hideTyping();
      ui.appendMessage('assistant', result.response, result.message_id, result.timestamp);
    } catch (err) {
      ui.hideTyping();
      ui.appendMessage('assistant', `Error: ${err.message}. Please try again.`, null, new Date().toISOString());
    } finally {
      app.isLoading = false;
      document.getElementById('btn-send').disabled = false;
      input.focus();
    }
  },

  // Clear only the current screen conversation.
  startNewChat() {
    app.currentSessionId = null;
    ui.renderWelcome();
    document.getElementById('message-input').focus();
  },

  sendSuggestion(text) {
    document.getElementById('message-input').value = text;
    app.handleSend();
  },

  async checkConnection() {
    try {
      const result = await api.checkHealth();
      ui.setConnectionStatus(result.status === 'ok', result.status === 'ok' ? 'Connected' : 'Limited');
    } catch {
      ui.setConnectionStatus(false, 'Offline');
    }
  },

  handleLogout(event) {
    event.preventDefault();
    window.location.href = '/auth/logout';
  },
};

window.app = app;

document.addEventListener('DOMContentLoaded', () => app.init());
