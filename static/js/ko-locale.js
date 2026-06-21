const KO_TEXT = new Map([
  ['Settings', '설정'],
  ['Peek', '뒤 화면 보기'],
  ['User', '사용자'],
  ['You', '나'],
  ['Assistant', 'AI'],
  ['Korean casual greeting', '한국어 인사 대화'],
  ['New Chat', '새 채팅'],
  ['New chat', '새 채팅'],
  ['Chats', '채팅'],
  ['Tools', '도구'],
  ['Brain', 'AI 기억'],
  ['Calendar', '일정표'],
  ['Compare', '비교'],
  ['Cookbook', '사용법 모음'],
  ['Deep Research', '심층 조사'],
  ['Gallery', '사진첩'],
  ['Library', '자료함'],
  ['Notes', '메모'],
  ['Tasks', '작업'],
  ['Theme', '화면 꾸미기'],
  ['Models', '모델'],
  ['Agent', '자동 작업'],
  ['Chat', '채팅'],
  ['Odysseus Chat', 'Odysseus 채팅'],
  ['Add Models', '모델 추가'],
  ['Added Models', '추가된 모델'],
  ['AI Defaults', 'AI 기본값'],
  ['Search', '검색'],
  ['Integrations', '연동'],
  ['Email', '이메일'],
  ['Reminders', '알림'],
  ['Appearance', '화면'],
  ['Shortcuts', '단축키'],
  ['Account', '계정'],
  ['Admin', '관리자'],
  ['Agent Tools', '에이전트 도구'],
  ['Users', '사용자'],
  ['System', '시스템'],
  ['Memories', '기억'],
  ['Skills', '기능'],
  ['Enabled', '사용 중'],
  ['Long-term facts the AI remembers across chats — recall, edit, or curate.', 'AI가 대화 전반에서 기억할 장기 정보를 저장합니다. 불러오고, 수정하고, 정리할 수 있습니다.'],
  ['Newest', '최신순'],
  ['Oldest', '오래된순'],
  ['Most used', '많이 사용한 순'],
  ['Recent', '최근'],
  ['Favorites', '즐겨찾기'],
  ['All models', '전체 모델'],
  ['No matching models', '일치하는 모델이 없습니다'],
  ['No models connected', '연결된 모델이 없습니다'],
  ['No memories yet', '아직 기억이 없습니다'],
  ['Import in Add tab', '추가 탭에서 가져오기'],
  ['No matches.', '일치하는 항목이 없습니다.'],
  ['Tidy', '정리'],
  ['Select', '선택'],
  ['All', '전체'],
  ['Delete', '삭제'],
  ['Rename', '이름 변경'],
  ['Copy Chat', '채팅 복사'],
  ['Save to Documents', '문서로 저장'],
  ['Last Active', '최근 활동순'],
  ['Newest First', '최신순'],
  ['By Folder', '폴더별'],
  ['Group', '그룹'],
  ['Sorting...', '정리 중...'],
  ['Rearrange', '순서 바꾸기'],
  ['manage', '관리'],
  ['new', '새로 만들기'],
  ['+ Chat', '+ 채팅'],
  ['Add Local Models', '로컬 모델 추가'],
  ['Add API Models', 'API 모델 추가'],
  ['Added Models', '추가된 모델'],
  ['(Endpoint)', '(엔드포인트)'],
  ['(Endpoints)', '(엔드포인트)'],
  ['Add a local model server (Ollama, llama.cpp, vLLM).', '로컬 모델 서버(Ollama, llama.cpp, vLLM)를 추가합니다.'],
  ['Connect a cloud provider (OpenAI, Anthropic, DeepSeek, OpenRouter, etc.).', '클라우드 공급자(OpenAI, Anthropic, DeepSeek, OpenRouter 등)를 연결합니다.'],
  ['Endpoints you\'ve connected. Probe re-tests them all; Clear offline removes the dead ones.', '연결된 엔드포인트입니다. 점검은 전체를 다시 테스트하고, 오프라인 삭제는 응답 없는 항목을 제거합니다.'],
  ['Test', '테스트'],
  ['Cancel', '취소'],
  ['Add', '추가'],
  ['Probe', '점검'],
  ['Clear offline', '오프라인 삭제'],
  ['Scan network', '네트워크 검색'],
  ['Add Ollama', 'Ollama 추가'],
  ['API key', 'API 키'],
  ['Import Codex CLI login', 'Codex CLI 로그인 가져오기'],
  ['Importing...', '가져오는 중...'],
  ['Codex CLI login found', 'Codex CLI 로그인을 찾았습니다'],
  ['Run codex login first', '먼저 codex login을 실행하세요'],
  ['Codex CLI login not found', 'Codex CLI 로그인을 찾지 못했습니다'],
  ['Reading local Codex CLI login...', '로컬 Codex CLI 로그인을 읽는 중...'],
  ['Codex CLI login imported', 'Codex CLI 로그인을 가져왔습니다'],
  ['Provider', '공급자'],
  ['Connection mode', '연결 방식'],
  ['Proxy', '프록시'],
  ['routed via server', '서버 경유'],
  ['API (direct)', 'API(직접)'],
  ['browser→provider', '브라우저→공급자'],
  ['Local', '로컬'],
  ['Image', '이미지'],
  ['Loading...', '불러오는 중...'],
  ['No API endpoints yet.', '아직 API 엔드포인트가 없습니다.'],
  ['Default Chat Model', '기본 채팅 모델'],
  ['The model used when creating a new chat session.', '새 채팅 세션을 만들 때 사용할 모델입니다.'],
  ['Endpoint', '엔드포인트'],
  ['Model', '모델'],
  ['Email Safety', '이메일 안전'],
  ['Web Search', '웹 검색'],
  ['Search API used for web search and deep research.', '웹 검색과 딥 리서치에 사용할 검색 API입니다.'],
  ['Deep Research runtime settings. Default Model is picked in', '딥 리서치 실행 설정입니다. 기본 모델은'],
  ['AI Defaults →', 'AI 기본값 →'],
  ['Search →', '검색 →'],
  ['Keyboard Shortcuts', '키보드 단축키'],
  ['Email Accounts', '이메일 계정'],
  ['Add, edit, delete, and test accounts in Integrations.', '계정 추가, 수정, 삭제, 테스트는 연동에서 관리합니다.'],
  ['Open Integrations', '연동 열기'],
  ['Email Tasks', '이메일 작업'],
  ['Configure email account, ntfy server, etc. in', '이메일 계정, ntfy 서버 등은 다음에서 설정합니다:'],
  ['Codex Agent', 'Codex 에이전트'],
  ['Claude Agent', 'Claude 에이전트'],
  ['Downloads a plugin bundle and registers it.', '플러그인 번들을 내려받고 등록합니다.'],
  ['All external service connections in one place.', '외부 서비스 연결을 한곳에서 관리합니다.'],
  ['Add Integration', '연동 추가'],
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
  ['2FA Code', '2단계 인증 코드'],
  ['Verify', '확인'],
  ['Invalid credentials', '인증 정보가 올바르지 않습니다'],
  ['Login failed', '로그인에 실패했습니다'],
  ['Account creation failed', '계정 생성에 실패했습니다'],
]);

