#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const PROJECT_ROOT = process.argv[2];
const OUTPUT_FILE = process.argv[3];

if (!PROJECT_ROOT || !OUTPUT_FILE) {
  process.stderr.write('Usage: node ua-project-scan.js <project-root> <output-file>\n');
  process.exit(1);
}

if (!fs.existsSync(PROJECT_ROOT)) {
  process.stderr.write(`Project root does not exist: ${PROJECT_ROOT}\n`);
  process.exit(1);
}

// ── Step 1: File Discovery ──────────────────────────────────────────────────
let allFiles = [];
try {
  const result = spawnSync('git', ['ls-files'], { cwd: PROJECT_ROOT, encoding: 'utf8' });
  if (result.status === 0 && result.stdout.trim()) {
    allFiles = result.stdout.trim().split('\n').filter(Boolean);
  } else {
    throw new Error('git ls-files failed');
  }
} catch (e) {
  function walk(dir, base) {
    const entries = fs.readdirSync(dir, { withFileTypes: true });
    for (const entry of entries) {
      const rel = base ? base + '/' + entry.name : entry.name;
      if (entry.isDirectory()) {
        walk(path.join(dir, entry.name), rel);
      } else {
        allFiles.push(rel);
      }
    }
  }
  walk(PROJECT_ROOT, '');
}

// ── Step 2: Hardcoded Exclusion Filtering ───────────────────────────────────
const EXCLUDE_DIR_SEGMENTS = new Set([
  'node_modules', '.git', 'vendor', 'venv', '.venv', '__pycache__',
  'dist', 'build', 'out', 'coverage', '.next', '.cache', '.turbo',
  'target', 'obj', '.idea', '.vscode'
]);

const EXCLUDE_EXTENSIONS = new Set([
  '.png', '.jpg', '.jpeg', '.gif', '.ico', '.woff', '.woff2',
  '.ttf', '.eot', '.mp3', '.mp4', '.pdf', '.zip', '.tar', '.gz'
]);

const EXCLUDE_FILENAMES = new Set([
  'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml',
  'LICENSE', '.gitignore', '.editorconfig', '.prettierrc'
]);

function isExcludedByDefault(filePath) {
  const parts = filePath.split('/');
  const filename = parts[parts.length - 1];

  for (let i = 0; i < parts.length - 1; i++) {
    if (EXCLUDE_DIR_SEGMENTS.has(parts[i])) return true;
  }

  if (EXCLUDE_FILENAMES.has(filename)) return true;

  const ext = path.extname(filename).toLowerCase();
  if (EXCLUDE_EXTENSIONS.has(ext)) return true;

  if (filename.endsWith('.lock')) return true;
  if (filename.endsWith('.min.js') || filename.endsWith('.min.css') || filename.endsWith('.map')) return true;
  if (/\.generated\./.test(filename)) return true;
  if (filename.endsWith('.log')) return true;
  if (filename.startsWith('.eslintrc')) return true;
  if (filename === '.DS_Store') return true;

  return false;
}

let filteredFiles = allFiles.filter(f => !isExcludedByDefault(f));

// ── Step 2.5: .understandignore ─────────────────────────────────────────────
let filteredByIgnore = 0;
const ignoreFilePaths = [
  path.join(PROJECT_ROOT, '.understand-anything', '.understandignore'),
  path.join(PROJECT_ROOT, '.understandignore')
];

const ignoreContents = [];
for (const igPath of ignoreFilePaths) {
  if (fs.existsSync(igPath)) {
    ignoreContents.push(fs.readFileSync(igPath, 'utf8'));
  }
}

