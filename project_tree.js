const fs = require('fs');
const path = require('path');

const ROOT = process.cwd();

const EXCLUDED_DIRS = new Set([
  'node_modules',
  '.git',
  '.venv',
  '__pycache__',
  'runtime',
  'dist',
  'build',
  'coverage',
  '.cache',
  '.turbo'
]);

const EXCLUDED_FILES = new Set([
  'project_tree.txt',
  'project_tree.js'
]);

function shouldExclude(name, isDirectory) {
  if (isDirectory) {
    return EXCLUDED_DIRS.has(name);
  }

  return EXCLUDED_FILES.has(name);
}

function getEntries(dir) {
  return fs.readdirSync(dir, { withFileTypes: true })
    .filter(entry => !shouldExclude(entry.name, entry.isDirectory()))
    .sort((a, b) => {
      if (a.isDirectory() && !b.isDirectory()) return -1;
      if (!a.isDirectory() && b.isDirectory()) return 1;

      return a.name.localeCompare(b.name, 'ru');
    });
}

function buildTree(dir, prefix = '') {
  const entries = getEntries(dir);
  const lines = [];

  entries.forEach((entry, index) => {
    const isLast = index === entries.length - 1;

    const connector = isLast ? '└── ' : '├── ';
    const nextPrefix = prefix + (isLast ? '    ' : '│   ');

    lines.push(`${prefix}${connector}${entry.name}`);

    if (entry.isDirectory()) {
      lines.push(
        ...buildTree(
          path.join(dir, entry.name),
          nextPrefix
        )
      );
    }
  });

  return lines;
}

const tree = [
  path.basename(ROOT),
  ...buildTree(ROOT)
].join('\n');

console.log('\n' + tree + '\n');

fs.writeFileSync(
  path.join(ROOT, 'project_tree.txt'),
  tree,
  'utf8'
);

console.log('----------------------------------------------');
console.log('Saved: project_tree.txt');
console.log('----------------------------------------------');