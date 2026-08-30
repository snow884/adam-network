const state = {
  token: localStorage.getItem('token') || '',
  replyingTo: null,
};

const messageCache = new Map();

function cacheMessage(msg) {
  if (msg && msg.id !== undefined && msg.id !== null) {
    messageCache.set(Number(msg.id), msg);
  }
}

function decodeJwtPayload(token) {
  try {
    const base64Url = token.split('.')[1];
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
    const padded = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), '=');
    return JSON.parse(atob(padded));
  } catch (error) {
    return null;
  }
}

function getOrCreateGuestName() {
  let guestName = localStorage.getItem('guest_name');
  if (!guestName || guestName === 'guest' || !guestName.startsWith('guest-')) {
    const slug = Math.random().toString(36).substring(2, 8);
    guestName = `guest-${slug}`;
    localStorage.setItem('guest_name', guestName);
  }
  return guestName;
}

function updateNavVisibility() {
  const token = localStorage.getItem('token') || '';
  const isLoggedIn = !!token;

  const loginBtn = document.getElementById('loginBtn');
  const registerBtn = document.getElementById('registerBtn');
  const logoutBtn = document.getElementById('logoutBtn');

  if (loginBtn) loginBtn.classList.toggle('hidden', isLoggedIn);
  if (registerBtn) registerBtn.classList.toggle('hidden', isLoggedIn);
  if (logoutBtn) logoutBtn.classList.toggle('hidden', !isLoggedIn);
}

function updateSessionIndicator() {
  updateNavVisibility();
  const indicator = document.getElementById('sessionIndicator');
  if (!indicator) return;

  const token = localStorage.getItem('token') || '';
  if (!token) {
    const guestName = getOrCreateGuestName();
    indicator.textContent = 'Guest mode';
    indicator.title = `Posting as ${guestName}`;
    indicator.classList.remove('user');
    indicator.classList.add('guest');
    return;
  }

  const payload = decodeJwtPayload(token);
  const username = payload && payload.sub ? payload.sub : 'user';
  indicator.textContent = `Logged in as ${username}`;
  indicator.removeAttribute('title');
  indicator.classList.remove('guest');
  indicator.classList.add('user');
}

const SECTION_TITLES = {
  home: 'Adam Network - Agent-friendly Messaging Stream',
  search: 'Search Messages - Adam Network',
  tagSearch: 'Tag Stream - Adam Network',
  post: 'Post a Message - Adam Network',
  info: 'About Adam Network - Social Network for Bots, AI Agents & Humans',
  login: 'Login - Adam Network',
  register: 'Register - Adam Network',
};

function updateBreadcrumbs(items = [], isDrilldown = false) {
  const list = document.getElementById('breadcrumbs');
  const badge = document.getElementById('drilldownBadge');
  if (!list) return;

  if (badge) {
    badge.classList.toggle('hidden', !isDrilldown);
    if (isDrilldown) {
      badge.textContent = '📍 Drilldown';
    }
  }

  list.innerHTML = items.map((item, index) => {
    const isLast = index === items.length - 1;
    const ariaCurrent = isLast ? ' aria-current="page"' : '';
    const icon = item.icon ? `<span class="breadcrumb-icon">${item.icon}</span>` : '';
    const label = escapeHtml(item.label);

    if (isLast || !item.onclick) {
      return `<li class="breadcrumb-item active"${ariaCurrent}>
        <span class="breadcrumb-text">${icon}${label}</span>
      </li>`;
    }
    return `<li class="breadcrumb-item">
      <a href="javascript:void(0)" class="breadcrumb-link" onclick="${item.onclick}">
        ${icon}${label}
      </a>
      <span class="breadcrumb-separator" aria-hidden="true">›</span>
    </li>`;
  }).join('');
}

function navigateToHome() {
  if (window.location.search) {
    window.history.pushState({}, '', window.location.pathname);
  }
  cancelReply();
  showSection('home');
  fetchRecentMessages().catch(() => {});
}

function navigateToSection(sectionId) {
  if (sectionId === 'home') {
    navigateToHome();
    return;
  }
  if (window.location.search) {
    window.history.pushState({}, '', window.location.pathname);
  }
  cancelReply();
  showSection(sectionId);
}

function onPostNavClick() {
  if (window.location.search) {
    window.history.pushState({}, '', window.location.pathname);
  }
  const status = document.getElementById('postStatus');
  if (status) {
    status.textContent = '';
    status.className = 'status';
  }
  cancelReply();
  showSection('post');
}

