__author__ = '@justmeth'
__channel__ = 'https://t.me/g_plugins'
__contact__ = 'https://t.me/justmeth'
import ast
from pathlib import Path

class Clean(ast.NodeTransformer):

    def clean(self, node):
        self.generic_visit(node)
        if node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant) and isinstance(node.body[0].value.value, str):
            node.body.pop(0)
        if not node.body:
            node.body.append(ast.Pass())
        return node
    visit_Module = clean
    visit_ClassDef = clean
    visit_FunctionDef = clean
    visit_AsyncFunctionDef = clean

def main(root):
    for folder in ['auto_telegram_emoji', 'FunPayAPI', 'tests', 'scripts']:
        for path in (root / folder).rglob('*.py'):
            tree = Clean().visit(ast.parse(path.read_text(encoding='utf8')))
            ast.fix_missing_locations(tree)
            path.write_text(ast.unparse(tree) + '\n', encoding='utf8')
    for path in [root / 'scripts/setup.py']:
        tree = Clean().visit(ast.parse(path.read_text(encoding='utf8')))
        ast.fix_missing_locations(tree)
        path.write_text(ast.unparse(tree) + '\n', encoding='utf8')
if __name__ == '__main__':
    main(Path(__file__).resolve().parents[1])
