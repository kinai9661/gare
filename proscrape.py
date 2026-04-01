

import os
import re
import sys
import json
import time
import hashlib
import mimetypes
import urllib.parse
import gzip
import io
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Set, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict
import threading
from collections import defaultdict
import logging

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
import cssutils
from fake_useragent import UserAgent
from tqdm import tqdm
import validators
from w3lib.url import canonicalize_url
import chardet
from http.server import HTTPServer, SimpleHTTPRequestHandler
import socket

logging.getLogger('cssutils').setLevel(logging.CRITICAL)
cssutils.log.enabled = False

@dataclass
class CloneConfig:
    """Configuration for website cloning."""
    url: str
    max_depth: int = 20
    max_pages: int = 15000
    concurrent_requests: int = 50
    timeout: int = 30
    rewrite_links: bool = True
    capture_api: bool = True
    download_media: bool = True
    download_fonts: bool = True
    download_documents: bool = True
    download_source: bool = True
    respect_robots: bool = False
    include_external: bool = False
    user_agent: str = ""
    delay_between_requests: float = 0.02
    clone_hidden: bool = True
    clone_data_files: bool = True
    clone_backend_files: bool = True
    follow_redirects: bool = True
    aggressive_scan: bool = True
    # 新增欄位：手動貼上 Cookie 或 Bearer token
    cookies: str = ""          # 完整 Cookie 字串，例如 "session=abc; other=def"
    auth_token: str = ""       # Bearer token，若有
    
    def __post_init__(self):
        if not self.user_agent:
            try:
                ua = UserAgent()
                self.user_agent = ua.random
            except:
                self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


@dataclass
class CloneStats:
    """Statistics for the cloning process."""
    pages_downloaded: int = 0
    assets_downloaded: int = 0
    api_endpoints_found: int = 0
    forms_found: int = 0
    external_links: int = 0
    errors: int = 0
    total_size_bytes: int = 0
    hidden_files_found: int = 0
    data_files_found: int = 0
    start_time: float = field(default_factory=time.time)
    end_time: float = 0
    
    @property
    def duration(self) -> float:
        return (self.end_time or time.time()) - self.start_time
    
    @property
    def total_size_mb(self) -> float:
        return self.total_size_bytes / (1024 * 1024)