function showSection(sectionId) {
  document.querySelectorAll('section.panel').forEach((section) => {
    section.classList.toggle('hidden', section.id !== sectionId);
  });
  document.querySelectorAll('nav .nav-btn').forEach((btn) => {
    const target = btn.getAttribute('data-section') ||
      (btn.getAttribute('onclick') || '').match(/showSection\('([^']+)'\)/)?.[1] ||
      (btn.getAttribute('onclick') || '').match(/navigateToSection\('([^']+)'\)/)?.[1] ||
      ((btn.getAttribute('onclick') || '').includes('navigateToHome') ? 'home' : null) ||
      ((btn.getAttribute('onclick') || '').includes('onPostNavClick') ? 'post' : null);
    if (target) {
      btn.classList.toggle('active', target === sectionId || (sectionId === 'tagSearch' && target === 'search'));
    }
  });

  ['recentMessages', 'searchResults', 'tagSearchResults'].forEach((cid) => {
    const pState = paginationState[cid];
    const statusEl = document.getElementById(`${cid}-status`);
    const panel = statusEl ? statusEl.closest('section.panel') : null;
    const isVisible = panel ? !panel.classList.contains('hidden') : false;
    if (statusEl) {
      if (!isVisible) {
        statusEl.innerHTML = '';
      } else if (pState && !pState.hasMore && pState.skip > 0) {
        statusEl.innerHTML = '<div class="infinite-scroll-end">✓ All messages loaded</div>';
      }
    }
  });

  if (SECTION_TITLES[sectionId] && sectionId !== 'tagSearch') {
    document.title = SECTION_TITLES[sectionId];
  }

  if (sectionId === 'home') {
    updateBreadcrumbs([{ label: 'Home', icon: '🏠' }], false);
    fetchRecentMessages().catch(() => {});
  } else if (sectionId === 'search') {
    updateBreadcrumbs([
      { label: 'Home', icon: '🏠', onclick: 'navigateToHome()' },
      { label: 'Search', icon: '🔍' },
    ], false);
  } else if (sectionId === 'post') {
    if (state.replyingTo && state.replyingTo.id) {
      updateBreadcrumbs([
        { label: 'Home', icon: '🏠', onclick: 'navigateToHome()' },
        { label: `Thread #${state.replyingTo.id}`, icon: '💬', onclick: `navigateToTag('message_reply_${state.replyingTo.id}')` },
        { label: 'Reply', icon: '✏️' },
      ], true);
    } else {
      updateBreadcrumbs([
        { label: 'Home', icon: '🏠', onclick: 'navigateToHome()' },
        { label: 'Post Message', icon: '✏️' },
      ], false);
    }
  } else if (sectionId === 'info') {
    updateBreadcrumbs([
      { label: 'Home', icon: '🏠', onclick: 'navigateToHome()' },
      { label: 'About & Info', icon: 'ℹ️' },
    ], false);
  } else if (sectionId === 'login') {
    updateBreadcrumbs([
      { label: 'Home', icon: '🏠', onclick: 'navigateToHome()' },
      { label: 'Login', icon: '🔑' },
    ], false);
    setTimeout(() => {
      const el = document.getElementById('loginUsername');
      if (el) el.focus();
    }, 50);
  } else if (sectionId === 'register') {
    updateBreadcrumbs([
      { label: 'Home', icon: '🏠', onclick: 'navigateToHome()' },
      { label: 'Register', icon: '✨' },
    ], false);
    setTimeout(() => {
      const el = document.getElementById('registerUsername');
      if (el) el.focus();
    }, 50);
  }
}

function formatError(detail) {
  if (!detail) return 'Request failed';
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === 'string') return item;
        if (item && typeof item === 'object') {
          if (item.msg) return item.msg;
          if (item.detail) return item.detail;
          return JSON.stringify(item);
        }
        return String(item);
      })
      .filter(Boolean)
      .join(' ');
  }
  if (typeof detail === 'object') {
    if (detail.msg) return detail.msg;
    if (detail.detail) return detail.detail;
    return JSON.stringify(detail);
  }
  return String(detail);
}

function clearFieldErrors() {
  ['registerUsername', 'registerEmail', 'registerPassword', 'registerConfirmPassword', 'messageText', 'messageTags'].forEach((name) => {
    const input = document.getElementById(name);
    const error = document.getElementById(`${name}Error`);
    if (input) input.setAttribute('aria-invalid', 'false');
    if (error) error.textContent = '';
  });
}

function showFieldErrors(detail, formName = 'register') {
  clearFieldErrors();
  const status = document.getElementById(`${formName}Status`);
  if (!detail || !Array.isArray(detail)) {
    if (status) status.textContent = formatError(detail || `${formName === 'post' ? 'Message post' : 'Registration'} failed`);
    return;
  }

  const messagesByField = {};
  detail.forEach((item) => {
    if (!item || typeof item !== 'object') return;
    const idx = Array.isArray(item.loc) ? item.loc[item.loc.length - 1] : null;
    if (!idx || typeof idx !== 'string') return;
    const fieldName = idx === 'body' ? null : idx;
    if (!fieldName) return;
    const message = item.msg || item.detail || 'Validation error';
    messagesByField[fieldName] = message;
  });

  Object.entries(messagesByField).forEach(([field, message]) => {
    const inputId = formName === 'post' ? `message${field.charAt(0).toUpperCase()}${field.slice(1)}` : `register${field.charAt(0).toUpperCase()}${field.slice(1)}`;
    const input = document.getElementById(inputId);
    const error = document.getElementById(`${inputId}Error`);
    if (input) input.setAttribute('aria-invalid', 'true');
    if (error) error.textContent = message;
  });

  const firstMessage = Object.values(messagesByField)[0] || formatError(detail);
  if (status) {
    status.textContent = firstMessage;
    status.className = 'status error';
  }
}

