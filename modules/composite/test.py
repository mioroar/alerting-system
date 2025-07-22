from .grammar import get_parser
from .ast_transform import AlertTransformer

text = "price >= 10 60"
tree = get_parser().parse(text)
ast  = AlertTransformer().transform(tree)
print(ast)

text = "(price > 5 300 & volume > 1000000 60) | volume_change < 50 600"
tree = get_parser().parse(text)
ast  = AlertTransformer().transform(tree)
print(ast)

text = "(price > 5 300 | volume > 1000000 60) & oi > 5"
tree = get_parser().parse(text)
ast  = AlertTransformer().transform(tree)
print(ast)

text = "((spread < 3 120 & funding < 0.01) | oi > 10) @1800"
tree = get_parser().parse(text)
ast  = AlertTransformer().transform(tree)
print(ast)

text = "oi > 5 @3600"
tree = get_parser().parse(text)
ast  = AlertTransformer().transform(tree)
print(ast)

text = "funding < 0.01 60"
tree = get_parser().parse(text)
ast  = AlertTransformer().transform(tree)
print(ast)