if (ignoreContents.length > 0) {
  let ignoreModule = null;
  try {
    ignoreModule = require(path.join(PROJECT_ROOT, 'node_modules', 'ignore'));
  } catch (e) {
    try { ignoreModule = require('ignore'); } catch (e2) {}
  }

  const patterns = ignoreContents.join('\n').split('\n')
    .map(l => l.trim())
    .filter(l => l && !l.startsWith('#'));

  if (ignoreModule) {
    const ig = ignoreModule();
    ig.add(patterns);
    const beforeCount = filteredFiles.length;
    filteredFiles = filteredFiles.filter(f => !ig.ignores(f));
    filteredByIgnore = beforeCount - filteredFiles.length;
  } else {
    function matchesPattern(filePath, pattern) {
      if (pattern.startsWith('!')) return false;
      if (pattern.endsWith('/')) {
        const dir = pattern.slice(0, -1);
        return filePath === dir || filePath.startsWith(dir + '/');
      }
      const regexStr = pattern
        .replace(/[.+^${}()|[\]\\]/g, '\\$&')
        .replace(/\*\*/g, '###GLOBSTAR###')
        .replace(/\*/g, '[^/]*')
        .replace(/###GLOBSTAR###/g, '.*');
      const regex = new RegExp('^' + regexStr + '(/.*)?$');
      return regex.test(filePath) || regex.test(filePath.split('/').pop());
    }

    const beforeCount = filteredFiles.length;
    filteredFiles = filteredFiles.filter(f => {
      return !patterns.some(p => !p.startsWith('!') && matchesPattern(f, p));
    });
    filteredByIgnore = beforeCount - filteredFiles.length;
  }
}

// ── Step 3: Language Detection ───────────────────────────────────────────────
const EXT_TO_LANG = {
  '.ts': 'typescript', '.tsx': 'typescript',
  '.js': 'javascript', '.jsx': 'javascript', '.mjs': 'javascript', '.cjs': 'javascript',
  '.py': 'python',
  '.go': 'go',
  '.rs': 'rust',
  '.java': 'java',
  '.rb': 'ruby',
  '.cpp': 'cpp', '.cc': 'cpp', '.cxx': 'cpp', '.h': 'cpp', '.hpp': 'cpp',
  '.c': 'c',
  '.cs': 'csharp',
  '.swift': 'swift',
  '.kt': 'kotlin',
  '.php': 'php',
  '.vue': 'vue',
  '.svelte': 'svelte',
  '.sh': 'shell', '.bash': 'shell',
  '.ps1': 'powershell',
  '.bat': 'batch', '.cmd': 'batch',
  '.md': 'markdown', '.rst': 'markdown',
  '.yaml': 'yaml', '.yml': 'yaml',
  '.json': 'json',
  '.jsonc': 'jsonc',
  '.toml': 'toml',
  '.sql': 'sql',
  '.graphql': 'graphql', '.gql': 'graphql',
  '.proto': 'protobuf',
  '.tf': 'terraform', '.tfvars': 'terraform',
  '.html': 'html', '.htm': 'html',
  '.css': 'css', '.scss': 'css', '.sass': 'css', '.less': 'css',
  '.xml': 'xml',
  '.cfg': 'config', '.ini': 'config', '.env': 'config',
  '.txt': 'text',
  '.csv': 'csv',
};

const BASENAME_TO_LANG = {
  'Dockerfile': 'dockerfile',
  'Makefile': 'makefile',
  'Jenkinsfile': 'jenkinsfile',
};

function detectLanguage(filePath) {
  const basename = path.basename(filePath);
  if (BASENAME_TO_LANG[basename]) return BASENAME_TO_LANG[basename];
  // .env, .env.example, .env.local, .env.production, etc.
  if (/^\.env(\.\w+)?$/.test(basename)) return 'config';
  const ext = path.extname(basename).toLowerCase();
  if (EXT_TO_LANG[ext]) return EXT_TO_LANG[ext];
  return ext ? ext.slice(1).toLowerCase() : 'unknown';
}

// ── Step 4: File Category Detection ─────────────────────────────────────────
function detectCategory(filePath) {
  const basename = path.basename(filePath);
  // Handle dotfiles like .env.example, .env.local, .env.production, etc.
  if (/^\.env(\.\w+)?$/.test(basename)) return 'config';
  const ext = path.extname(basename).toLowerCase();
  const parts = filePath.split('/');

  if (basename === 'Dockerfile' || /^docker-compose/.test(basename)) return 'infra';
  if (ext === '.tf' || ext === '.tfvars') return 'infra';
  if (basename === 'Makefile' || basename === 'Jenkinsfile' || basename === 'Procfile' || basename === 'Vagrantfile') return 'infra';
  if (filePath.startsWith('.github/workflows/') || filePath.startsWith('.circleci/') || basename === '.gitlab-ci.yml') return 'infra';
  if (parts.includes('k8s') || parts.includes('kubernetes')) return 'infra';
  if (filePath.endsWith('.k8s.yaml') || filePath.endsWith('.k8s.yml')) return 'infra';

  if (['.md', '.rst'].includes(ext)) return 'docs';
  if (ext === '.txt') return 'docs';

  if (['.yaml', '.yml', '.json', '.jsonc', '.toml', '.xml', '.cfg', '.ini', '.env'].includes(ext)) return 'config';
  if (['tsconfig.json', 'package.json', 'pyproject.toml', 'Cargo.toml', 'go.mod', 'requirements.txt', 'Gemfile', 'setup.py', 'setup.cfg', 'Pipfile'].includes(basename)) return 'config';

  if (['.sql', '.graphql', '.gql', '.proto', '.csv'].includes(ext)) return 'data';
  if (ext === '.prisma' || basename.endsWith('.schema.json')) return 'data';

  if (['.sh', '.bash', '.ps1', '.bat', '.cmd'].includes(ext)) return 'script';

  if (['.html', '.htm', '.css', '.scss', '.sass', '.less'].includes(ext)) return 'markup';

  return 'code';
}

// ── Step 5: Line Counting ────────────────────────────────────────────────────
function countLines(files) {
  const counts = {};
  if (files.length === 0) return counts;

  const BATCH_SIZE = 100;
  for (let i = 0; i < files.length; i += BATCH_SIZE) {
    const batch = files.slice(i, i + BATCH_SIZE);
    const absPaths = batch.map(f => path.join(PROJECT_ROOT, f));
    try {
      const result = spawnSync('wc', ['-l', ...absPaths], { encoding: 'utf8' });
      if (result.stdout) {
        const lines = result.stdout.trim().split('\n');
        for (const line of lines) {
          const match = line.trim().match(/^(\d+)\s+(.+)$/);
          if (match) {
            const absPath = match[2];
            const relPath = path.relative(PROJECT_ROOT, absPath);
            counts[relPath] = parseInt(match[1], 10);
          }
        }
      }
    } catch (e) {
      for (const f of batch) {
        try {
          const content = fs.readFileSync(path.join(PROJECT_ROOT, f), 'utf8');
          counts[f] = content.split('\n').length;
        } catch (e2) {
          counts[f] = 0;
        }
      }
    }
  }
  return counts;
}

const lineCounts = countLines(filteredFiles);

// ── Step 6: Framework Detection ──────────────────────────────────────────────
const frameworks = new Set();
const KNOWN_JS_FRAMEWORKS = {
  'react': 'React', 'vue': 'Vue', 'svelte': 'Svelte', '@angular/core': 'Angular',
  'express': 'Express', 'fastify': 'Fastify', 'koa': 'Koa',
  'next': 'Next.js', 'nuxt': 'Nuxt', 'vite': 'Vite',
  'vitest': 'Vitest', 'jest': 'Jest', 'mocha': 'Mocha',
  'tailwindcss': 'Tailwind CSS', 'prisma': 'Prisma',
  'typeorm': 'TypeORM', 'sequelize': 'Sequelize', 'mongoose': 'Mongoose',
  'redux': 'Redux', 'zustand': 'Zustand', 'mobx': 'MobX',
};

const KNOWN_PYTHON_FRAMEWORKS = [
  'django', 'djangorestframework', 'fastapi', 'flask', 'sqlalchemy',
  'alembic', 'celery', 'pydantic', 'uvicorn', 'gunicorn', 'aiohttp',
  'tornado', 'starlette', 'pytest', 'hypothesis', 'channels'
];

const PYTHON_FRAMEWORK_DISPLAY = {
  'django': 'Django', 'djangorestframework': 'Django REST Framework',
  'fastapi': 'FastAPI', 'flask': 'Flask', 'sqlalchemy': 'SQLAlchemy',
  'alembic': 'Alembic', 'celery': 'Celery', 'pydantic': 'Pydantic',
  'uvicorn': 'Uvicorn', 'gunicorn': 'Gunicorn', 'aiohttp': 'aiohttp',
  'tornado': 'Tornado', 'starlette': 'Starlette', 'pytest': 'pytest',
  'hypothesis': 'Hypothesis', 'channels': 'Django Channels'
};

function readFileSafe(relPath) {
  try {
    return fs.readFileSync(path.join(PROJECT_ROOT, relPath), 'utf8');
  } catch (e) {
    return null;
  }
}

const packageJsonFiles = filteredFiles.filter(f => path.basename(f) === 'package.json');
for (const pkgFile of packageJsonFiles) {
  const content = readFileSafe(pkgFile);
  if (!content) continue;
  try {
    const pkg = JSON.parse(content);
    const allDeps = { ...pkg.dependencies, ...pkg.devDependencies };
    for (const [dep, display] of Object.entries(KNOWN_JS_FRAMEWORKS)) {
      if (allDeps[dep]) frameworks.add(display);
    }
  } catch (e) {}
}

const reqFiles = filteredFiles.filter(f => path.basename(f) === 'requirements.txt');
for (const reqFile of reqFiles) {
  const content = readFileSafe(reqFile);
  if (!content) continue;
  const lines = content.split('\n').map(l => l.trim().split(/[>=<![\s]/)[0].toLowerCase().trim());
  for (const pkg of lines) {
    if (KNOWN_PYTHON_FRAMEWORKS.includes(pkg) && PYTHON_FRAMEWORK_DISPLAY[pkg]) {
      frameworks.add(PYTHON_FRAMEWORK_DISPLAY[pkg]);
    }
  }
}

const pyprojectFiles = filteredFiles.filter(f => path.basename(f) === 'pyproject.toml');
for (const pyFile of pyprojectFiles) {
  const content = readFileSafe(pyFile);
  if (!content) continue;
  for (const fw of KNOWN_PYTHON_FRAMEWORKS) {
    if (content.toLowerCase().includes(fw) && PYTHON_FRAMEWORK_DISPLAY[fw]) {
      frameworks.add(PYTHON_FRAMEWORK_DISPLAY[fw]);
    }
  }
}

if (filteredFiles.some(f => path.basename(f) === 'Dockerfile')) frameworks.add('Docker');
if (filteredFiles.some(f => path.basename(f) === 'docker-compose.yml' || path.basename(f) === 'docker-compose.yaml')) frameworks.add('Docker Compose');
if (filteredFiles.some(f => f.endsWith('.tf'))) frameworks.add('Terraform');
if (filteredFiles.some(f => f.startsWith('.github/workflows/') && f.endsWith('.yml'))) frameworks.add('GitHub Actions');
if (filteredFiles.some(f => path.basename(f) === '.gitlab-ci.yml')) frameworks.add('GitLab CI');
if (filteredFiles.some(f => path.basename(f) === 'Jenkinsfile')) frameworks.add('Jenkins');

// ── Step 7: Complexity Estimation ────────────────────────────────────────────
function estimateComplexity(count) {
  if (count <= 30) return 'small';
  if (count <= 150) return 'moderate';
  if (count <= 500) return 'large';
  return 'very-large';
}

// ── Step 8: Project Name ─────────────────────────────────────────────────────
let projectName = path.basename(PROJECT_ROOT);
let rawDescription = '';
let readmeHead = '';

const goModContent = readFileSafe('go.mod');
if (goModContent) {
  const m = goModContent.match(/^module\s+(\S+)/m);
  if (m) projectName = m[1].split('/').pop();
}

for (const pyFile of pyprojectFiles) {
  const content = readFileSafe(pyFile);
  if (!content) continue;
  const m = content.match(/^\s*name\s*=\s*["']([^"']+)["']/m);
  if (m) { projectName = m[1]; break; }
}

const cargoToml = readFileSafe('Cargo.toml');
if (cargoToml) {
  const m = cargoToml.match(/^\s*name\s*=\s*"([^"]+)"/m);
  if (m) projectName = m[1];
}

const rootPkg = readFileSafe('package.json');
if (rootPkg) {
  try {
    const pkg = JSON.parse(rootPkg);
    if (pkg.name) projectName = pkg.name;
    if (pkg.description) rawDescription = pkg.description;
  } catch (e) {}
}

// Also check coffee-map/package.json
const coffeeMapPkg = readFileSafe('coffee-map/package.json');
if (coffeeMapPkg) {
  try {
    const pkg = JSON.parse(coffeeMapPkg);
    if (pkg.name && !rootPkg) projectName = pkg.name;
    if (pkg.description && !rawDescription) rawDescription = pkg.description;
  } catch (e) {}
}

for (const f of ['README.md', 'readme.md', 'Readme.md']) {
  const content = readFileSafe(f);
  if (content) {
    readmeHead = content.split('\n').slice(0, 10).join('\n');
    break;
  }
}

// Use BtwnMeetings as project name (from README)
if (projectName === 'coffee_app' || projectName === 'coffee-map') {
  projectName = 'BtwnMeetings';
}

// ── Step 9: Import Resolution ─────────────────────────────────────────────────
const fileSet = new Set(filteredFiles);

let tsconfigPaths = {};
let tsconfigBaseUrl = '';
const tsconfigFiles = filteredFiles.filter(f => path.basename(f) === 'tsconfig.json');
for (const tc of tsconfigFiles) {
  const content = readFileSafe(tc);
  if (!content) continue;
  try {
    const stripped = content.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*/g, '');
    const tsconfig = JSON.parse(stripped);
    const co = tsconfig.compilerOptions || {};
    if (co.baseUrl) tsconfigBaseUrl = co.baseUrl;
    if (co.paths) tsconfigPaths = co.paths;
  } catch (e) {}
}