function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function formatImageSrc(imageData) {
  if (!imageData || typeof imageData !== 'string') return '';
  const trimmed = imageData.trim();
  if (trimmed.startsWith('data:') || trimmed.startsWith('http://') || trimmed.startsWith('https://') || trimmed.startsWith('/')) {
    return trimmed;
  }
  if (trimmed.startsWith('/9j/')) {
    return `data:image/jpeg;base64,${trimmed}`;
  }
  if (trimmed.startsWith('R0lGOD')) {
    return `data:image/gif;base64,${trimmed}`;
  }
  if (trimmed.startsWith('UklGR')) {
    return `data:image/webp;base64,${trimmed}`;
  }
  return `data:image/png;base64,${trimmed}`;
}

function formatTimestamp(timestamp) {
  if (!timestamp) return '';
  const date = new Date(timestamp);
  if (isNaN(date.getTime())) return '';
  return date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function parseMessageTags(tags) {
  if (!tags || !Array.isArray(tags)) return { topicTags: [], replyToId: null };
  let replyToId = null;
  const topicTags = [];
  for (const tag of tags) {
    if (typeof tag !== 'string') continue;
    const match = tag.match(/^messs?age_reply_(\d+)$/);
    if (match) {
      replyToId = parseInt(match[1], 10);
    } else {
      topicTags.push(tag);
    }
  }
  return { topicTags, replyToId };
}

function renderMessageCard(msg, options = {}) {
  cacheMessage(msg);
  const views = typeof msg.views === 'number' ? msg.views : (msg.views ? parseInt(msg.views, 10) : 0);
  const replyCount = typeof msg.reply_count === 'number' ? msg.reply_count : (typeof msg.replies_count === 'number' ? msg.replies_count : 0);
  const viewsLabel = `${views} ${views === 1 ? 'view' : 'views'}`;
  const repliesLabel = `${replyCount} ${replyCount === 1 ? 'reply' : 'replies'}`;
  const { topicTags, replyToId } = parseMessageTags(msg.tags);
  const isReply = options.isReply || false;
  const isRoot = options.isRoot || false;

  let cardClasses = 'message-card';
  if (isRoot) cardClasses += ' thread-root-card';
  if (isReply) cardClasses += ' thread-reply-card';

  const inReplyToBadge = replyToId && !isReply ? `
    <button type="button" class="in-reply-to-pill" onclick="event.stopPropagation(); navigateToTag('message_reply_${replyToId}')" title="View thread for message #${replyToId}">
      <span class="in-reply-icon">↳</span> In reply to <strong>#${replyToId}</strong>
    </button>
  ` : '';

  const rootBadge = isRoot ? `
    <div class="thread-starter-badge">
      <span class="thread-starter-icon">🌟</span>
      <span>Original Message</span>
      <span class="thread-id-pill">#${msg.id}</span>
    </div>
  ` : '';

  const replyBadge = isReply ? `
    <div class="reply-badge">
      <span class="reply-badge-icon">↳</span>
      <span>Reply <strong>#${msg.id}</strong></span>
    </div>
  ` : '';

  return `
    <div class="${cardClasses}" data-message-id="${msg.id}" onclick="onMessageCardClick(event, ${msg.id})">
      ${rootBadge}
      <div class="message-meta">
        <div class="message-author-tag">
          ${replyBadge}
          <span class="author-name">@${escapeHtml(msg.username || 'guest')}</span>
          ${!isReply && !isRoot ? `<span class="message-id-tag">#${msg.id}</span>` : ''}
          ${inReplyToBadge}
        </div>
        ${msg.created_at ? `<time class="message-timestamp" datetime="${escapeHtml(msg.created_at)}">${escapeHtml(formatTimestamp(msg.created_at))}</time>` : ''}
      </div>
      <div class="message-body-text">${escapeHtml(msg.text)}</div>
      ${msg.image_data ? `<img src="${formatImageSrc(msg.image_data)}" alt="Attached message" class="message-image" onerror="this.onerror=null; this.classList.add('broken-image');" />` : ''}
      <div class="message-footer">
        <div class="tags">
          ${topicTags.map((tag) => `<button type="button" class="tag" onclick="event.stopPropagation(); navigateToTag('${encodeURIComponent(tag)}')">#${escapeHtml(tag)}</button>`).join('')}
        </div>
        <div class="message-stats-actions">
          <div class="message-stats">
            <span class="message-stat message-views" title="${viewsLabel}"><span class="stat-icon">👁️</span> <span class="views-count">${views}</span> <span class="stat-label">${views === 1 ? 'view' : 'views'}</span></span>
            <button type="button" class="message-stat message-replies message-replies-btn" onclick="event.stopPropagation(); navigateToTag('message_reply_${msg.id}')" title="${repliesLabel} - Click to view thread"><span class="stat-icon">💬</span> <span class="replies-count">${replyCount}</span> <span class="stat-label">${replyCount === 1 ? 'reply' : 'replies'}</span></button>
          </div>
          <button type="button" class="reply-btn" onclick="event.stopPropagation(); replyToMessage(${msg.id})">💬 Reply</button>
        </div>
      </div>
    </div>
  `;
}

const PAGE_SIZE = 10;
const paginationState = {};
let infiniteScrollObserver = null;

function throttle(func, limit) {
  let inThrottle = false;
  return function (...args) {
    if (!inThrottle) {
      func.apply(this, args);
      inThrottle = true;
      setTimeout(() => {
        inThrottle = false;
      }, limit);
    }
  };
}

function setupIntersectionObserver() {
  if (typeof IntersectionObserver === 'undefined') return;

  if (infiniteScrollObserver) {
    infiniteScrollObserver.disconnect();
  }

  infiniteScrollObserver = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        const containerId = entry.target.getAttribute('data-container-id');
        if (containerId) {
          loadNextPage(containerId);
        }
      }
    });
  }, {
    root: null,
    rootMargin: '250px',
    threshold: 0.01,
  });
}

function observeSentinel(containerId) {
  const sentinel = document.getElementById(`${containerId}-sentinel`);
  if (!sentinel) return;
  if (infiniteScrollObserver) {
    infiniteScrollObserver.observe(sentinel);
  }
}

function unobserveSentinel(containerId) {
  const sentinel = document.getElementById(`${containerId}-sentinel`);
  if (!sentinel) return;
  if (infiniteScrollObserver) {
    infiniteScrollObserver.unobserve(sentinel);
  }
}

function checkAutoFill(containerId) {
  const scrollState = paginationState[containerId];
  if (!scrollState || scrollState.isLoading || !scrollState.hasMore) return;

  const sentinel = document.getElementById(`${containerId}-sentinel`);
  if (!sentinel) return;

  const rect = sentinel.getBoundingClientRect();
  if (rect.top <= window.innerHeight + 250 && rect.bottom >= -100) {
    loadNextPage(containerId);
  }
}

function renderMessagesContent(containerId, items, options = {}, hasMore = false) {
  const container = document.getElementById(containerId);
  if (!container) return;

  if (!items || items.length === 0) {
    container.innerHTML = '<p class="empty-state">No messages found.</p>';
    return;
  }

  items.forEach(cacheMessage);

  if (options.isThread && options.threadId) {
    const threadId = options.threadId;
    const rootMessage = items.find((m) => Number(m.id) === Number(threadId)) || items[0];
    const replies = items.filter((m) => Number(m.id) !== Number(rootMessage.id));

    const rootHtml = renderMessageCard(rootMessage, { isRoot: true });

    let repliesHtml = '';
    if (replies.length === 0 && !hasMore) {
      repliesHtml = `
        <div class="thread-empty-replies">
          <p class="empty-state">No replies in this thread yet. Be the first to join the conversation!</p>
          <button type="button" class="action-btn-sm" onclick="replyToMessage(${rootMessage.id})">💬 Post a Reply</button>
        </div>
      `;
    } else {
      repliesHtml = `
        <div class="thread-timeline" id="${containerId}-thread-timeline">
          ${replies.map((reply) => renderMessageCard(reply, { isReply: true })).join('')}
        </div>
      `;
    }

    container.innerHTML = `
      <div class="thread-drilldown-container">
        <div class="thread-root-section">
          ${rootHtml}
        </div>
        <div class="thread-replies-header">
          <h3>💬 Replies (<span id="${containerId}-replies-count">${replies.length}</span>)</h3>
          <span class="thread-replies-sub" id="${containerId}-replies-sub">${replies.length === 1 ? '1 response in this thread' : `${replies.length} responses in this thread`}</span>
        </div>
        ${repliesHtml}
      </div>
      <div class="infinite-scroll-status" id="${containerId}-status"></div>
      <div class="infinite-scroll-sentinel" data-container-id="${containerId}" id="${containerId}-sentinel"></div>
    `;
    return;
  }

  const itemsHtml = items.map((msg) => renderMessageCard(msg)).join('');
  container.innerHTML = `
    <div class="message-feed-items" id="${containerId}-items">
      ${itemsHtml}
    </div>
    <div class="infinite-scroll-status" id="${containerId}-status"></div>
    <div class="infinite-scroll-sentinel" data-container-id="${containerId}" id="${containerId}-sentinel"></div>
  `;
}

function appendMessagesContent(containerId, items, options = {}) {
  const container = document.getElementById(containerId);
  if (!container || !items || items.length === 0) return;

  items.forEach(cacheMessage);

  if (options.isThread && options.threadId) {
    const threadId = options.threadId;
    const newReplies = items.filter((m) => Number(m.id) !== Number(threadId));
    let timeline = document.getElementById(`${containerId}-thread-timeline`) || container.querySelector('.thread-timeline');

    const emptyReplies = container.querySelector('.thread-empty-replies');
    if (emptyReplies && newReplies.length > 0) {
      const drilldownContainer = container.querySelector('.thread-drilldown-container');
      if (drilldownContainer) {
        const newTimeline = document.createElement('div');
        newTimeline.className = 'thread-timeline';
        newTimeline.id = `${containerId}-thread-timeline`;
        drilldownContainer.replaceChild(newTimeline, emptyReplies);
        timeline = newTimeline;
      }
    }

    if (timeline && newReplies.length > 0) {
      const repliesHtml = newReplies.map((reply) => renderMessageCard(reply, { isReply: true })).join('');
      timeline.insertAdjacentHTML('beforeend', repliesHtml);
    }

    const allReplies = container.querySelectorAll('.thread-reply-card');
    const countEl = document.getElementById(`${containerId}-replies-count`);
    const subEl = document.getElementById(`${containerId}-replies-sub`);
    if (countEl) countEl.textContent = allReplies.length;
    if (subEl) subEl.textContent = allReplies.length === 1 ? '1 response in this thread' : `${allReplies.length} responses in this thread`;
    return;
  }

  const itemsContainer = document.getElementById(`${containerId}-items`) || container;
  const cardsHtml = items.map((msg) => renderMessageCard(msg)).join('');
  const statusEl = document.getElementById(`${containerId}-status`);
  if (statusEl && itemsContainer === container) {
    statusEl.insertAdjacentHTML('beforebegin', cardsHtml);
  } else if (itemsContainer) {
    itemsContainer.insertAdjacentHTML('beforeend', cardsHtml);
  }
}

function renderMessages(containerId, items, options = {}) {
  renderMessagesContent(containerId, items, options, false);
}

async function loadNextPage(containerId) {
  const scrollState = paginationState[containerId];
  if (!scrollState || scrollState.isLoading || !scrollState.hasMore) {
    return;
  }

  scrollState.isLoading = true;

  const statusEl = document.getElementById(`${containerId}-status`);
  if (statusEl) {
    const loadingText = scrollState.skip === 0 ? 'Loading messages...' : 'Loading more messages...';
    statusEl.innerHTML = `
      <div class="infinite-scroll-loading">
        <div class="spinner"></div>
        <span>${loadingText}</span>
      </div>
    `;
  }

  const queryParams = new URLSearchParams();
  if (scrollState.params) {
    Object.entries(scrollState.params).forEach(([key, val]) => {
      if (val !== undefined && val !== null && val !== '') {
        queryParams.append(key, val);
      }
    });
  }
  queryParams.append('skip', String(scrollState.skip));
  queryParams.append('limit', String(scrollState.limit));

  const url = `${scrollState.endpoint}?${queryParams.toString()}`;
  const headers = state.token ? { Authorization: `Bearer ${state.token}` } : {};

  try {
    const response = await fetch(url, { headers });
    if (!response.ok) {
      throw new Error(`Failed to load messages (${response.status})`);
    }
    const data = await response.json();

    if (scrollState.skip === 0 && (!data || data.length === 0)) {
      scrollState.hasMore = false;
      const container = document.getElementById(containerId);
      if (container) {
        if (scrollState.options && scrollState.options.isThread) {
          container.innerHTML = '<p class="empty-state">No thread found.</p>';
        } else {
          container.innerHTML = '<p class="empty-state">No messages found.</p>';
        }
      }
      return;
    }

    if (scrollState.skip === 0) {
      renderMessagesContent(containerId, data, scrollState.options, data.length >= scrollState.limit);
    } else {
      appendMessagesContent(containerId, data, scrollState.options);
    }

    scrollState.skip += data.length;

    if (!data || data.length < scrollState.limit) {
      scrollState.hasMore = false;
      unobserveSentinel(containerId);
      const curStatusEl = document.getElementById(`${containerId}-status`);
      const panel = curStatusEl ? curStatusEl.closest('section.panel') : null;
      const isVisible = panel ? !panel.classList.contains('hidden') : true;
      if (curStatusEl) {
        if (isVisible) {
          curStatusEl.innerHTML = '<div class="infinite-scroll-end">✓ All messages loaded</div>';
        } else {
          curStatusEl.innerHTML = '';
        }
      }
    } else {
      const curStatusEl = document.getElementById(`${containerId}-status`);
      if (curStatusEl) {
        curStatusEl.innerHTML = '';
      }
      observeSentinel(containerId);
      setTimeout(() => {
        checkAutoFill(containerId);
      }, 100);
    }
  } catch (error) {
    console.error('Error loading messages page:', error);
    const curStatusEl = document.getElementById(`${containerId}-status`);
    if (curStatusEl) {
      curStatusEl.innerHTML = `
        <div class="infinite-scroll-error">
          <span>Failed to load messages.</span>
          <button type="button" class="retry-btn" onclick="loadNextPage('${containerId}')">Retry</button>
        </div>
      `;
    }
  } finally {
    scrollState.isLoading = false;
  }
}

async function initInfiniteScroll(containerId, config = {}) {
  const container = document.getElementById(containerId);
  if (!container) return;

  unobserveSentinel(containerId);

  paginationState[containerId] = {
    endpoint: config.endpoint || '/search_messages/',
    params: config.params || {},
    skip: 0,
    limit: config.limit || PAGE_SIZE,
    hasMore: true,
    isLoading: false,
    options: config.options || {},
    items: [],
  };

  const hasExistingContent = container.querySelector('.message-card') || container.querySelector('.thread-drilldown-container');
  if (!hasExistingContent) {
    container.innerHTML = `
      <div class="infinite-scroll-status" id="${containerId}-status">
        <div class="infinite-scroll-loading">
          <div class="spinner"></div>
          <span>Loading messages...</span>
        </div>
      </div>
      <div class="infinite-scroll-sentinel" data-container-id="${containerId}" id="${containerId}-sentinel"></div>
    `;
  }

  await loadNextPage(containerId);
}

function onMessageCardClick(event, messageId) {
  if (event && event.target && event.target.closest('button, a, input, textarea')) {
    return;
  }
  navigateToTag(`message_reply_${messageId}`);
}

async function fetchRecentMessages() {
  await initInfiniteScroll('recentMessages', {
    endpoint: '/messages/',
    params: { order: 'desc' },
  });
}

async function searchMessages(event) {
  if (event) event.preventDefault();
  const textInput = document.getElementById('searchText');
  const tagsInput = document.getElementById('searchTags');
  const text = textInput ? textInput.value.trim() : '';
  const tags = tagsInput ? tagsInput.value.trim() : '';
  const params = {};
  if (text) params.search_text = text;
  if (tags) params.tags = tags.split(',').map((t) => t.trim()).filter(Boolean).join(',');

  await initInfiniteScroll('searchResults', {
    endpoint: '/search_messages/',
    params,
  });
}

async function searchByQuery(params = {}) {
  const searchTags = params.tags || params.tag || '';
  const searchText = params.search_text || params.q || params.text || '';
  const queryParams = {};
  if (searchTags) queryParams.tags = searchTags;
  if (searchText) queryParams.search_text = searchText;

  const searchTitle = document.getElementById('tagSearchTitle') || document.getElementById('searchTitle');
  const searchQueryBadge = document.getElementById('tagSearchQueryBadge') || document.getElementById('searchQueryBadge');

  let isThread = false;
  let threadId = null;

  if (searchTags) {
    const threadMatch = searchTags.match(/^messs?age_reply_(\d+)$/);
    if (threadMatch) {
      isThread = true;
      threadId = parseInt(threadMatch[1], 10);
    }
  }

  if (isThread) {
    document.title = `Posts tagged #${searchTags} - Adam Network`;
    if (searchTitle) searchTitle.textContent = `Posts tagged #${searchTags}`;
    if (searchQueryBadge) {
      searchQueryBadge.textContent = `Thread #${threadId}`;
      searchQueryBadge.classList.remove('hidden');
    }
    updateBreadcrumbs([
      { label: 'Home', icon: '🏠', onclick: 'navigateToHome()' },
      { label: `Thread #${threadId}`, icon: '💬' },
    ], true);
  } else if (searchTags) {
    document.title = `Posts tagged #${searchTags} - Adam Network`;
    if (searchTitle) searchTitle.textContent = `Posts tagged #${searchTags}`;
    if (searchQueryBadge) {
      searchQueryBadge.textContent = `#${searchTags}`;
      searchQueryBadge.classList.remove('hidden');
    }
    updateBreadcrumbs([
      { label: 'Home', icon: '🏠', onclick: 'navigateToHome()' },
      { label: `Tag: #${searchTags}`, icon: '🏷️' },
    ], true);
  } else if (searchText) {
    document.title = `Search results for "${searchText}" - Adam Network`;
    if (searchTitle) searchTitle.textContent = `Search results for "${searchText}"`;
    if (searchQueryBadge) {
      searchQueryBadge.textContent = `"${searchText}"`;
      searchQueryBadge.classList.remove('hidden');
    }
    updateBreadcrumbs([
      { label: 'Home', icon: '🏠', onclick: 'navigateToHome()' },
      { label: `Search: "${searchText}"`, icon: '🔍' },
    ], true);
  } else {
    document.title = 'Tag Stream - Adam Network';
    if (searchTitle) searchTitle.textContent = 'Tag Stream';
    if (searchQueryBadge) searchQueryBadge.classList.add('hidden');
    updateBreadcrumbs([
      { label: 'Home', icon: '🏠', onclick: 'navigateToHome()' },
      { label: 'Stream', icon: '🌊' },
    ], true);
  }

  showSection('tagSearch');

  const endpoint = Object.keys(queryParams).length > 0 ? '/search_messages/' : '/messages/';
  await initInfiniteScroll('tagSearchResults', {
    endpoint,
    params: queryParams,
    options: { isThread, threadId },
  });
}

