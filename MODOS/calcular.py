import ast
import math
import operator

def calcular(expressao):
    """Calculadora matemática segura usando AST."""
    try:
        expressao = str(expressao).strip()
        if not expressao:
            return "❌ Desculpa, mas você precisa fornecer uma expressão matemática para eu calcular! 🥺"

        # Operadores permitidos
        ops_permitidos = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.FloorDiv: operator.floordiv,
            ast.Mod: operator.mod,
            ast.Pow: operator.pow,
            ast.USub: operator.neg,
            ast.UAdd: operator.pos,
        }

        # Constantes e funções math permitidas
        constantes = {
            'pi': math.pi,
            'e': math.e,
            'tau': math.tau,
            'inf': math.inf,
        }

        funcoes_math = {
            'sqrt': math.sqrt,
            'abs': abs,
            'round': round,
            'ceil': math.ceil,
            'floor': math.floor,
            'log': math.log,
            'log2': math.log2,
            'log10': math.log10,
            'sin': math.sin,
            'cos': math.cos,
            'tan': math.tan,
            'factorial': math.factorial,
            'gcd': math.gcd,
        }

        def avaliar_no(node):
            if isinstance(node, ast.Expression):
                return avaliar_no(node.body)
            elif isinstance(node, ast.Constant):
                if isinstance(node.value, (int, float, complex)):
                    return node.value
                raise ValueError(f"Tipo não permitido: {type(node.value)}")
            elif isinstance(node, ast.Name):
                nome = node.id.lower()
                if nome in constantes:
                    return constantes[nome]
                raise ValueError(f"Variável não permitida: {node.id}")
            elif isinstance(node, ast.BinOp):
                tipo_op = type(node.op)
                if tipo_op not in ops_permitidos:
                    raise ValueError(f"Operador não permitido: {tipo_op.__name__}")
                esq = avaliar_no(node.left)
                dir_ = avaliar_no(node.right)
                # Proteção contra potências gigantes
                if tipo_op == ast.Pow:
                    if isinstance(dir_, (int, float)) and abs(dir_) > 1000:
                        raise ValueError("Expoente muito grande (máximo: 1000)")
                return ops_permitidos[tipo_op](esq, dir_)
            elif isinstance(node, ast.UnaryOp):
                tipo_op = type(node.op)
                if tipo_op not in ops_permitidos:
                    raise ValueError(f"Operador não permitido: {tipo_op.__name__}")
                return ops_permitidos[tipo_op](avaliar_no(node.operand))
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    nome_func = node.func.id.lower()
                    if nome_func in funcoes_math:
                        args = [avaliar_no(arg) for arg in node.args]
                        return funcoes_math[nome_func](*args)
                    raise ValueError(f"Função não permitida: {node.func.id}")
                raise ValueError("Chamada de função inválida.")
            else:
                raise ValueError(f"Expressão não suportada: {type(node).__name__}")

        # Pré-processar: substituir '^' por '**', 'x' por '*'
        expr_proc = expressao.replace('^', '**').replace('×', '*').replace('÷', '/')

        tree = ast.parse(expr_proc, mode='eval')
        resultado = avaliar_no(tree)

        # Formatar resultado
        if isinstance(resultado, float):
            if resultado == int(resultado) and not math.isinf(resultado):
                resultado_str = str(int(resultado))
            else:
                resultado_str = f"{resultado:.10g}"
        else:
            resultado_str = str(resultado)

        return (
            f"🔢 **Calculadora da Ayla** 🌸\n"
            f"📝 Expressão: `{expressao}`\n"
            f"✅ Resultado: **{resultado_str}**"
        )

    except ZeroDivisionError:
        return "❌ Oxi! Erro: não dá para dividir por zero! 🙀"
    except ValueError as ve:
        return f"❌ Aconteceu um errinho na expressão: {ve} 🥺"
    except SyntaxError:
        return f"❌ Essa expressão parece inválida: `{expressao}`. Dá uma olhadinha na sintaxe, tá bom? 🥺"
    except Exception as e:
        return f"❌ Desculpa, aconteceu um erro ao calcular: {e} 💔"

TOOL_MAP["calcular"] = calcular
TOOL_MAP["calcular"] = calcular

if "calcular" not in [fd["name"] for fd in FUNCTION_DECLARATIONS]:
    FUNCTION_DECLARATIONS.append({
        "name": "calcular",
        "description": "Calculadora matemática fofa e segura! 🌸 Suporta +, -, *, /, **, //, %, e funções como sqrt(), log(), sin(), cos(), factorial(). Constantes: pi, e, tau.",
        "parameters": {
            "type": "object",
            "properties": {
                "expressao": {
                    "type": "string",
                    "description": "Expressão matemática fofa para eu calcular (ex: '2 + 3 * 4', 'sqrt(144)', '2^10', 'pi * 5**2')"
                }
            },
            "required": ["expressao"]
        }
    })