class WebCloner:
    """Advanced website cloner with comprehensive features."""
    
    MEDIA_EXTENSIONS = {
        'images': {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg', '.ico', '.avif', '.tiff', '.tif', '.heic', '.heif', '.raw'},
        'videos': {'.mp4', '.webm', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.m4v', '.3gp', '.3g2', '.ogv'},
        'audio': {'.mp3', '.wav', '.ogg', '.flac', '.aac', '.m4a', '.wma', '.opus', '.mid', '.midi'},
        'fonts': {'.woff', '.woff2', '.ttf', '.otf', '.eot', '.sfnt'},
        'documents': {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt', '.csv', '.rtf', '.odt', '.ods', '.odp'},
        'data': {'.json', '.xml', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf', '.properties', '.env.example', '.env.sample'},
        'archives': {'.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz'},
        'source': {'.js', '.ts', '.jsx', '.tsx', '.mjs', '.cjs', '.vue', '.svelte', '.py', '.rb', '.php', '.go', '.rs', '.java', '.kt', '.swift', '.c', '.cpp', '.h', '.hpp', '.cs', '.scala', '.clj', '.ex', '.exs', '.erl', '.hrl', '.elm', '.hs', '.ml', '.fs', '.dart', '.lua', '.r', '.jl', '.nim', '.zig', '.v', '.sh', '.bash', '.zsh', '.fish', '.ps1', '.bat', '.cmd'},
        'config': {'.lock', '.lockb', '.npmrc', '.yarnrc', '.nvmrc', '.node-version', '.python-version', '.ruby-version', '.tool-versions', '.editorconfig', '.prettierrc', '.eslintrc', '.babelrc', '.browserslistrc'}
    }
    
    HIDDEN_FILES = [
        'robots.txt', 'sitemap.xml', 'sitemap_index.xml', 'sitemap-index.xml',
        '.well-known/security.txt', '.well-known/dnt-policy.txt', '.well-known/change-password',
        '.well-known/assetlinks.json', '.well-known/apple-app-site-association',
        '.well-known/webfinger', '.well-known/host-meta', '.well-known/host-meta.json',
        'manifest.json', 'manifest.webmanifest', 'site.webmanifest', 'app.webmanifest',
        'browserconfig.xml', 'humans.txt', 'ads.txt', 'app-ads.txt', 'sellers.json',
        'security.txt', 'crossdomain.xml', 'clientaccesspolicy.xml',
        'favicon.ico', 'favicon.png', 'favicon.svg', 'favicon-16x16.png', 'favicon-32x32.png',
        'apple-touch-icon.png', 'apple-touch-icon-precomposed.png',
        'apple-touch-icon-57x57.png', 'apple-touch-icon-72x72.png',
        'apple-touch-icon-76x76.png', 'apple-touch-icon-114x114.png',
        'apple-touch-icon-120x120.png', 'apple-touch-icon-144x144.png',
        'apple-touch-icon-152x152.png', 'apple-touch-icon-180x180.png',
        'mstile-70x70.png', 'mstile-144x144.png', 'mstile-150x150.png', 'mstile-310x150.png', 'mstile-310x310.png',
        'safari-pinned-tab.svg', 'mask-icon.svg',
        'sw.js', 'service-worker.js', 'serviceworker.js', 'worker.js',
        'offline.html', 'offline.json', 'app.json',
        'opensearch.xml', 'rss.xml', 'feed.xml', 'atom.xml', 'feed.json',
        'BingSiteAuth.xml', 'google[a-z0-9]*.html', 'yandex_[a-z0-9]*.html',
        '.htaccess', 'web.config', 'wp-config.php', 'config.php',
        'VERSION', 'version.txt', 'version.json', 'CHANGELOG.md', 'changelog.txt',
        'LICENSE', 'LICENSE.txt', 'LICENSE.md', 'COPYING',
        'README.md', 'readme.txt', 'README.txt',
        'i18n/*.json', 'locales/*.json', 'lang/*.json', 'translations/*.json',
        'static/manifest.json', 'public/manifest.json', 'assets/manifest.json',
        
        'package.json', 'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml', 'bun.lockb',
        'index.js', 'index.ts', 'index.mjs', 'index.cjs', 'main.js', 'main.ts',
        'app.js', 'app.ts', 'server.js', 'server.ts', 'app/index.js', 'src/index.js',
        'src/app.js', 'src/server.js', 'src/main.js', 'src/index.ts', 'src/app.ts',
        'server/index.js', 'server/app.js', 'server/server.js', 'api/index.js',
        'routes/index.js', 'routes.js', 'router.js', 'middleware.js', 'controllers/index.js',
        'express.js', 'fastify.js', 'koa.js', 'hapi.js', 'nest.js',
        
        'tsconfig.json', 'jsconfig.json', 'tsconfig.node.json', 'tsconfig.app.json',
        'webpack.config.js', 'webpack.config.ts', 'webpack.common.js', 'webpack.prod.js', 'webpack.dev.js',
        'vite.config.js', 'vite.config.ts', 'rollup.config.js', 'rollup.config.ts',
        'esbuild.config.js', 'parcel.config.js', 'turbo.json',
        'next.config.js', 'next.config.mjs', 'next.config.ts', 'nuxt.config.js', 'nuxt.config.ts',
        'gatsby-config.js', 'gatsby-node.js', 'gatsby-browser.js', 'gatsby-ssr.js',
        'svelte.config.js', 'astro.config.mjs', 'remix.config.js', 'angular.json',
        'vue.config.js', 'quasar.config.js', 'ember-cli-build.js',
        
        '.env.example', '.env.sample', '.env.template', '.env.development', '.env.production',
        'config/default.json', 'config/production.json', 'config/development.json',
        'config.json', 'config.js', 'config.ts', 'settings.json', 'settings.js',
        '.babelrc', '.babelrc.js', 'babel.config.js', 'babel.config.json',
        '.eslintrc', '.eslintrc.js', '.eslintrc.json', '.eslintrc.yaml', 'eslint.config.js',
        '.prettierrc', '.prettierrc.js', '.prettierrc.json', 'prettier.config.js',
        '.stylelintrc', '.stylelintrc.json', 'stylelint.config.js',
        'jest.config.js', 'jest.config.ts', 'vitest.config.js', 'vitest.config.ts',
        'cypress.config.js', 'cypress.config.ts', 'playwright.config.js', 'playwright.config.ts',
        'karma.conf.js', 'mocha.opts', '.mocharc.json', 'ava.config.js',
        'tailwind.config.js', 'tailwind.config.ts', 'postcss.config.js', 'postcss.config.cjs',
        'windi.config.js', 'uno.config.js', 'unocss.config.js',
        
        'Dockerfile', 'docker-compose.yml', 'docker-compose.yaml', 'docker-compose.prod.yml',
        '.dockerignore', 'Makefile', 'Rakefile', 'Gruntfile.js', 'Gulpfile.js',
        'Procfile', 'vercel.json', 'netlify.toml', 'render.yaml', 'fly.toml', 'railway.json',
        'now.json', 'app.yaml', 'app.yml', 'serverless.yml', 'serverless.ts',
        '.github/workflows/main.yml', '.github/workflows/ci.yml', '.github/workflows/deploy.yml',
        '.gitlab-ci.yml', 'Jenkinsfile', 'azure-pipelines.yml', 'bitbucket-pipelines.yml',
        '.circleci/config.yml', '.travis.yml', 'appveyor.yml', 'cloudbuild.yaml',
        
        'requirements.txt', 'requirements-dev.txt', 'requirements-prod.txt',
        'setup.py', 'setup.cfg', 'pyproject.toml', 'poetry.lock', 'Pipfile', 'Pipfile.lock',
        'manage.py', 'wsgi.py', 'asgi.py', 'app.py', 'main.py', 'run.py',
        'settings.py', 'config.py', 'urls.py', 'views.py', 'models.py', 'admin.py', 'forms.py',
        'django.conf', 'flask_app.py', 'celery.py', 'tasks.py', 'gunicorn.conf.py',
        
        'Gemfile', 'Gemfile.lock', 'config.ru', 'Capfile', 'Vagrantfile',
        'composer.json', 'composer.lock', 'artisan', 'phpunit.xml',
        'go.mod', 'go.sum', 'main.go', 'cmd/main.go', 'pkg/server.go',
        'Cargo.toml', 'Cargo.lock', 'main.rs', 'lib.rs', 'mod.rs',
        'pom.xml', 'build.gradle', 'build.gradle.kts', 'settings.gradle', 'gradlew',
        'build.sbt', 'project/build.properties', 'project/plugins.sbt',
        'mix.exs', 'mix.lock', 'rebar.config', 'rebar.lock',
        'deno.json', 'deno.jsonc', 'deno.lock', 'import_map.json',
        
        '.gitignore', '.gitattributes', '.npmignore', '.nvmrc', '.node-version',
        '.python-version', '.ruby-version', '.tool-versions', 'asdf.config',
        '.editorconfig', '.vscode/settings.json', '.vscode/launch.json', '.idea/workspace.xml',
        'CONTRIBUTING.md', 'CODE_OF_CONDUCT.md', 'SECURITY.md', 'CODEOWNERS',
        '.husky/pre-commit', '.husky/commit-msg', 'commitlint.config.js', '.commitlintrc',
        'lerna.json', 'nx.json', 'workspace.json', 'rush.json', 'pnpm-workspace.yaml',
        
        'schema.prisma', 'prisma/schema.prisma', 'prisma/migrations',
        'drizzle.config.ts', 'knexfile.js', 'ormconfig.json', 'typeorm.config.ts',
        'sequelize.config.js', 'database.yml', 'db/migrate', 'db/schema.rb', 'db/seeds.rb',
        'alembic.ini', 'alembic/env.py', 'migrations/env.py',
        'graphql/schema.graphql', 'schema.graphql', 'typeDefs.js', 'resolvers.js',
        'openapi.yaml', 'openapi.json', 'swagger.yaml', 'swagger.json', 'api-spec.yaml'
    ]
    
    HIDDEN_DIRECTORIES = [
        '.well-known', 'api', 'v1', 'v2', 'v3', 'v4', 'graphql', 'rest',
        'static', 'assets', 'public', 'dist', 'build', 'out', 'output', '.output',
        'css', 'js', 'javascript', 'scripts', 'styles', 'stylesheets',
        'images', 'img', 'media', 'fonts', 'icons', 'svg', 'webfonts',
        'i18n', 'locales', 'lang', 'translations', 'messages',
        'data', 'json', 'xml', 'config', 'conf', 'settings', 'env',
        '_next', '__next', '_nuxt', '.nuxt', '_astro', '.svelte-kit',
        'wp-content', 'wp-includes', 'wp-admin', 'wp-json',
        'vendor', 'node_modules', 'bower_components', 'packages',
        
        'src', 'source', 'lib', 'libs', 'core', 'app', 'application',
        'server', 'backend', 'api-server', 'services', 'service',
        'routes', 'controllers', 'middleware', 'middlewares', 'handlers',
        'models', 'schemas', 'entities', 'database', 'db', 'migrations',
        'views', 'templates', 'layouts', 'partials', 'components',
        'utils', 'utilities', 'helpers', 'common', 'shared', 'modules',
        'plugins', 'extensions', 'addons', 'integrations',
        'tests', 'test', '__tests__', 'spec', 'specs', 'e2e', 'cypress', 'playwright',
        
        'client', 'frontend', 'web', 'www', 'pages', 'screens',
        'redux', 'store', 'stores', 'state', 'context', 'hooks', 'providers',
        'features', 'domains', 'slices', 'reducers', 'actions', 'selectors',
        'types', 'interfaces', 'typings', '@types', 'definitions',
        'constants', 'enums', 'configs', 'environments',
        
        'prisma', 'drizzle', 'typeorm', 'sequelize', 'knex', 'mongoose',
        'graphql', 'apollo', 'trpc', 'grpc', 'websocket', 'socket',
        'auth', 'authentication', 'authorization', 'security', 'guards',
        'cache', 'caching', 'redis', 'memcached',
        'queue', 'queues', 'jobs', 'workers', 'tasks', 'cron', 'scheduler',
        'mail', 'email', 'notifications', 'messaging',
        'upload', 'uploads', 'storage', 'files', 'downloads',
        'logs', 'logging', 'monitoring', 'metrics', 'analytics',
        
        'docker', '.docker', 'kubernetes', 'k8s', 'helm', 'terraform',
        '.github', '.gitlab', '.circleci', '.jenkins', 'ci', 'cd',
        'scripts', 'bin', 'tools', 'devops', 'deploy', 'deployment',
        'docs', 'documentation', 'wiki', 'guides', 'examples', 'samples'
    ]
    
    API_PATTERNS = [
        r'/api/', r'/v\d+/', r'/graphql', r'/rest/',
        r'\.json$', r'/ajax/', r'/xhr/', r'/data/',
        r'/feed/', r'/rss/', r'/atom/'
    ]
    
    def __init__(self, config: CloneConfig):
        self.config = config
        self.stats = CloneStats()
        self.visited_urls: Set[str] = set()
        self.queued_urls: Set[str] = set()
        self.downloaded_assets: Set[str] = set()
        self.api_endpoints: List[Dict] = []
        self.forms: List[Dict] = []
        self.external_links: Set[str] = set()
        self.url_mapping: Dict[str, str] = {}
        self.errors: List[Dict] = []
        self.discovered_paths: Set[str] = set()
        self.lock = threading.Lock()
        
        parsed = urllib.parse.urlparse(config.url)
        self.base_domain = parsed.netloc
        self.base_scheme = parsed.scheme
        self.base_url = f"{parsed.scheme}://{parsed.netloc}"
        
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        safe_domain = re.sub(r'[^\w\-.]', '_', self.base_domain)
        self.output_dir = Path(f"mirror_{safe_domain}_{timestamp}")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.session = self._create_session()
        
    def _create_session(self) -> requests.Session:
        """Create a high-performance requests session with optimized connection pooling."""
        session = requests.Session()
        
        retry_strategy = Retry(
            total=3,
            backoff_factor=0.3,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"],
            raise_on_status=False
        )
        
        adapter = HTTPAdapter(
            max_retries=retry_strategy, 
            pool_connections=200, 
            pool_maxsize=200,
            pool_block=False
        )
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        session.headers.update({
            'User-Agent': self.config.user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/avif,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,*;q=0.5',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
        })
        # Disable automatic decompression to receive raw gzip content for manual handling
        session.headers['Accept-Encoding'] = 'identity'
        # 注入 grok.com 驗證資訊（若提供）
        if self.config.cookies:
            session.headers['Cookie'] = self.config.cookies
        if self.config.auth_token:
            session.headers['Authorization'] = f"Bearer {self.config.auth_token}"
        
        return session
    
    def _normalize_url(self, url: str, base_url: Optional[str] = None) -> Optional[str]:
        """Normalize and validate a URL."""
        if not url or not isinstance(url, str):
            return None
            
        url = url.strip()
        
        if url.startswith(('#', 'javascript:', 'mailto:', 'tel:', 'data:', 'blob:')):
            return None
            
        base = base_url or self.base_url
        
        try:
            if url.startswith('//'):
                url = f"{self.base_scheme}:{url}"
            elif url.startswith('/'):
                url = f"{self.base_url}{url}"
            elif not url.startswith(('http://', 'https://')):
                url = urllib.parse.urljoin(base, url)
            
            parsed = urllib.parse.urlparse(url)
            url = urllib.parse.urlunparse((
                parsed.scheme,
                parsed.netloc,
                parsed.path or '/',
                parsed.params,
                parsed.query,
                ''
            ))
            
            return canonicalize_url(url)
        except Exception:
            return None
    
    def _is_same_domain(self, url: str) -> bool:
        """Check if URL belongs to the same domain."""
        try:
            parsed = urllib.parse.urlparse(url)
            return parsed.netloc == self.base_domain or parsed.netloc.endswith(f".{self.base_domain}")
        except:
            return False
    
    def _get_local_path(self, url: str) -> Path:
        """Convert URL to local file path."""
        parsed = urllib.parse.urlparse(url)
        path = urllib.parse.unquote(parsed.path.strip('/'))
        
        if not path:
            path = 'index.html'
        elif path.endswith('/'):
            path = path + 'index.html'
        elif not os.path.splitext(path)[1]:
            path = path + '/index.html'
        
        if parsed.query:
            query_hash = hashlib.md5(parsed.query.encode()).hexdigest()[:8]
            base, ext = os.path.splitext(path)
            path = f"{base}_{query_hash}{ext}"
        
        path = re.sub(r'[<>:"|?*]', '_', path)
        
        local_path = self.output_dir / path
        return local_path
    
    def _decompress_content(self, content: bytes, encoding: Optional[str] = None) -> bytes:
        """Decompress gzip or deflate content if needed."""
        try:
            # Check for gzip magic number
            if content[:2] == b'\x1f\x8b':
                return gzip.decompress(content)
        except Exception:
            pass
        return content
    
    def _download_content(self, url: str) -> Optional[Tuple[bytes, str, Dict]]:
        """Download content from URL with proper encoding detection and decompression."""
        try:
            response = self.session.get(
                url, 
                timeout=self.config.timeout, 
                allow_redirects=self.config.follow_redirects,
                stream=False
            )
            response.raise_for_status()
            
            content = response.content
            # Decompress if needed
            content = self._decompress_content(content)
            
            content_type = response.headers.get('Content-Type', '')
            
            with self.lock:
                self.stats.total_size_bytes += len(content)
            
            return content, content_type, dict(response.headers)
            
        except requests.exceptions.RequestException as e:
            with self.lock:
                self.stats.errors += 1
                self.errors.append({
                    'url': url,
                    'error': str(e),
                    'timestamp': datetime.now().isoformat()
                })
            return None
    
    def _save_file(self, path: Path, content):
        """Save content to file, handling both text and binary."""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            
            # Check if content is already a string
            if isinstance(content, str):
                # Save as text with UTF-8 encoding
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(content)
            else:
                # Content is bytes - check if it's text or binary
                ext = path.suffix.lower()
                text_extensions = {'.html', '.htm', '.css', '.js', '.json', '.xml', '.txt', '.md', '.svg', '.ts', '.jsx', '.tsx', '.py', '.rb', '.php', '.java'}
                
                is_text = ext in text_extensions
                
                if is_text:
                    # Try to decode as text
                    try:
                        detected = chardet.detect(content)
                        encoding = detected['encoding'] if detected and detected['encoding'] else 'utf-8'
                        text_content = content.decode(encoding, errors='replace')
                        with open(path, 'w', encoding='utf-8') as f:
                            f.write(text_content)
                    except Exception:
                        # Fallback to binary save
                        with open(path, 'wb') as f:
                            f.write(content)
                else:
                    # Save as binary for images, fonts, etc.
                    with open(path, 'wb') as f:
                        f.write(content)
        except Exception as e:
            with self.lock:
                self.errors.append({
                    'path': str(path),
                    'error': f"Failed to save: {e}",
                    'timestamp': datetime.now().isoformat()
                })
    
    def _extract_urls_from_html(self, html: str, base_url: str) -> Dict[str, Set[str]]:
        """Extract all URLs from HTML content."""
        urls = {
            'pages': set(),
            'assets': set(),
            'external': set()
        }
        
        try:
            soup = BeautifulSoup(html, 'lxml')
        except:
            soup = BeautifulSoup(html, 'html.parser')
        
        link_attrs = [
            ('a', 'href'),
            ('link', 'href'),
            ('script', 'src'),
            ('img', 'src'),
            ('img', 'data-src'),
            ('img', 'data-lazy-src'),
            ('img', 'data-original'),
            ('img', 'data-srcset'),
            ('source', 'src'),
            ('source', 'srcset'),
            ('source', 'data-src'),
            ('video', 'src'),
            ('video', 'poster'),
            ('video', 'data-src'),
            ('audio', 'src'),
            ('audio', 'data-src'),
            ('embed', 'src'),
            ('object', 'data'),
            ('iframe', 'src'),
            ('iframe', 'data-src'),
            ('form', 'action'),
            ('input', 'src'),
            ('track', 'src'),
            ('use', 'href'),
            ('use', 'xlink:href'),
            ('image', 'href'),
            ('image', 'xlink:href'),
        ]
        
        for meta in soup.find_all('meta'):
            content = meta.get('content')
            prop = meta.get('property', '') or meta.get('name', '')
            if content and isinstance(content, str):
                if prop in ['og:image', 'og:url', 'twitter:image', 'twitter:image:src', 'og:video', 'og:audio']:
                    self._categorize_url(content, base_url, urls)
        
        for tag_name, attr in link_attrs:
            for tag in soup.find_all(tag_name, attrs={attr: True}):
                raw_url = tag.get(attr)
                if not raw_url:
                    continue
                
                if isinstance(raw_url, list):
                    raw_url = raw_url[0] if raw_url else ''
                
                if not isinstance(raw_url, str):
                    continue
                
                if attr in ['srcset', 'data-srcset']:
                    for part in raw_url.split(','):
                        src = part.strip().split()[0] if part.strip() else ''
                        if src:
                            self._categorize_url(src, base_url, urls)
                else:
                    self._categorize_url(raw_url, base_url, urls)
        
        style_pattern = re.compile(r'url\(["\']?([^"\')\s]+)["\']?\)', re.IGNORECASE)
        
        for style_tag in soup.find_all('style'):
            if style_tag.string and isinstance(style_tag.string, str):
                for match in style_pattern.finditer(style_tag.string):
                    self._categorize_url(match.group(1), base_url, urls)
        
        for tag in soup.find_all(style=True):
            style = tag.get('style', '')
            if style and isinstance(style, str):
                for match in style_pattern.finditer(style):
                    self._categorize_url(match.group(1), base_url, urls)
        
        js_url_pattern = re.compile(r'["\']([^"\']*\.(js|css|png|jpg|jpeg|gif|svg|woff2?|ttf|otf|eot|ico|webp|avif|mp4|webm|mp3|json|xml))["\']', re.IGNORECASE)
        for script in soup.find_all('script'):
            if script.string and isinstance(script.string, str):
                for match in js_url_pattern.finditer(script.string):
                    self._categorize_url(match.group(1), base_url, urls)
        
        for noscript in soup.find_all('noscript'):
            noscript_html = str(noscript)
            inner_urls = self._extract_urls_from_html(noscript_html, base_url)
            for key in urls:
                urls[key].update(inner_urls.get(key, set()))
        
        for form in soup.find_all('form'):
            action = form.get('action', '')
            method = form.get('method', 'GET')
            if isinstance(method, list):
                method = method[0] if method else 'GET'
            if isinstance(action, list):
                action = action[0] if action else ''
                
            form_data = {
                'action': str(action) if action else '',
                'method': str(method).upper() if method else 'GET',
                'id': str(form.get('id', '')),
                'name': str(form.get('name', '')),
                'inputs': []
            }
            for input_tag in form.find_all(['input', 'select', 'textarea']):
                form_data['inputs'].append({
                    'name': str(input_tag.get('name', '')),
                    'type': str(input_tag.get('type', 'text')),
                    'id': str(input_tag.get('id', ''))
                })
            
            with self.lock:
                self.forms.append(form_data)
                self.stats.forms_found += 1
        
        preload_pattern = re.compile(r'<link[^>]*rel=["\']?preload["\']?[^>]*href=["\']?([^"\'>\s]+)["\']?', re.IGNORECASE)
        for match in preload_pattern.finditer(html):
            self._categorize_url(match.group(1), base_url, urls)
        
        return urls
    
    def _categorize_url(self, raw_url: str, base_url: str, urls: Dict[str, Set[str]]):
        """Categorize URL as page, asset, or external."""
        if not raw_url or not isinstance(raw_url, str):
            return
            
        url = self._normalize_url(raw_url, base_url)
        if not url:
            return
        
        if not self._is_same_domain(url):
            urls['external'].add(url)
            with self.lock:
                self.external_links.add(url)
                self.stats.external_links += 1
            return
        
        ext = os.path.splitext(urllib.parse.urlparse(url).path)[1].lower()
        
        is_asset = False
        for category, extensions in self.MEDIA_EXTENSIONS.items():
            if ext in extensions:
                is_asset = True
                break
        
        if ext in {'.css', '.js', '.mjs', '.cjs', '.map'}:
            is_asset = True
        
        if is_asset:
            urls['assets'].add(url)
        else:
            urls['pages'].add(url)
    
    def _extract_urls_from_css(self, css: str, base_url: str) -> Set[str]:
        """Extract URLs from CSS content."""
        urls = set()
        
        if not css or not isinstance(css, str):
            return urls
        
        url_pattern = re.compile(r'url\(["\']?([^"\')\s]+)["\']?\)', re.IGNORECASE)
        import_pattern = re.compile(r'@import\s+["\']([^"\']+)["\']', re.IGNORECASE)
        import_url_pattern = re.compile(r'@import\s+url\(["\']?([^"\')\s]+)["\']?\)', re.IGNORECASE)
        
        for match in url_pattern.finditer(css):
            url = self._normalize_url(match.group(1), base_url)
            if url and self._is_same_domain(url):
                urls.add(url)
        
        for match in import_pattern.finditer(css):
            url = self._normalize_url(match.group(1), base_url)
            if url and self._is_same_domain(url):
                urls.add(url)
        
        for match in import_url_pattern.finditer(css):
            url = self._normalize_url(match.group(1), base_url)
            if url and self._is_same_domain(url):
                urls.add(url)
        
        return urls
    
    def _extract_urls_from_js(self, js: str, base_url: str) -> Set[str]:
        """Extract URLs from JavaScript content."""
        urls = set()
        
        if not js or not isinstance(js, str):
            return urls
        
        patterns = [
            re.compile(r'["\']([^"\']*\.(js|css|png|jpg|jpeg|gif|svg|woff2?|ttf|otf|eot|ico|webp|avif|mp4|webm|mp3|json|xml|html?))["\']', re.IGNORECASE),
            re.compile(r'fetch\(["\']([^"\']+)["\']', re.IGNORECASE),
            re.compile(r'import\s+.*?from\s+["\']([^"\']+)["\']', re.IGNORECASE),
            re.compile(r'import\(["\']([^"\']+)["\']', re.IGNORECASE),
            re.compile(r'require\(["\']([^"\']+)["\']', re.IGNORECASE),
        ]
        
        for pattern in patterns:
            for match in pattern.finditer(js):
                url = self._normalize_url(match.group(1), base_url)
                if url and self._is_same_domain(url):
                    urls.add(url)
        
        return urls
    
    def _detect_api_endpoints(self, url: str, content: str) -> List[Dict]:
        """Detect potential API endpoints in content."""
        endpoints = []
        
        if not content or not isinstance(content, str):
            return endpoints
        
        for pattern in self.API_PATTERNS:
            if re.search(pattern, url, re.IGNORECASE):
                endpoints.append({
                    'url': url,
                    'type': 'detected_from_url',
                    'pattern': pattern
                })
        
        api_url_pattern = re.compile(r'["\']((https?://[^"\']*|/[^"\']*)(api|v\d|graphql|rest|ajax|data)[^"\']*)["\']', re.IGNORECASE)
        for match in api_url_pattern.finditer(content):
            api_url = self._normalize_url(match.group(1), url)
            if api_url:
                endpoints.append({
                    'url': api_url,
                    'type': 'detected_from_content',
                    'source': url
                })
        
        return endpoints
    
    def _rewrite_urls_in_html(self, html: str, page_url: str) -> str:
        """Rewrite URLs in HTML for local browsing."""
        try:
            soup = BeautifulSoup(html, 'lxml')
        except:
            soup = BeautifulSoup(html, 'html.parser')
        
        attrs_to_rewrite = [
            ('a', 'href'),
            ('link', 'href'),
            ('script', 'src'),
            ('img', 'src'),
            ('img', 'data-src'),
            ('source', 'src'),
            ('video', 'src'),
            ('video', 'poster'),
            ('audio', 'src'),
            ('iframe', 'src'),
            ('form', 'action'),
            ('use', 'href'),
            ('use', 'xlink:href'),
            ('image', 'href'),
            ('image', 'xlink:href'),
        ]
        
        for tag_name, attr in attrs_to_rewrite:
            for tag in soup.find_all(tag_name, attrs={attr: True}):
                original_url = tag.get(attr)
                if not original_url:
                    continue
                
                if isinstance(original_url, list):
                    original_url = original_url[0] if original_url else ''
                
                if not isinstance(original_url, str):
                    continue
                
                if original_url.startswith(('#', 'javascript:', 'mailto:', 'tel:', 'data:', 'blob:')):
                    continue
                
                full_url = self._normalize_url(original_url, page_url)
                if full_url and self._is_same_domain(full_url):
                    local_path = self._get_local_path(full_url)
                    page_local_path = self._get_local_path(page_url)
                    
                    try:
                        rel_path = os.path.relpath(local_path, page_local_path.parent)
                        tag[attr] = rel_path
                    except ValueError:
                        pass
        
        for style_tag in soup.find_all('style'):
            if style_tag.string and isinstance(style_tag.string, str):
                new_css = self._rewrite_urls_in_css(style_tag.string, page_url)
                style_tag.string = new_css
        
        for tag in soup.find_all(style=True):
            style = tag.get('style', '')
            if style and isinstance(style, str):
                new_style = self._rewrite_urls_in_css(style, page_url)
                tag['style'] = new_style
        
        return str(soup)
    
    def _rewrite_urls_in_css(self, css: str, css_url: str) -> str:
        """Rewrite URLs in CSS for local browsing."""
        if not css or not isinstance(css, str):
            return css
            
        def replace_url(match):
            original_url = match.group(1)
            
            if original_url.startswith('data:'):
                return match.group(0)
            
            full_url = self._normalize_url(original_url, css_url)
            if full_url and self._is_same_domain(full_url):
                local_path = self._get_local_path(full_url)
                css_local_path = self._get_local_path(css_url)
                
                try:
                    rel_path = os.path.relpath(local_path, css_local_path.parent)
                    return f'url("{rel_path}")'
                except ValueError:
                    pass
            
            return match.group(0)
        
        url_pattern = re.compile(r'url\(["\']?([^"\')\s]+)["\']?\)', re.IGNORECASE)
        return url_pattern.sub(replace_url, css)
    
    def _download_single_hidden_file(self, hidden_file: str) -> Optional[Dict]:
        """Download a single hidden file and return result."""
        url = f"{self.base_url}/{hidden_file}"
        result = self._download_content(url)
        
        if result:
            content, content_type, _ = result
            local_path = self._get_local_path(url)
            self._save_file(local_path, content)
            return {
                'file': hidden_file,
                'url': url,
                'content': content,
                'content_type': content_type,
                'is_sitemap': hidden_file.endswith('.xml') and 'sitemap' in hidden_file.lower()
            }
        return None
    
    def _download_hidden_files(self):
        """Download common hidden files using fast parallel batch processing."""
        print("\n[*] Scanning for hidden files and backend files (TURBO MODE)...")
        print(f"    Using {self.config.concurrent_requests} concurrent connections")
        
        discovered_files = 0
        
        all_files_to_check = []
        
        essential_files = [
            'robots.txt', 'sitemap.xml', 'sitemap_index.xml',
            'manifest.json', 'favicon.ico', 'index.html', 'package.json'
        ]
        all_files_to_check.extend(essential_files)
        
        for hidden_file in self.HIDDEN_FILES:
            if '*' not in hidden_file and hidden_file not in essential_files:
                all_files_to_check.append(hidden_file)
        
        for i in range(1, 11):
            all_files_to_check.extend([f"sitemap{i}.xml", f"sitemap-{i}.xml"])
        
        priority_dirs = ['src', 'server', 'api', 'routes', 'controllers', 'lib', 
                        'static', 'assets', 'public', 'dist', '.well-known', 
                        'config', 'models', 'views', 'app', 'components']
        
        dir_test_files = ['index.js', 'index.ts', 'index.html', 'index.json', 
                         'main.js', 'main.ts', 'app.js', 'server.js']
        
        for dir_name in priority_dirs:
            for test_file in dir_test_files:
                all_files_to_check.append(f"{dir_name}/{test_file}")
        
        all_files_to_check = list(dict.fromkeys(all_files_to_check))
        
        print(f"    Checking {len(all_files_to_check)} potential files...")
        
        batch_size = min(self.config.concurrent_requests, 100)
        found_files = []
        
        with ThreadPoolExecutor(max_workers=batch_size) as executor:
            futures = {executor.submit(self._download_single_hidden_file, f): f 
                      for f in all_files_to_check}
            
            with tqdm(total=len(futures), desc="    Scanning files", unit="file", 
                     ncols=70, leave=False) as pbar:
                for future in as_completed(futures):
                    result = future.result()
                    if result:
                        found_files.append(result)
                        discovered_files += 1
                        with self.lock:
                            self.stats.hidden_files_found += 1
                        if result['is_sitemap']:
                            self._parse_sitemap(result['content'], result['content_type'])
                    pbar.update(1)
        
        print(f"\n    [+] Found {discovered_files} hidden/backend files:")
        for f in sorted(found_files, key=lambda x: x['file'])[:20]:
            print(f"        - {f['file']}")
        if len(found_files) > 20:
            print(f"        ... and {len(found_files) - 20} more files")
        
        if self.config.aggressive_scan:
            self._scan_source_directories()
    
    def _scan_source_directories(self):
        """Aggressively scan for source code directories and files."""
        print("\n[*] Aggressive source directory scan...")
        
        source_patterns = [
            'src', 'server', 'api', 'lib', 'app', 'backend',
            'routes', 'controllers', 'models', 'views', 'services',
            'middleware', 'handlers', 'utils', 'helpers', 'common',
            'config', 'configs', 'settings', 'core', 'modules',
            'components', 'pages', 'features', 'store', 'redux',
            'graphql', 'prisma', 'database', 'db', 'migrations',
            'tests', 'test', '__tests__', 'spec', 'e2e'
        ]
        
        common_files = [
            'index.js', 'index.ts', 'index.mjs', 'index.cjs',
            'main.js', 'main.ts', 'app.js', 'app.ts',
            'server.js', 'server.ts', 'routes.js', 'routes.ts',
            'router.js', 'router.ts', 'api.js', 'api.ts',
            'config.js', 'config.ts', 'config.json',
            'schema.js', 'schema.ts', 'schema.graphql', 'schema.prisma',
            'types.ts', 'types.d.ts', 'interfaces.ts',
            'constants.js', 'constants.ts', 'utils.js', 'utils.ts',
            'helpers.js', 'helpers.ts', 'middleware.js', 'middleware.ts'
        ]
        
        paths_to_check = []
        
        for dir_name in source_patterns:
            for file_name in common_files:
                paths_to_check.append(f"{dir_name}/{file_name}")
            
            for subdir in ['api', 'routes', 'handlers', 'utils', 'lib']:
                for file_name in common_files[:5]:
                    paths_to_check.append(f"{dir_name}/{subdir}/{file_name}")
        
        paths_to_check = list(dict.fromkeys(paths_to_check))
        
        batch_size = min(self.config.concurrent_requests, 50)
        found_count = 0
        
        with ThreadPoolExecutor(max_workers=batch_size) as executor:
            futures = {executor.submit(self._download_single_hidden_file, f): f 
                      for f in paths_to_check}
            
            for future in as_completed(futures):
                result = future.result()
                if result:
                    found_count += 1
                    with self.lock:
                        self.stats.data_files_found += 1
        
        if found_count > 0:
            print(f"    [+] Found {found_count} additional source files")
    
    def _parse_sitemap(self, content: bytes, content_type: str):
        """Parse sitemap XML and extract URLs."""
        try:
            xml_content = content.decode('utf-8', errors='replace')
            loc_pattern = re.compile(r'<loc>([^<]+)</loc>', re.IGNORECASE)
            
            for match in loc_pattern.finditer(xml_content):
                url = match.group(1).strip()
                if url and self._is_same_domain(url):
                    with self.lock:
                        self.discovered_paths.add(url)
        except Exception:
            pass
    
    def _process_page(self, url: str, depth: int) -> Set[str]:
        """Process a single page and return discovered URLs."""
        if depth > self.config.max_depth:
            return set()
        
        if url in self.visited_urls:
            return set()
        
        with self.lock:
            if self.stats.pages_downloaded >= self.config.max_pages:
                return set()
            self.visited_urls.add(url)
        
        result = self._download_content(url)
        if not result:
            return set()
        
        content, content_type, headers = result
        local_path = self._get_local_path(url)
        
        discovered_urls = set()
        
        if 'text/html' in content_type or 'application/xhtml' in content_type:
            try:
                detected = chardet.detect(content)
                encoding = detected['encoding'] if detected and detected['encoding'] else 'utf-8'
                html = content.decode(encoding, errors='replace')
            except:
                html = content.decode('utf-8', errors='replace')
            
            urls = self._extract_urls_from_html(html, url)
            discovered_urls.update(urls['pages'])
            
            for asset_url in urls['assets']:
                if asset_url not in self.downloaded_assets:
                    self._download_asset(asset_url)
            
            if self.config.capture_api:
                endpoints = self._detect_api_endpoints(url, html)
                with self.lock:
                    self.api_endpoints.extend(endpoints)
                    self.stats.api_endpoints_found += len(endpoints)
            
            if self.config.rewrite_links:
                html = self._rewrite_urls_in_html(html, url)
                content = html.encode('utf-8')
            
            with self.lock:
                self.stats.pages_downloaded += 1
        
        elif 'text/css' in content_type:
            try:
                css = content.decode('utf-8', errors='replace')
            except:
                css = content.decode('latin-1', errors='replace')
            
            css_urls = self._extract_urls_from_css(css, url)
            for asset_url in css_urls:
                if asset_url not in self.downloaded_assets:
                    self._download_asset(asset_url)
            
            if self.config.rewrite_links:
                css = self._rewrite_urls_in_css(css, url)
                content = css.encode('utf-8')
        
        elif 'javascript' in content_type or 'application/json' in content_type:
            try:
                js = content.decode('utf-8', errors='replace')
                js_urls = self._extract_urls_from_js(js, url)
                for asset_url in js_urls:
                    if asset_url not in self.downloaded_assets:
                        self._download_asset(asset_url)
            except:
                pass
        
        self._save_file(local_path, content)
        
        with self.lock:
            self.url_mapping[url] = str(local_path)
        
        time.sleep(self.config.delay_between_requests)
        
        return discovered_urls
    
    def _download_asset(self, url: str):
        """Download a single asset."""
        if url in self.downloaded_assets:
            return
        
        with self.lock:
            self.downloaded_assets.add(url)
        
        ext = os.path.splitext(urllib.parse.urlparse(url).path)[1].lower()
        
        should_download = True
        if ext in self.MEDIA_EXTENSIONS['images'] or ext in self.MEDIA_EXTENSIONS['videos'] or ext in self.MEDIA_EXTENSIONS['audio']:
            should_download = self.config.download_media
        elif ext in self.MEDIA_EXTENSIONS['fonts']:
            should_download = self.config.download_fonts
        elif ext in self.MEDIA_EXTENSIONS['documents']:
            should_download = self.config.download_documents
        
        if not should_download:
            return
        
        result = self._download_content(url)
        if result:
            content, content_type, _ = result
            local_path = self._get_local_path(url)
            self._save_file(local_path, content)
            
            if 'text/css' in content_type:
                try:
                    css = content.decode('utf-8', errors='replace')
                    css_urls = self._extract_urls_from_css(css, url)
                    for css_url in css_urls:
                        if css_url not in self.downloaded_assets:
                            self._download_asset(css_url)
                    
                    if self.config.rewrite_links:
                        css = self._rewrite_urls_in_css(css, url)
                        self._save_file(local_path, css.encode('utf-8'))
                except:
                    pass
            
            elif 'javascript' in content_type:
                try:
                    js = content.decode('utf-8', errors='replace')
                    js_urls = self._extract_urls_from_js(js, url)
                    for js_url in js_urls:
                        if js_url not in self.downloaded_assets:
                            self._download_asset(js_url)
                except:
                    pass
            
            with self.lock:
                self.stats.assets_downloaded += 1
                self.url_mapping[url] = str(local_path)
    
    def clone(self):
        """Start the cloning process."""
        print(f"\n{'='*60}")
        print(f"  Advanced Web Cloner - Starting Deep Clone")
        print(f"{'='*60}")
        print(f"\n  Target: {self.config.url}")
        print(f"  Output: {self.output_dir}")
        print(f"  Max Depth: {self.config.max_depth}")
        print(f"  Max Pages: {self.config.max_pages}")
        print(f"  Concurrent Requests: {self.config.concurrent_requests}")
        print(f"\n{'='*60}\n")
        
        if self.config.clone_hidden:
            self._download_hidden_files()
        
        print("\n[*] Starting deep page crawl...")
        
        urls_to_process: List[Tuple[str, int]] = [(self.config.url, 0)]
        
        for discovered_url in list(self.discovered_paths):
            if discovered_url.startswith('http'):
                urls_to_process.append((discovered_url, 1))
        
        with tqdm(total=self.config.max_pages, desc="Pages", unit="page") as pbar:
            with ThreadPoolExecutor(max_workers=self.config.concurrent_requests) as executor:
                while urls_to_process and self.stats.pages_downloaded < self.config.max_pages:
                    batch = []
                    while urls_to_process and len(batch) < self.config.concurrent_requests:
                        url, depth = urls_to_process.pop(0)
                        if url not in self.visited_urls and url not in self.queued_urls:
                            batch.append((url, depth))
                            self.queued_urls.add(url)
                    
                    if not batch:
                        break
                    
                    futures = {
                        executor.submit(self._process_page, url, depth): (url, depth)
                        for url, depth in batch
                    }
                    
                    for future in as_completed(futures):
                        url, depth = futures[future]
                        try:
                            discovered = future.result()
                            for new_url in discovered:
                                if new_url not in self.visited_urls and new_url not in self.queued_urls:
                                    urls_to_process.append((new_url, depth + 1))
                        except Exception as e:
                            with self.lock:
                                self.stats.errors += 1
                        
                        pbar.update(1)
                        pbar.set_postfix({
                            'assets': self.stats.assets_downloaded,
                            'hidden': self.stats.hidden_files_found,
                            'errors': self.stats.errors
                        })
        
        self.stats.end_time = time.time()
        self._save_index()
        self._print_summary()
    
    def _save_index(self):
        """Save the scraping index with all metadata."""
        index = {
            'metadata': {
                'url': self.config.url,
                'domain': self.base_domain,
                'cloned_at': datetime.now().isoformat(),
                'duration_seconds': self.stats.duration,
                'tool': 'Advanced Web Cloner - Professional Edition',
                'auth_used': bool(self.config.cookies or self.config.auth_token),
                'auth_method': (
                    'cookie' if self.config.cookies else
                    ('bearer' if self.config.auth_token else 'none')
                ),
                'user_agent': self.config.user_agent,
            },
            'config': asdict(self.config),
            'statistics': {
                'pages_downloaded': self.stats.pages_downloaded,
                'assets_downloaded': self.stats.assets_downloaded,
                'hidden_files_found': self.stats.hidden_files_found,
                'api_endpoints_found': self.stats.api_endpoints_found,
                'forms_found': self.stats.forms_found,
                'external_links_found': self.stats.external_links,
                'errors': self.stats.errors,
                'total_size_mb': round(self.stats.total_size_mb, 2)
            },
            'url_mapping': self.url_mapping,
            'api_endpoints': self.api_endpoints,
            'forms': self.forms,
            'external_links': list(self.external_links),
            'discovered_paths': list(self.discovered_paths),
            'errors': self.errors
        }
        
        index_path = self.output_dir / 'scraping_index.json'
        with open(index_path, 'w', encoding='utf-8') as f:
            json.dump(index, f, indent=2, ensure_ascii=False)
    
    def _print_summary(self):
        """Print cloning summary."""
        print(f"\n{'='*60}")
        print(f"  Deep Clone Complete!")
        print(f"{'='*60}")
        print(f"\n  Summary:")
        print(f"  --------")
        print(f"  Pages Downloaded:     {self.stats.pages_downloaded}")
        print(f"  Assets Downloaded:    {self.stats.assets_downloaded}")
        print(f"  Hidden Files Found:   {self.stats.hidden_files_found}")
        print(f"  API Endpoints Found:  {self.stats.api_endpoints_found}")
        print(f"  Forms Found:          {self.stats.forms_found}")
        print(f"  External Links:       {self.stats.external_links}")
        print(f"  Errors:               {self.stats.errors}")
        print(f"  Total Size:           {self.stats.total_size_mb:.2f} MB")
        print(f"  Duration:             {self.stats.duration:.2f} seconds")
        print(f"\n  Output Directory: {self.output_dir}")
        print(f"  Index File: {self.output_dir}/scraping_index.json")
        print(f"\n{'='*60}\n")


class PreviewServer:
    """Local server for previewing cloned websites on port 5000."""
    
    def __init__(self, directory: Path, port: int = 5000):
        self.directory = directory
        self.port = port
        self.server = None
        self.original_dir = os.getcwd()
    
    def _find_all_html_files(self) -> List[Dict]:
        """Find all HTML files in the directory."""
        html_files = []
        
        for html_file in sorted(self.directory.rglob('*.html')):
            rel_path = html_file.relative_to(self.directory)
            html_files.append({
                'path': str(rel_path),
                'full_path': str(html_file),
                'name': html_file.name,
                'size': html_file.stat().st_size
            })
        
        for htm_file in sorted(self.directory.rglob('*.htm')):
            rel_path = htm_file.relative_to(self.directory)
            html_files.append({
                'path': str(rel_path),
                'full_path': str(htm_file),
                'name': htm_file.name,
                'size': htm_file.stat().st_size
            })
        
        return html_files
    
    def _find_entry_point(self) -> Optional[str]:
        """Find the main HTML entry point."""
        candidates = ['index.html', 'index.htm', 'home.html', 'default.html']
        
        for candidate in candidates:
            if (self.directory / candidate).exists():
                return '/'
        
        for html_file in self.directory.rglob('index.html'):
            rel_path = html_file.relative_to(self.directory)
            return '/' + str(rel_path.parent) + '/'
        
        for html_file in self.directory.rglob('*.html'):
            rel_path = html_file.relative_to(self.directory)
            return '/' + str(rel_path)
        
        return None
    
    def start(self):
        """Start the preview server on port 5000."""
        entry_point = self._find_entry_point()
        
        if not entry_point:
            print("\n  No HTML files found in the directory.")
            return
        
        os.chdir(self.directory)
        
        class CORSRequestHandler(SimpleHTTPRequestHandler):
            def end_headers(self):
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
                self.send_header('Access-Control-Allow-Headers', '*')
                self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
                self.send_header('Pragma', 'no-cache')
                self.send_header('Expires', '0')
                super().end_headers()
            
            def do_OPTIONS(self):
                self.send_response(200)
                self.end_headers()
            
            def log_message(self, format, *args):
                pass
            
            def do_GET(self):
                path = self.path.split('?')[0]
                
                if path.endswith('/') and not os.path.exists(self.translate_path(path + 'index.html')):
                    pass
                
                super().do_GET()
        
        self.port = 5000
        
        try:
            self.server = HTTPServer(('0.0.0.0', self.port), CORSRequestHandler)
        except OSError as e:
            if "Address already in use" in str(e):
                print(f"\n  Port {self.port} is already in use. Trying to stop existing server...")
                time.sleep(1)
                try:
                    self.server = HTTPServer(('0.0.0.0', self.port), CORSRequestHandler)
                except:
                    print(f"  Could not start server on port {self.port}")
                    os.chdir(self.original_dir)
                    return
            else:
                raise
        
        print(f"\n{'='*60}")
        print(f"  Preview Server Started")
        print(f"{'='*60}")
        print(f"\n  Directory: {self.directory}")
        print(f"  URL: http://0.0.0.0:{self.port}{entry_point}")
        print(f"\n  The website is now running. Press Ctrl+C to stop.")
        print(f"\n{'='*60}\n")
        
        try:
            self.server.serve_forever()
        except KeyboardInterrupt:
            print("\n\n  Server stopped.")
            self.server.shutdown()
        finally:
            os.chdir(self.original_dir)


def list_cloned_websites() -> List[Dict]:
    """List all cloned websites with their statistics."""
    websites = []
    
    for item in Path('.').iterdir():
        if item.is_dir() and item.name.startswith('mirror_'):
            index_file = item / 'scraping_index.json'
            
            html_files = list(item.rglob('*.html')) + list(item.rglob('*.htm'))
            all_files = list(item.rglob('*'))
            all_files = [f for f in all_files if f.is_file()]
            
            if not all_files:
                continue
            
            total_size = sum(f.stat().st_size for f in all_files)
            size_mb = total_size / (1024 * 1024)
            
            parts = item.name.split('_')
            if len(parts) >= 2:
                domain = parts[1]
            else:
                domain = 'Unknown'
            
            if len(parts) >= 3:
                timestamp = parts[2]
                try:
                    cloned_at = f"{timestamp[:4]}-{timestamp[4:6]}-{timestamp[6:8]} {timestamp[8:10]}:{timestamp[10:12]}:{timestamp[12:14]}"
                except:
                    cloned_at = 'Unknown'
            else:
                cloned_at = 'Unknown'
            
            if index_file.exists():
                try:
                    with open(index_file, 'r') as f:
                        index = json.load(f)
                        websites.append({
                            'directory': str(item),
                            'domain': index.get('metadata', {}).get('domain', domain),
                            'url': index.get('metadata', {}).get('url', f'https://{domain}'),
                            'cloned_at': index.get('metadata', {}).get('cloned_at', cloned_at),
                            'pages': index.get('statistics', {}).get('pages_downloaded', len(html_files)),
                            'assets': index.get('statistics', {}).get('assets_downloaded', len(all_files) - len(html_files)),
                            'hidden_files': index.get('statistics', {}).get('hidden_files_found', 0),
                            'size_mb': index.get('statistics', {}).get('total_size_mb', size_mb),
                            'html_files': len(html_files),
                            'total_files': len(all_files)
                        })
                except json.JSONDecodeError:
                    websites.append({
                        'directory': str(item),
                        'domain': domain,
                        'url': f'https://{domain}',
                        'cloned_at': cloned_at,
                        'pages': len(html_files),
                        'assets': len(all_files) - len(html_files),
                        'hidden_files': 0,
                        'size_mb': size_mb,
                        'html_files': len(html_files),
                        'total_files': len(all_files)
                    })
            else:
                websites.append({
                    'directory': str(item),
                    'domain': domain,
                    'url': f'https://{domain}',
                    'cloned_at': cloned_at,
                    'pages': len(html_files),
                    'assets': len(all_files) - len(html_files),
                    'hidden_files': 0,
                    'size_mb': size_mb,
                    'html_files': len(html_files),
                    'total_files': len(all_files)
                })
    
    return sorted(websites, key=lambda x: x.get('cloned_at', ''), reverse=True)


def list_files_in_website(directory: Path) -> List[Dict]:
    """List all files in a cloned website."""
    files = []
    
    for file_path in sorted(directory.rglob('*')):
        if file_path.is_file():
            rel_path = file_path.relative_to(directory)
            files.append({
                'path': str(rel_path),
                'full_path': str(file_path),
                'name': file_path.name,
                'size': file_path.stat().st_size,
                'extension': file_path.suffix.lower(),
                'is_html': file_path.suffix.lower() in ['.html', '.htm']
            })
    
    return files


def print_menu():
    """Print the main menu."""
    print(f"\n{'='*60}")
    print(f"  Advanced Web Cloner - Professional Edition")
    print(f"{'='*60}")
    print("""
  1. Clone Website (Full Deep Mirror)
  2. Clone Website (Custom Settings)
  3. Quick Clone (Fast Mode)
  4. Preview Cloned Website
  5. List Cloned Websites
  6. Exit
    """)
    print(f"{'='*60}")


def get_url_input() -> str:
    """Get and validate URL input from user."""
    while True:
        url = input("\n  Enter website URL: ").strip()
        
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        if validators.url(url):
            return url
        else:
            print("  Invalid URL. Please enter a valid website URL.")


def clone_full_mirror():
    """Clone with default deep settings."""
    url = get_url_input()
    config = CloneConfig(url=url)
    cloner = WebCloner(config)
    cloner.clone()


def clone_custom():
    """Clone with custom settings."""
    url = get_url_input()
    
    print("\n  Configure cloning settings (press Enter for defaults):")
    
    try:
        max_depth = input("  Max depth [15]: ").strip()
        max_depth = int(max_depth) if max_depth else 15
        
        max_pages = input("  Max pages [10000]: ").strip()
        max_pages = int(max_pages) if max_pages else 10000
        
        concurrent = input("  Concurrent requests [25]: ").strip()
        concurrent = int(concurrent) if concurrent else 25
        
        media = input("  Download media (y/n) [y]: ").strip().lower()
        download_media = media != 'n'
        
        fonts = input("  Download fonts (y/n) [y]: ").strip().lower()
        download_fonts = fonts != 'n'
        
        rewrite = input("  Rewrite links for local testing (y/n) [y]: ").strip().lower()
        rewrite_links = rewrite != 'n'
        
        capture_api = input("  Capture API endpoints (y/n) [y]: ").strip().lower()
        capture_api_val = capture_api != 'n'
        
        clone_hidden = input("  Clone hidden files (y/n) [y]: ").strip().lower()
        clone_hidden_val = clone_hidden != 'n'
        
        # 新增：手動輸入 Cookie 與 Bearer token（可留空）
        cookies = input("  Cookie string (optional, leave empty if none): ").strip()
        auth_token = input("  Bearer token (optional, leave empty if none): ").strip()
        
    except ValueError:
        print("  Invalid input. Using default values.")
        max_depth, max_pages, concurrent = 15, 10000, 25
        download_media, download_fonts, rewrite_links, capture_api_val, clone_hidden_val = True, True, True, True, True
        cookies, auth_token = "", ""
    
    config = CloneConfig(
        url=url,
        max_depth=max_depth,
        max_pages=max_pages,
        concurrent_requests=concurrent,
        download_media=download_media,
        download_fonts=download_fonts,
        rewrite_links=rewrite_links,
        capture_api=capture_api_val,
        clone_hidden=clone_hidden_val,
        cookies=cookies,
        auth_token=auth_token
    )
    
    cloner = WebCloner(config)
    cloner.clone()


def clone_quick():
    """Quick clone with minimal settings."""
    url = get_url_input()
    
    # Quick mode 仍允許手動提供驗證資訊（可留空）
    cookies = input("  Cookie string (optional, leave empty if none): ").strip()
    auth_token = input("  Bearer token (optional, leave empty if none): ").strip()
    
    config = CloneConfig(
        url=url,
        max_depth=5,
        max_pages=200,
        concurrent_requests=30,
        download_media=False,
        download_fonts=False,
        capture_api=False,
        clone_hidden=False,
        cookies=cookies,
        auth_token=auth_token
    )
    
    cloner = WebCloner(config)
    cloner.clone()


def preview_website():
    """Preview a cloned website with comprehensive file listing and index selection."""
    websites = list_cloned_websites()
    
    if not websites:
        print("\n  No cloned websites found.")
        print("  Use option 1, 2, or 3 to clone a website first.")
        return
    
    print(f"\n{'='*60}")
    print(f"  STEP 1: Select a Cloned Website")
    print(f"{'='*60}\n")
    
    for i, site in enumerate(websites, 1):
        print(f"  [{i}] {site['domain']}")
        cloned_date = site['cloned_at'][:19] if site['cloned_at'] != 'Unknown' else 'Unknown'
        print(f"      Directory: {site['directory']}")
        print(f"      Cloned: {cloned_date}")
        print(f"      Pages: {site['pages']}, Assets: {site['assets']}")
        print(f"      Total Files: {site['total_files']}, Size: {site['size_mb']:.2f} MB")
        print()
    
    print(f"  [0] Go back to main menu")
    print(f"\n{'='*60}")
    
    try:
        choice = input("\n  Enter website number to preview: ").strip()
        
        if choice == '0' or choice == '':
            return
            
        website_index = int(choice) - 1
        
        if not (0 <= website_index < len(websites)):
            print("  Invalid selection. Please enter a valid number.")
            return
        
        selected_site = websites[website_index]
        directory = Path(selected_site['directory'])
        
        files = list_files_in_website(directory)
        html_files = [f for f in files if f['is_html']]
        css_files = [f for f in files if f['extension'] == '.css']
        js_files = [f for f in files if f['extension'] == '.js']
        image_files = [f for f in files if f['extension'] in ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.ico', '.avif']]
        font_files = [f for f in files if f['extension'] in ['.woff', '.woff2', '.ttf', '.otf', '.eot']]
        other_files = [f for f in files if f not in html_files + css_files + js_files + image_files + font_files]
        
        print(f"\n{'='*60}")
        print(f"  STEP 2: File Listing for {selected_site['domain']}")
        print(f"{'='*60}")
        print(f"\n  Directory: {directory}")
        print(f"\n  File Summary:")
        print(f"  {'-'*50}")
        print(f"  HTML Files:   {len(html_files):>6}")
        print(f"  CSS Files:    {len(css_files):>6}")
        print(f"  JS Files:     {len(js_files):>6}")
        print(f"  Images:       {len(image_files):>6}")
        print(f"  Fonts:        {len(font_files):>6}")
        print(f"  Other Files:  {len(other_files):>6}")
        print(f"  {'-'*50}")
        print(f"  TOTAL:        {len(files):>6}")
        
        print(f"\n  HTML Files (Entry Points):")
        print(f"  {'-'*50}")
        
        display_limit = min(30, len(html_files))
        for i, f in enumerate(html_files[:display_limit], 1):
            size_kb = f['size'] / 1024
            print(f"  [{i:>3}] {f['path'][:50]:<50} ({size_kb:>7.1f} KB)")
        
        if len(html_files) > display_limit:
            print(f"        ... and {len(html_files) - display_limit} more HTML files")
        
        print(f"\n{'='*60}")
        print(f"  STEP 3: Preview Options")
        print(f"{'='*60}")
        print(f"\n  [Enter] - Start preview server on port 5000 (serves all files)")
        print(f"  [0]     - Go back to main menu")
        
        file_choice = input("\n  Enter choice: ").strip()
        
        if file_choice == '0':
            print("  Returning to main menu...")
            return
        
        print(f"\n{'='*60}")
        print(f"  Starting Preview Server")
        print(f"{'='*60}")
        print(f"\n  Website: {selected_site['domain']}")
        print(f"  Directory: {directory}")
        print(f"  Port: 5000")
        print(f"\n  Server will serve all {len(files)} files without modification.")
        
        server = PreviewServer(directory, port=5000)
        server.start()
        
    except ValueError:
        print("  Invalid input. Please enter a valid number.")
    except KeyboardInterrupt:
        print("\n  Cancelled.")


def list_websites():
    """List all cloned websites with detailed file information."""
    websites = list_cloned_websites()
    
    if not websites:
        print("\n  No cloned websites found.")
        return
    
    print(f"\n{'='*60}")
    print(f"  Cloned Websites - Detailed View")
    print(f"{'='*60}\n")
    
    for i, site in enumerate(websites, 1):
        print(f"  [{i}] Domain: {site['domain']}")
        print(f"      URL: {site['url']}")
        print(f"      Directory: {site['directory']}")
        cloned_date = site['cloned_at'][:19] if site['cloned_at'] != 'Unknown' else 'Unknown'
        print(f"      Cloned: {cloned_date}")
        print(f"      Statistics:")
        print(f"        - Pages: {site['pages']}")
        print(f"        - Assets: {site['assets']}")
        print(f"        - Hidden Files: {site.get('hidden_files', 0)}")
        print(f"        - Total Files: {site['total_files']}")
        print(f"        - HTML Files: {site['html_files']}")
        print(f"        - Size: {site['size_mb']:.2f} MB")
        print(f"  {'-'*50}")
    
    print(f"\n{'='*60}")
    
    try:
        view_files = input("\n  Enter website number to view all files (or press Enter to skip): ").strip()
        if view_files:
            idx = int(view_files) - 1
            if 0 <= idx < len(websites):
                directory = Path(websites[idx]['directory'])
                files = list_files_in_website(directory)
                
                print(f"\n{'='*60}")
                print(f"  All Files in: {websites[idx]['domain']}")
                print(f"{'='*60}\n")
                
                for ext in ['.html', '.htm', '.css', '.js', '.json', '.xml', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.woff', '.woff2', '.ttf', '.otf', '.pdf']:
                    ext_files = [f for f in files if f['extension'] == ext]
                    if ext_files:
                        print(f"\n  {ext.upper()} Files ({len(ext_files)}):")
                        for f in ext_files[:20]:
                            size_kb = f['size'] / 1024
                            print(f"    - {f['path']} ({size_kb:.1f} KB)")
                        if len(ext_files) > 20:
                            print(f"    ... and {len(ext_files) - 20} more")
                
                other_files = [f for f in files if f['extension'] not in ['.html', '.htm', '.css', '.js', '.json', '.xml', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.woff', '.woff2', '.ttf', '.otf', '.pdf']]
                if other_files:
                    print(f"\n  Other Files ({len(other_files)}):")
                    for f in other_files[:10]:
                        size_kb = f['size'] / 1024
                        print(f"    - {f['path']} ({size_kb:.1f} KB)")
                    if len(other_files) > 10:
                        print(f"    ... and {len(other_files) - 10} more")
    except ValueError:
        pass


def main():
    """Main entry point."""
    while True:
        print_menu()
        
        try:
            choice = input("  Select option (1-6): ").strip()
            
            if choice == '1':
                clone_full_mirror()
            elif choice == '2':
                clone_custom()
            elif choice == '3':
                clone_quick()
            elif choice == '4':
                preview_website()
            elif choice == '5':
                list_websites()
            elif choice == '6':
                print("\n  Goodbye!\n")
                break
            else:
                print("\n  Invalid option. Please select 1-6.")
                
        except KeyboardInterrupt:
            print("\n\n  Operation cancelled.")
        except Exception as e:
            print(f"\n  Error: {e}")


if __name__ == '__main__':
    main()