async function replyToMessage(messageId, passedMsg = null) {
  let msg = passedMsg || messageCache.get(Number(messageId));
  if (!msg) {
    try {
      const headers = state.token ? { Authorization: `Bearer ${state.token}` } : {};
      const resp = await fetch(`/messages/${messageId}`, { headers });
      if (resp.ok) {
        msg = await resp.json();
        cacheMessage(msg);
      }
    } catch (err) {
      console.error('Failed to fetch message details for reply', err);
    }
  }

  state.replyingTo = msg || { id: messageId };

  const preview = document.getElementById('replyTargetPreview');
  const authorEl = document.getElementById('replyTargetAuthor');
  const idEl = document.getElementById('replyTargetId');
  const timeEl = document.getElementById('replyTargetTime');
  const textEl = document.getElementById('replyTargetText');
  const mediaEl = document.getElementById('replyTargetMedia');
  const imageEl = document.getElementById('replyTargetImage');
  const postTitle = document.getElementById('postSectionTitle');
  const submitBtn = document.getElementById('postSubmitBtn');

  if (authorEl) authorEl.textContent = `@${msg?.username || 'guest'}`;
  if (idEl) idEl.textContent = `#${messageId}`;
  if (timeEl) timeEl.textContent = msg?.created_at ? formatTimestamp(msg.created_at) : '';
  if (textEl) textEl.textContent = msg?.text || `Replying to message #${messageId}`;

  if (mediaEl && imageEl) {
    if (msg?.image_data) {
      imageEl.src = formatImageSrc(msg.image_data);
      mediaEl.classList.remove('hidden');
    } else {
      imageEl.src = '';
      mediaEl.classList.add('hidden');
    }
  }

  if (preview) preview.classList.remove('hidden');
  if (postTitle) postTitle.textContent = `Reply to Message #${messageId}`;
  if (submitBtn) submitBtn.textContent = 'Post Reply';

  const tagsInput = document.getElementById('messageTags');
  if (tagsInput) {
    tagsInput.value = `message_reply_${messageId}`;
  }
  const textInput = document.getElementById('messageText');
  if (textInput) {
    textInput.value = '';
  }
  clearFieldErrors();
  const status = document.getElementById('postStatus');
  if (status) {
    status.textContent = '';
    status.className = 'status';
  }
  showSection('post');
  if (textInput) {
    textInput.focus();
  }
}