const KO_ATTRS = {
  placeholder: new Map([
    ['Paste endpoint URL, e.g. http://localhost:11434/v1', '엔드포인트 URL 붙여넣기, 예: http://localhost:11434/v1'],
    ['API key (optional — for protected local endpoints)', 'API 키(선택 - 보호된 로컬 엔드포인트용)'],
    ['Base URL or pick provider', '기본 URL 또는 공급자 선택'],
    ['API key, e.g. sk-proj-AbCdEf…', 'API 키, 예: sk-proj-AbCdEf...'],
    ['Search conversations...', '대화 검색...'],
    ['Search models...', '모델 검색...'],
    ['Search models…', '모델 검색...'],
    ['Search memories…', '기억 검색...'],
    ['Search memories...', '기억 검색...'],
    ['Search skills…', '기능 검색...'],
    ['Message Odysseus...', 'Odysseus에게 메시지...'],
    ['No models connected', '연결된 모델이 없습니다'],
    ['Theme name...', '테마 이름...'],
    ['Paste theme JSON here...', '테마 JSON을 붙여넣으세요...'],
    ['Enter session name', '채팅 이름 입력'],
    ['Enter 6-digit code', '6자리 코드 입력'],
  ]),
  title: new Map([
    ['Fade this window to preview the page behind it', '뒤 화면을 볼 수 있게 이 창을 흐리게 표시'],
    ['More options', '추가 옵션'],
    ['Pick provider', '공급자 선택'],
    ['Re-test every endpoint and refresh online status', '모든 엔드포인트를 다시 테스트하고 온라인 상태 새로고침'],
    ['Remove all endpoints currently marked offline', '현재 오프라인으로 표시된 엔드포인트 제거'],
    ['Remember me', '로그인 유지'],
    ['Search conversations (Ctrl+K)', '대화 검색(Ctrl+K)'],
    ['Email', '이메일'],
    ['Settings', '설정'],
    ['New chat', '새 채팅'],
    ['Toggle sidebar', '사이드바 열기/닫기'],
    ['Brain', 'AI 기억'],
    ['Cookbook', '사용법 모음'],
    ['Library', '자료함'],
    ['Notes', '메모'],
    ['Tasks', '작업'],
    ['Theme', '화면 꾸미기'],
    ['Manage Chats (Library)', '채팅 관리(라이브러리)'],
    ['Sort sessions', '채팅 정렬'],
    ['Sort models', '모델 정렬'],
    ['Switch model', '모델 바꾸기'],
    ['Add model endpoints', '모델 연결 추가'],
    ['Select multiple memories', '여러 기억 선택'],
    ['AI tidy: deduplicate and clean up memories', 'AI 정리: 중복 기억을 제거하고 다듬기'],
    ['Cancel (Esc)', '취소(Esc)'],
  ]),
  'aria-label': new Map([
    ['Settings', '설정'],
    ['Close settings', '설정 닫기'],
    ['Close memory modal', 'AI 기억 닫기'],
    ['Toggle sidebar', '사이드바 열기/닫기'],
    ['Sidebar', '사이드바'],
    ['Brain', 'AI 기억'],
    ['Theme', '화면 꾸미기'],
    ['Cookbook', '사용법 모음'],
    ['Library', '자료함'],
    ['Notes', '메모'],
    ['Tasks', '작업'],
    ['Chat area', '채팅 영역'],
    ['Message input', '메시지 입력'],
    ['Remember me', '로그인 유지'],
    ['Show password', '비밀번호 보이기'],
    ['Hide password', '비밀번호 숨기기'],
    ['Search models', '모델 검색'],
    ['Search memories', '기억 검색'],
    ['Search skills', '기능 검색'],
    ['Select model', '모델 선택'],
    ['Add model endpoints', '모델 연결 추가'],
    ['Sort memories', '기억 정렬'],
    ['New memory text', '새 기억 내용'],
    ['Skill import URL', '스킬 가져오기 URL'],
    ['Skill title', '스킬 제목'],
    ['Add model chat', '모델 채팅 추가'],
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

function translateTextNode(node) {
  const original = node.nodeValue || '';
  const key = original.trim().replace(/\s+/g, ' ');
  if (!key) return;
  const translated = KO_TEXT.get(key) || translatePattern(key);
  if (!translated) return;
  node.nodeValue = translatedWhitespace(original, translated);
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
  return null;
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
    if (root.matches?.(ROOT_SELECTOR)) {
      roots.push(root);
    } else {
      const scope = root.closest?.(ROOT_SELECTOR);
      if (scope) roots.push(scope);
    }
  }
  if (root.querySelectorAll) {
    roots.push(...root.querySelectorAll(ROOT_SELECTOR));
  }
  if (root === document) {
    roots.push(...document.querySelectorAll(ROOT_SELECTOR));
  }

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
    translateRoot(root);
    const message = document.getElementById('message');
    if (message && message.getAttribute('placeholder') === 'Message Odysseus...') {
      message.setAttribute('placeholder', 'Odysseus에게 메시지...');
    }
    if (document.title === 'Odysseus — Login') {
      document.title = 'Odysseus - 로그인';
    }
  });
}

scheduleTranslate();
window.__odysseusKoLocaleReady = true;
window.__odysseusKoLocaleTranslate = () => scheduleTranslate(document);

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
