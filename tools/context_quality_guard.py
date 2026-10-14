"""Fail CI when retired context-loss mechanisms return to current source files."""
import ast
from pathlib import Path
import re
import subprocess
import sys

def inspect(root):
    process = subprocess.run(['git', '-C', str(root), 'ls-files', '-z'], capture_output=True, check=True)
    issues = []
    for name in process.stdout.decode('utf-8').split('\0'):
        if not name:
            continue
        path = root / name
        if not path.is_file() or path.suffix not in ('.py', '.md', '.json', '.yaml', '.mjs', '.js', '.sh', '.ps1'):
            continue
        if path.resolve() == Path(__file__).resolve() or '/tests/' in '/' + name or path.name.startswith('test_'):
            continue
        if path.name in ('CHANGELOG.md',) or '/memory/' in '/' + name or name.startswith('memory/'):
            continue  # preserve historical evidence and rejection records
        text = path.read_text(encoding='utf-8-sig', errors='strict')
        if path.suffix == '.py':
            tree = ast.parse(text, filename=name)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and 'caveman' in node.name.lower():
                    issues.append(f'{name}:{node.lineno}: retired executable mode')
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id.startswith('CAVEMAN_'):
                            issues.append(f'{name}:{node.lineno}: retired mode flag/ruleset')
        patterns = [r'Always prefix commands with\s+`rtk`', r'headroom proxy --',
                    r'pip install headroom-ai', r'Caveman-ultra\.',
                    r'Respond terse like a smart caveman', r'\*\*Caveman \(stručnost\)',
                    r'\*\*LEAN:\*\*.*deleguj', r'lean apply.*(?:opus|settings\.json)',
                    r'context.*<150k']
        for number, line in enumerate(text.splitlines(), 1):
            if any(re.search(pattern, line, re.I) for pattern in patterns):
                issues.append(f'{name}:{number}: retired context/output policy')
    return issues

if __name__ == '__main__':
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    issues = inspect(root)
    print('\n'.join(issues) if issues else 'PASS: retired active context-loss mechanisms absent in tracked sources')
    raise SystemExit(bool(issues))