let goModuleName = '';
if (goModContent) {
  const m = goModContent.match(/^module\s+(\S+)/m);
  if (m) goModuleName = m[1];
}

const TS_PROBES = ['.ts', '.tsx', '.js', '.jsx', '/index.ts', '/index.js', '/index.tsx', '/index.jsx'];
const PY_PROBES = ['.py', '/__init__.py'];

function probeExtensions(base, probes) {
  for (const probe of probes) {
    const candidate = probe.startsWith('/') ? base + probe : base + probe;
    if (fileSet.has(candidate)) return candidate;
  }
  return null;
}

function resolveRelativeImport(importPath, importerDir, probes) {
  const resolved = path.normalize(path.join(importerDir, importPath));
  if (fileSet.has(resolved)) return resolved;
  return probeExtensions(resolved, probes);
}

function extractImports(filePath, language) {
  const content = readFileSafe(filePath);
  if (!content) return [];
  const importerDir = path.dirname(filePath) === '.' ? '' : path.dirname(filePath);
  const resolved = [];

  if (language === 'typescript' || language === 'javascript') {
    const importRegex = /(?:import|export)\s+(?:[\s\S]*?\s+from\s+)?['"]([^'"]+)['"]/g;
    const requireRegex = /require\(['"]([^'"]+)['"]\)/g;
    const allMatches = [];
    let m;
    while ((m = importRegex.exec(content)) !== null) allMatches.push(m[1]);
    while ((m = requireRegex.exec(content)) !== null) allMatches.push(m[1]);

    for (const importPath of allMatches) {
      if (importPath.startsWith('.')) {
        const base = importerDir ? importerDir + '/' + importPath : importPath;
        const normalized = path.normalize(base);
        if (fileSet.has(normalized)) { resolved.push(normalized); continue; }
        const r = probeExtensions(normalized, TS_PROBES);
        if (r) resolved.push(r);
      } else {
        // Path aliases
        let aliasResolved = false;
        for (const [alias, targets] of Object.entries(tsconfigPaths)) {
          const aliasPrefix = alias.replace(/\/\*$/, '');
          if (importPath === aliasPrefix || importPath.startsWith(aliasPrefix + '/')) {
            const rest = importPath.slice(aliasPrefix.length).replace(/^\//, '');
            for (const target of targets) {
              const targetBase = target.replace(/\/\*$/, '');
              const candidate = tsconfigBaseUrl
                ? path.normalize(path.join(tsconfigBaseUrl, targetBase, rest))
                : path.normalize(path.join(targetBase, rest));
              if (fileSet.has(candidate)) { resolved.push(candidate); aliasResolved = true; break; }
              const r = probeExtensions(candidate, TS_PROBES);
              if (r) { resolved.push(r); aliasResolved = true; break; }
            }
            if (aliasResolved) break;
          }
        }
        if (!aliasResolved) {
          for (const [prefix, base] of [['@/', ''], ['~/', '']]) {
            if (importPath.startsWith(prefix)) {
              const rest = importPath.slice(prefix.length);
              const candidate = tsconfigBaseUrl ? path.normalize(path.join(tsconfigBaseUrl, rest)) : rest;
              const r = probeExtensions(candidate, TS_PROBES);
              if (r) { resolved.push(r); break; }
            }
          }
        }
      }
    }
  } else if (language === 'python') {
    const relImportRegex = /from\s+(\.+)([\w.]*)?(?:\s+import\s+(.+))?/g;
    let m;
    while ((m = relImportRegex.exec(content)) !== null) {
      const dots = m[1].length;
      const modPath = (m[2] || '').trim();
      let baseDir = importerDir || '.';
      for (let i = 1; i < dots; i++) baseDir = path.dirname(baseDir);
      if (baseDir === '.') baseDir = '';
      const candidate = modPath
        ? (baseDir ? baseDir + '/' + modPath.replace(/\./g, '/') : modPath.replace(/\./g, '/'))
        : baseDir;
      if (!candidate) continue;
      const r = probeExtensions(candidate, PY_PROBES);
      if (r) resolved.push(r);
    }

    const absImportRegex = /^(?:import\s+([\w.]+)|from\s+([\w.]+)\s+import\s+(.+))$/gm;
    while ((m = absImportRegex.exec(content)) !== null) {
      const modulePath = (m[1] || m[2] || '').trim();
      if (!modulePath || modulePath.startsWith('.')) continue;
      const parts = modulePath.split('.');
      const asFile = parts.join('/');
      const matched = probeExtensions(asFile, PY_PROBES);
      if (matched) {
        resolved.push(matched);
        if (matched.endsWith('/__init__.py') && m[3]) {
          const names = m[3].split(',').map(n => n.trim().split(/\s+/)[0]);
          for (const name of names) {
            const subCandidate = asFile + '/' + name;
            const subMatch = probeExtensions(subCandidate, PY_PROBES);
            if (subMatch) resolved.push(subMatch);
          }
        }
      }
    }
  } else if (language === 'go' && goModuleName) {
    const importRegex = /import\s+(?:\(([^)]+)\)|"([^"]+)")/g;
    let m;
    while ((m = importRegex.exec(content)) !== null) {
      const block = m[1] || m[2] || '';
      const paths = block.match(/"([^"]+)"/g) || (m[2] ? ['"' + m[2] + '"'] : []);
      for (const p of paths) {
        const imp = p.replace(/"/g, '');
        if (imp.startsWith(goModuleName + '/')) {
          const rel = imp.slice(goModuleName.length + 1);
          for (const f of filteredFiles) {
            if (f.startsWith(rel + '/') && f.endsWith('.go')) {
              resolved.push(f);
              break;
            }
          }
        }
      }
    }
  } else if (language === 'rust') {
    const modRegex = /^mod\s+(\w+)/gm;
    let m;
    while ((m = modRegex.exec(content)) !== null) {
      const modName = m[1];
      const sibling = importerDir ? importerDir + '/' + modName + '.rs' : modName + '.rs';
      const siblingMod = importerDir ? importerDir + '/' + modName + '/mod.rs' : modName + '/mod.rs';
      if (fileSet.has(sibling)) resolved.push(sibling);
      else if (fileSet.has(siblingMod)) resolved.push(siblingMod);
    }
  } else if (language === 'ruby') {
    const relReqRegex = /require_relative\s+['"]([^'"]+)['"]/g;
    const reqRegex = /require\s+['"]([^'"]+)['"]/g;
    let m;
    while ((m = relReqRegex.exec(content)) !== null) {
      const imp = m[1];
      const base = importerDir ? importerDir + '/' + imp : imp;
      const normalized = path.normalize(base);
      if (fileSet.has(normalized)) { resolved.push(normalized); continue; }
      const r = probeExtensions(normalized, ['.rb', '']);
      if (r) resolved.push(r);
    }
    while ((m = reqRegex.exec(content)) !== null) {
      const imp = m[1];
      for (const root of ['lib', 'app', '']) {
        const candidate = root ? root + '/' + imp : imp;
        if (fileSet.has(candidate)) { resolved.push(candidate); break; }
        const r = probeExtensions(candidate, ['.rb', '']);
        if (r) { resolved.push(r); break; }
      }
    }
  }

  return [...new Set(resolved)];
}

const importMap = {};
for (const f of filteredFiles) {
  const lang = detectLanguage(f);
  const cat = detectCategory(f);
  if (cat === 'code') {
    importMap[f] = extractImports(f, lang);
  } else {
    importMap[f] = [];
  }
}

// ── Assemble Output ───────────────────────────────────────────────────────────
const fileObjs = filteredFiles
  .sort()
  .map(f => ({
    path: f,
    language: detectLanguage(f),
    sizeLines: lineCounts[f] || 0,
    fileCategory: detectCategory(f),
  }));

const allLanguages = [...new Set(fileObjs.map(f => f.language))].sort();
const complexity = estimateComplexity(fileObjs.length);

const output = {
  scriptCompleted: true,
  name: projectName,
  rawDescription,
  readmeHead,
  languages: allLanguages,
  frameworks: [...frameworks].sort(),
  files: fileObjs,
  totalFiles: fileObjs.length,
  filteredByIgnore,
  estimatedComplexity: complexity,
  importMap,
};

fs.mkdirSync(path.dirname(OUTPUT_FILE), { recursive: true });
fs.writeFileSync(OUTPUT_FILE, JSON.stringify(output, null, 2));
process.exit(0);