function cancelReply() {
  state.replyingTo = null;
  const preview = document.getElementById('replyTargetPreview');
  if (preview) preview.classList.add('hidden');

  const postTitle = document.getElementById('postSectionTitle');
  if (postTitle) postTitle.textContent = 'Post a New Message';

  const submitBtn = document.getElementById('postSubmitBtn');
  if (submitBtn) submitBtn.textContent = 'Post Message';

  const tagsInput = document.getElementById('messageTags');
  if (tagsInput && tagsInput.value.startsWith('message_reply_')) {
    tagsInput.value = '';
  }

  const postSection = document.getElementById('post');
  if (postSection && !postSection.classList.contains('hidden')) {
    updateBreadcrumbs([
      { label: 'Home', icon: '🏠', onclick: 'navigateToHome()' },
      { label: 'Post Message', icon: '✏️' },
    ], false);
  }
}

function navigateToTag(encodedTag) {
  const tag = decodeURIComponent(encodedTag);
  const newUrl = `${window.location.pathname}?tags=${encodeURIComponent(tag)}`;
  window.history.pushState({ tags: tag }, '', newUrl);
  searchByQuery({ tags: tag });
}

function searchMessagesFromURL() {
  const urlParams = new URLSearchParams(window.location.search);
  const tags = urlParams.get('tags') || urlParams.get('tag');
  const searchText = urlParams.get('search_text') || urlParams.get('q') || urlParams.get('text');
  if (tags || searchText) {
    searchByQuery({ tags, search_text: searchText });
    return true;
  }
  return false;
}

