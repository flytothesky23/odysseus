(function () {
  const KO_TEXT = new Map([
    ['Settings', '설정'],
    ['Peek', '뒤 화면 보기'],
    ['User', '사용자'],
    ['You', '나'],
    ['Assistant', 'AI'],
    ['Korean casual greeting', '한국어 인사 대화'],
    ['New Chat', '새 채팅'],
    ['New chat', '새 채팅'],
    ['New chat ready.', '새 채팅이 준비되었습니다.'],
    ['Type /setup, then choose Local models or API.', '/setup을 입력한 뒤 로컬 모델 또는 API를 선택하세요.'],
    ['Chats', '채팅'],
    ['Search', '검색'],
    ['Tools', '도구'],
    ['Brain', 'AI 기억'],
    ['Calendar', '일정표'],
    ['Compare', '비교'],
    ['Cookbook', '사용법 모음'],
    ['Deep Research', '심층 조사'],
    ['Email', '이메일'],
    ['Gallery', '사진첩'],
    ['Library', '자료함'],
    ['Notes', '메모'],
    ['Tasks', '작업'],
    ['Theme', '화면 꾸미기'],
    ['Models', '모델'],
    ['Agent', '자동 작업'],
    ['Chat', '채팅'],
    ['Memories', '기억'],
    ['Skills', '기능'],
    ['Add', '추가'],
    ['new', '새로 만들기'],
    ['document', '문서'],
    ['Add Models', '모델 추가'],
    ['Added Models', '추가된 모델'],
    ['AI Defaults', 'AI 기본값'],
    ['Agent Tools', '에이전트 도구'],
    ['Users', '사용자'],
    ['System', '시스템'],
    ['Web Search', '웹 검색'],
    ['Search API used for web search and deep research.', '웹 검색과 심층 조사에 사용할 검색 API입니다.'],
    ['Deep Research runtime settings. Default Model is picked in', '심층 조사 실행 설정입니다. 기본 모델은'],
    ['AI Defaults →', 'AI 기본값 →'],
    ['Search →', '검색 →'],
    ['Add Local Models', '로컬 모델 추가'],
    ['Add API Models', 'API 모델 추가'],
    ['Utility Model', '유틸리티 모델'],
    ['Recommended: Local Endpoint', '권장: 로컬 엔드포인트'],
    ['Model used for Deep Research, more settings under', '심층 조사에 사용할 모델입니다. 추가 설정:'],
    ['Provider', '공급자'],
    ['Endpoint', '엔드포인트'],
    ['Model', '모델'],
    ['Reasoning', '추론 정도'],
    ['Reasoning effort', '추론 정도'],
    ['Automatic', '자동'],
    ['Low', '낮음'],
    ['Medium', '보통'],
    ['High', '높음'],
    ['Extra High', '매우 높음'],
    ['Max', '최대'],
    ['Local', '로컬'],
    ['OpenAI', 'OpenAI'],
    ['Test', '테스트'],
    ['Cancel', '취소'],
    ['Probe', '점검'],
    ['Clear offline', '오프라인 삭제'],
    ['Scan network', '네트워크 검색'],
    ['Add Ollama', 'Ollama 추가'],
    ['API key', 'API 키'],
    ['No API endpoints yet.', '아직 API 엔드포인트가 없습니다.'],
    ['Long-term facts the AI remembers across chats — recall, edit, or curate.', 'AI가 대화 전반에서 기억할 장기 정보를 저장합니다. 불러오고, 수정하고, 정리할 수 있습니다.'],
    ['Newest', '최신순'],
    ['Oldest', '오래된순'],
    ['Most used', '많이 사용한 순'],
    ['Recent', '최근'],
    ['Favorites', '즐겨찾기'],
    ['All', '전체'],
    ['Select', '선택'],
    ['Tidy', '정리'],
    ['Delete', '삭제'],
    ['Delete All', '전체 삭제'],
    ['Rename', '이름 변경'],
    ['Save', '저장'],
    ['Export', '내보내기'],
    ['Apply', '적용'],
    ['Change Password', '비밀번호 변경'],
    ['Current password', '현재 비밀번호'],
    ['New password', '새 비밀번호'],
    ['Confirm new password', '새 비밀번호 확인'],
    ['Update Password', '비밀번호 변경'],
    ['Email Settings', '이메일 설정'],
    ['Open Email Settings', '이메일 설정 열기'],
    ['Danger Zone', '위험 구역'],
    ['Username', '사용자 이름'],
    ['Password', '비밀번호'],
    ['Confirm Password', '비밀번호 확인'],
    ['Sign In', '로그인'],
    ['Sign in', '로그인'],
    ['Sign up', '가입'],
    ['Create Account', '계정 만들기'],
    ['Create Admin Account', '관리자 계정 만들기'],
    ['Already have an account?', '이미 계정이 있으신가요?'],
    ['Don\'t have an account?', '계정이 없으신가요?'],
    ['First-time setup — create your admin account', '첫 설정 - 관리자 계정을 만듭니다'],
    ['Remember me', '로그인 유지'],
    ['2FA Code', '2단계 인증 코드'],
    ['Verify', '확인'],
    ['Passwords do not match', '비밀번호가 일치하지 않습니다'],
    ['Login failed', '로그인에 실패했습니다'],
    ['Account creation failed', '계정 생성에 실패했습니다'],
  ]);

  const KO_ATTRS = {
    placeholder: new Map([
      ['Message Odysseus...', 'Odysseus에게 메시지...'],
      ['Search conversations...', '대화 검색...'],
      ['Search models', '모델 검색'],
      ['Search models...', '모델 검색...'],
      ['No models connected', '연결된 모델이 없습니다'],
      ['Search memories…', '기억 검색...'],
      ['Search skills…', '기능 검색...'],
      ['Search logs...', '로그 검색...'],
      ['Paste endpoint URL, e.g. http://localhost:11434/v1', '엔드포인트 URL 붙여넣기, 예: http://localhost:11434/v1'],
      ['API key (optional — for protected local endpoints)', 'API 키(선택 - 보호된 로컬 엔드포인트용)'],
      ['Base URL or pick provider', '기본 URL 또는 공급자 선택'],
      ['API key, e.g. sk-proj-AbCdEf…', 'API 키, 예: sk-proj-AbCdEf...'],
      ['Theme name...', '테마 이름...'],
      ['Paste theme JSON here...', '테마 JSON을 붙여넣으세요...'],
      ['Enter session name', '채팅 이름 입력'],
      ['Enter 6-digit code', '6자리 코드 입력'],
      ['Username', '사용자 이름'],
      ['Password', '비밀번호'],
      ['Current password', '현재 비밀번호'],
      ['New password', '새 비밀번호'],
      ['Confirm new password', '새 비밀번호 확인'],
      ['Enter custom value', '직접 입력'],
      ['http://localhost:8080 (optional)', 'http://localhost:8080 (선택)'],
      ['Google PSE engine ID', 'Google PSE 엔진 ID'],
      ['8192 (default)', '8192 (기본값)'],
      ['90 sec', '90초'],
      ['1800 sec (0 = no limit)', '1800초 (0 = 제한 없음)'],
      ['model name', '모델 이름'],
    ]),
    title: new Map([
      ['Fade this window to preview the page behind it', '뒤 화면을 볼 수 있게 이 창을 흐리게 표시'],
      ['More options', '추가 옵션'],
      ['Search conversations (Ctrl+K)', '대화 검색(Ctrl+K)'],
      ['Settings', '설정'],
      ['Toggle sidebar', '사이드바 열기/닫기'],
      ['Brain', 'AI 기억'],
      ['Calendar', '일정표'],
      ['Compare', '비교'],
      ['Cookbook', '사용법 모음'],
      ['Deep Research', '심층 조사'],
      ['Email', '이메일'],
      ['Gallery', '사진첩'],
      ['Library', '자료함'],
      ['Notes', '메모'],
      ['Tasks', '작업'],
      ['Theme', '화면 꾸미기'],
      ['Remember me', '로그인 유지'],
      ['Show password', '비밀번호 보이기'],
      ['Hide password', '비밀번호 숨기기'],
      ['Add model endpoints', '모델 연결 추가'],
      ['Refresh model picker', '모델 목록 새로고침'],
      ['Delete all chats', '모든 채팅 삭제'],
      ['Delete all memory', '모든 기억 삭제'],
      ['Delete every category', '모든 범주 삭제'],
    ]),
    'aria-label': new Map([
      ['Settings', '설정'],
      ['Close settings', '설정 닫기'],
      ['Close memory modal', 'AI 기억 닫기'],
      ['Toggle sidebar', '사이드바 열기/닫기'],
      ['Sidebar', '사이드바'],
      ['Brain', 'AI 기억'],
      ['Theme', '화면 꾸미기'],
      ['Chat area', '채팅 영역'],
      ['Message input', '메시지 입력'],
      ['Remember me', '로그인 유지'],
      ['Show password', '비밀번호 보이기'],
      ['Hide password', '비밀번호 숨기기'],
      ['Search models', '모델 검색'],
      ['Refresh model picker', '모델 목록 새로고침'],
      ['Reasoning effort', '추론 정도'],
      ['Search memories', '기억 검색'],
      ['Search skills', '기능 검색'],
      ['Two-factor authentication code', '2단계 인증 코드'],
    ]),
  };

  const ROOT_SELECTOR = [
    '#settings-modal',
    '#search-overlay',
    '#memory-modal',
    '#theme-modal',
    '#theme-popup',
    '#cookbook-modal',
    '#custom-preset-modal',
    '#rename-session-modal',
    '#model-picker-wrap',
    '#model-picker-menu',
    '#chat-form',
    '#message',
    '#toast',
    '.modal',
    '.modal-content',
    '.mode-toggle',
    '.chat-meta-overlay',
    '.chat-input-bar',
    '.icon-rail',
    '.sidebar',
    '#sidebar',
    '.user-bar',
    '.welcome-screen',
    'main.card',
  ].join(',');

  const SKIP_SELECTOR = [
    'script',
    'style',
    'pre',
    'code',
    'textarea',
    '.cm-editor',
    '.markdown-body',
    '.message',
    '.chat-message',
    '.document-editor',
  ].join(',');

  function translatedWhitespace(original, translated) {
    const leading = original.match(/^\s*/)?.[0] || '';
    const trailing = original.match(/\s*$/)?.[0] || '';
    return `${leading}${translated}${trailing}`;
  }

  function normalizeText(value) {
    return value.trim().replace(/\s+/g, ' ');
  }

  function translatePattern(key) {
    let match = key.match(/^(\d+(?:\/\d+)?) memories$/);
    if (match) return `${match[1]}개 기억`;
    match = key.match(/^(\d+) memory$/);
    if (match) return `${match[1]}개 기억`;
    match = key.match(/^(\d+) Selected$/);
    if (match) return `${match[1]}개 선택됨`;
    match = key.match(/^Using (.+)$/);
    if (match) return `${match[1]} 사용 중`;
    match = key.match(/^Default: (low|medium|high|xhigh|max)$/);
    if (match) {
      const efforts = {
        low: '낮음',
        medium: '보통',
        high: '높음',
        xhigh: '매우 높음',
        max: '최대',
      };
      return `기본값: ${efforts[match[1]]}`;
    }
    return null;
  }

  function translateTextNode(node) {
    const original = node.nodeValue || '';
    const key = normalizeText(original);
    if (!key) return;
    const translated = KO_TEXT.get(key) || translatePattern(key);
    if (!translated) return;
    node.nodeValue = translatedWhitespace(original, translated);
  }

  function translateAttrs(el) {
    for (const [attr, translations] of Object.entries(KO_ATTRS)) {
      if (!el.hasAttribute?.(attr)) continue;
      const current = el.getAttribute(attr);
      const translated = translations.get(current);
      if (translated) el.setAttribute(attr, translated);
    }
  }

  function translateRoot(root) {
    if (!root) return;
    const roots = [];
    if (root.nodeType === Node.ELEMENT_NODE) {
      if (root.matches?.(ROOT_SELECTOR)) roots.push(root);
      const scope = root.closest?.(ROOT_SELECTOR);
      if (scope) roots.push(scope);
    }
    if (root.querySelectorAll) roots.push(...root.querySelectorAll(ROOT_SELECTOR));
    if (root === document) roots.push(...document.querySelectorAll(ROOT_SELECTOR));

    for (const scope of new Set(roots)) {
      if (scope.closest?.(SKIP_SELECTOR)) continue;
      translateAttrs(scope);
      scope.querySelectorAll?.('*').forEach((el) => {
        if (!el.closest(SKIP_SELECTOR)) translateAttrs(el);
      });
      const walker = document.createTreeWalker(scope, NodeFilter.SHOW_TEXT, {
        acceptNode(node) {
          const parent = node.parentElement;
          if (!parent || parent.closest(SKIP_SELECTOR)) return NodeFilter.FILTER_REJECT;
          return NodeFilter.FILTER_ACCEPT;
        },
      });
      let node;
      while ((node = walker.nextNode())) translateTextNode(node);
    }
  }

  function nearestScope(node) {
    const el = node?.nodeType === Node.ELEMENT_NODE ? node : node?.parentElement;
    if (!el) return document;
    return el.matches?.(ROOT_SELECTOR) ? el : (el.closest?.(ROOT_SELECTOR) || document);
  }

  let pending = false;
  function scheduleTranslate(root = document) {
    if (pending) return;
    pending = true;
    requestAnimationFrame(() => {
      pending = false;
      document.documentElement.lang = 'ko';
      translateRoot(document);
      const message = document.getElementById('message');
      if (message && message.getAttribute('placeholder') === 'Message Odysseus...') {
        message.setAttribute('placeholder', 'Odysseus에게 메시지...');
      }
      if (document.title === 'Odysseus Chat') document.title = 'Odysseus 채팅';
      if (document.title === 'Odysseus — Login') document.title = 'Odysseus - 로그인';
      window.__odysseusKoLocaleReady = true;
    });
  }

  window.__odysseusKoLocaleTranslate = () => scheduleTranslate(document);
  scheduleTranslate();

  new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      if (mutation.type === 'attributes') {
        scheduleTranslate(nearestScope(mutation.target));
        return;
      }
      if (mutation.type === 'characterData') {
        const parent = mutation.target.parentElement;
        if (parent?.closest(ROOT_SELECTOR) && !parent.closest(SKIP_SELECTOR)) {
          scheduleTranslate(nearestScope(parent));
          return;
        }
      }
      for (const node of mutation.addedNodes) {
        if (node.nodeType === Node.ELEMENT_NODE || node.nodeType === Node.TEXT_NODE) {
          scheduleTranslate(nearestScope(node));
          return;
        }
      }
    }
  }).observe(document.documentElement, {
    childList: true,
    subtree: true,
    characterData: true,
    attributes: true,
    attributeFilter: ['placeholder', 'title', 'aria-label'],
  });
})();