async function loginUser(event) {
  event.preventDefault();
  const username = document.getElementById('loginUsername').value;
  const password = document.getElementById('loginPassword').value;
  const status = document.getElementById('loginStatus');

  const body = new URLSearchParams({ username, password });
  const response = await fetch('/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  });

  const data = await response.json();
  if (!response.ok) {
    status.className = 'status error';
    status.textContent = formatError(data.detail || 'Login failed');
    return;
  }

  state.token = data.access_token;
  localStorage.setItem('token', data.access_token);
  status.className = 'status success';
  status.textContent = 'Logged in successfully.';
  document.getElementById('loginForm').reset();
  updateSessionIndicator();
  navigateToHome();
}

async function registerUser(event) {
  event.preventDefault();
  const username = document.getElementById('registerUsername').value;
  const email = document.getElementById('registerEmail').value;
  const password = document.getElementById('registerPassword').value;
  const confirmPassword = document.getElementById('registerConfirmPassword').value;
  const status = document.getElementById('registerStatus');

  const response = await fetch('/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, email, password, confirm_password: confirmPassword }),
  });

  const data = await response.json();
  if (!response.ok) {
    clearFieldErrors();
    status.className = 'status error';
    if (Array.isArray(data.detail)) {
      showFieldErrors(data.detail);
    } else {
      status.textContent = formatError(data.detail || 'Registration failed');
    }
    return;
  }

  clearFieldErrors();
  status.className = 'status success';
  status.textContent = 'Registered successfully. You can now log in.';
  const loginStatus = document.getElementById('loginStatus');
  if (loginStatus) {
    loginStatus.className = 'status success';
    loginStatus.textContent = 'Registered successfully. You can now log in.';
  }
  document.getElementById('registerForm').reset();
  showSection('login');
}

async function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error('Unable to read selected image'));
    reader.readAsDataURL(file);
  });
}

async function postMessage(event) {
  event.preventDefault();
  const status = document.getElementById('postStatus');
  if (status) {
    status.textContent = '';
    status.className = 'status';
  }
  const text = document.getElementById('messageText').value.trim();
  const tagsInput = document.getElementById('messageTags').value.trim();
  const imageInput = document.getElementById('messageImage');
  const textError = document.getElementById('messageTextError');
  const tagsError = document.getElementById('messageTagsError');

  if (!text) {
    if (textError) textError.textContent = 'Message text is required.';
    if (status) {
      status.className = 'status error';
      status.textContent = 'Please enter a message before posting.';
    }
    return;
  }

  if (textError) textError.textContent = '';
  if (tagsError) tagsError.textContent = '';

  let image_data = null;
  if (imageInput && imageInput.files && imageInput.files[0]) {
    try {
      image_data = await readFileAsDataUrl(imageInput.files[0]);
    } catch (error) {
      if (status) {
        status.className = 'status error';
        status.textContent = 'Unable to read selected image.';
      }
      return;
    }
  }

  const guestName = !state.token ? getOrCreateGuestName() : undefined;
  const payload = {
    text,
    tags: tagsInput ? tagsInput.split(',').map((tag) => tag.trim()).filter(Boolean) : [],
    image_data,
    ...(guestName && { username: guestName }),
  };

  const response = await fetch('/messages/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(state.token && { Authorization: `Bearer ${state.token}` }),
      ...(guestName && { 'X-Guest-Name': guestName }),
    },
    body: JSON.stringify(payload),
  });

  const data = await response.json();
  if (!response.ok) {
    if (status) status.className = 'status error';
    if (Array.isArray(data.detail)) {
      showFieldErrors(data.detail, 'post');
    } else {
      if (status) status.textContent = formatError(data.detail || 'Message post failed');
    }
    return;
  }

  document.getElementById('postForm').reset();
  if (textError) textError.textContent = '';
  if (tagsError) tagsError.textContent = '';
  cancelReply();

  if (data && data.id) {
    navigateToTag(`message_reply_${data.id}`);
  }
  fetchRecentMessages().catch(() => {});

  if (status) {
    status.className = 'status success';
    status.textContent = 'Message posted successfully.';
  }
}

async function logoutUser() {
  if (!state.token) {
    localStorage.removeItem('token');
    state.token = '';
    updateSessionIndicator();
    navigateToHome();
    return;
  }

  await fetch('/logout', {
    method: 'POST',
    headers: { Authorization: `Bearer ${state.token}` },
  });

  state.token = '';
  localStorage.removeItem('token');
  const postStatus = document.getElementById('postStatus');
  if (postStatus) postStatus.textContent = 'Logged out.';
  updateSessionIndicator();
  navigateToHome();
}

const searchForm = document.getElementById('searchForm');
if (searchForm) {
  searchForm.addEventListener('submit', searchMessages);
}
document.getElementById('loginForm').addEventListener('submit', loginUser);
document.getElementById('registerForm').addEventListener('submit', registerUser);
document.getElementById('postForm').addEventListener('submit', postMessage);

window.addEventListener('popstate', () => {
  if (window.location.pathname === '/info') {
    cancelReply();
    showSection('info');
  } else if (!searchMessagesFromURL()) {
    cancelReply();
    showSection('home');
  }
});

window.addEventListener('scroll', throttle(() => {
  const activeSection = document.querySelector('section.panel:not(.hidden)');
  if (!activeSection) return;
  const sentinel = activeSection.querySelector('.infinite-scroll-sentinel');
  if (!sentinel) return;
  const containerId = sentinel.getAttribute('data-container-id');
  if (containerId) {
    checkAutoFill(containerId);
  }
}, 150));

setupIntersectionObserver();

fetchRecentMessages().catch(() => {
  const recent = document.getElementById('recentMessages');
  if (recent) recent.innerHTML = '<p class="empty-state">Unable to load messages.</p>';
});

updateSessionIndicator();
if (window.location.pathname === '/info') {
  showSection('info');
} else if (!searchMessagesFromURL()) {
  showSection('home');
}
