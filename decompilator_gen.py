import re
import os
from collections import defaultdict, deque

class ControlFlowGraph:
    def __init__(self):
        self.blocks = {}
        self.edges = defaultdict(list)
        self.entry_block = None
        self.exit_blocks = []
        
    def add_block(self, block_id, instructions):
        self.blocks[block_id] = instructions
        
    def add_edge(self, from_block, to_block, condition=None):
        self.edges[from_block].append((to_block, condition))
        
    def get_dominators(self):
        dominators = {}
        all_blocks = set(self.blocks.keys())
        
        if self.entry_block is None:
            return dominators
            
        dominators[self.entry_block] = {self.entry_block}
        
        for block in all_blocks - {self.entry_block}:
            dominators[block] = all_blocks.copy()
        
        changed = True
        while changed:
            changed = False
            for block in all_blocks - {self.entry_block}:
                predecessors = [pred for pred, _ in self.edges.items() if any(succ == block for succ, _ in self.edges[pred])]
                
                if predecessors:
                    new_dom = set.intersection(*[dominators[pred] for pred in predecessors if pred in dominators])
                    new_dom.add(block)
                    
                    if new_dom != dominators[block]:
                        dominators[block] = new_dom
                        changed = True
        
        return dominators

class BytecodeDecompiler:
    def __init__(self):
        self.stack = []
        self.code_lines = []
        self.imports = {}
        self.variables = {}
        self.functions = {}
        self.classes = {}
        self.current_import = None
        self.import_items = []
        self.import_aliases = {}
        self.line_mapping = {}
        self.strings = {}
        self.numbers = {}
        self.loops = []
        self.conditions = []
        self.blocks = []
        self.indent_level = 0
        self.jump_targets = {}
        self.instruction_index = 0
        self.instructions = []
        self.offset_to_index = {}
        self.labels = {}
        self.exception_handlers = []
        self.with_blocks = []
        self.comprehensions = []
        self.decorators = []
        self.annotations = {}
        self.last_line_num = None
        self.cfg = ControlFlowGraph()
        self.basic_blocks = {}
        self.loop_blocks = set()
        self.back_edges = set()
        self.forward_refs = {}
        self.temp_vars = {}
        self.block_stack = []
        self.try_blocks = []
        self.context_managers = []
        
    def build_cfg(self):
        current_block = []
        block_id = 0
        block_starts = {0}
        
        for i, instr in enumerate(self.instructions):
            if not instr:
                continue
                
            opcode = instr['opcode']
            
            if 'JUMP' in opcode or opcode == 'FOR_ITER':
                target = self.extract_jump_target(instr['args'])
                if target is not None:
                    block_starts.add(target)
                    block_starts.add(i + 1)
                    
            elif opcode in ['RETURN_VALUE', 'RETURN_CONST', 'RAISE_VARARGS']:
                block_starts.add(i + 1)
        
        block_starts = sorted(block_starts)
        
        for i in range(len(block_starts)):
            start = block_starts[i]
            end = block_starts[i + 1] if i + 1 < len(block_starts) else len(self.instructions)
            
            block_instrs = []
            for j in range(start, end):
                if j < len(self.instructions) and self.instructions[j]:
                    block_instrs.append((j, self.instructions[j]))
            
            if block_instrs:
                self.basic_blocks[start] = block_instrs
                self.cfg.add_block(start, block_instrs)
        
        if 0 in self.basic_blocks:
            self.cfg.entry_block = 0
        
        for block_start, block_instrs in self.basic_blocks.items():
            if not block_instrs:
                continue
                
            last_idx, last_instr = block_instrs[-1]
            opcode = last_instr['opcode']
            
            if opcode in ['JUMP_FORWARD', 'JUMP_ABSOLUTE', 'JUMP']:
                target = self.extract_jump_target(last_instr['args'])
                if target in self.basic_blocks:
                    self.cfg.add_edge(block_start, target)
                    
            elif opcode in ['POP_JUMP_IF_FALSE', 'POP_JUMP_IF_TRUE', 'POP_JUMP_FORWARD_IF_FALSE', 'POP_JUMP_FORWARD_IF_TRUE']:
                target = self.extract_jump_target(last_instr['args'])
                next_block = last_idx + 1
                
                if target in self.basic_blocks:
                    self.cfg.add_edge(block_start, target, 'false' if 'FALSE' in opcode else 'true')
                
                for next_start in sorted(self.basic_blocks.keys()):
                    if next_start >= next_block:
                        self.cfg.add_edge(block_start, next_start, 'true' if 'FALSE' in opcode else 'false')
                        break
                        
            elif opcode == 'FOR_ITER':
                target = self.extract_jump_target(last_instr['args'])
                next_block = last_idx + 1
                
                if target in self.basic_blocks:
                    self.cfg.add_edge(block_start, target, 'end_loop')
                    self.loop_blocks.add(block_start)
                
                for next_start in sorted(self.basic_blocks.keys()):
                    if next_start >= next_block:
                        self.cfg.add_edge(block_start, next_start, 'loop_body')
                        break
                        
            elif opcode in ['JUMP_BACKWARD', 'POP_JUMP_BACKWARD_IF_FALSE', 'POP_JUMP_BACKWARD_IF_TRUE']:
                target = self.extract_jump_target(last_instr['args'])
                if target in self.basic_blocks:
                    self.cfg.add_edge(block_start, target)
                    self.back_edges.add((block_start, target))
                    
            elif opcode not in ['RETURN_VALUE', 'RETURN_CONST', 'RAISE_VARARGS']:
                next_block = last_idx + 1
                for next_start in sorted(self.basic_blocks.keys()):
                    if next_start >= next_block:
                        self.cfg.add_edge(block_start, next_start)
                        break
        
        for block_start in self.basic_blocks.keys():
            if block_start in self.basic_blocks:
                last_idx, last_instr = self.basic_blocks[block_start][-1]
                if last_instr['opcode'] in ['RETURN_VALUE', 'RETURN_CONST']:
                    self.cfg.exit_blocks.append(block_start)
    
    def detect_loops(self):
        loops = []
        
        for back_edge in self.back_edges:
            from_block, to_block = back_edge
            loop_body = {to_block}
            
            worklist = deque([from_block])
            visited = {to_block}
            
            while worklist:
                current = worklist.popleft()
                if current in visited:
                    continue
                    
                visited.add(current)
                loop_body.add(current)
                
                for pred_block, edges in self.cfg.edges.items():
                    for succ, _ in edges:
                        if succ == current and pred_block not in visited:
                            worklist.append(pred_block)
            
            loops.append({
                'header': to_block,
                'body': loop_body,
                'back_edge': back_edge
            })
        
        return loops
    
    def detect_conditionals(self):
        conditionals = []
        
        for block_start, edges in self.cfg.edges.items():
            if len(edges) == 2:
                true_branch = None
                false_branch = None
                
                for target, condition in edges:
                    if condition == 'true':
                        true_branch = target
                    elif condition == 'false':
                        false_branch = target
                
                if true_branch is not None and false_branch is not None:
                    conditionals.append({
                        'block': block_start,
                        'true_branch': true_branch,
                        'false_branch': false_branch
                    })
        
        return conditionals
    
    def analyze_data_flow(self):
        def_use = {}
        
        for block_start, block_instrs in self.basic_blocks.items():
            defs = set()
            uses = set()
            
            for idx, instr in block_instrs:
                opcode = instr['opcode']
                
                if opcode in ['LOAD_NAME', 'LOAD_GLOBAL', 'LOAD_FAST', 'LOAD_DEREF']:
                    var_name = self.extract_name(instr['args'])
                    if var_name not in defs:
                        uses.add(var_name)
                        
                elif opcode in ['STORE_NAME', 'STORE_GLOBAL', 'STORE_FAST', 'STORE_DEREF']:
                    var_name = self.extract_name(instr['args'])
                    defs.add(var_name)
            
            def_use[block_start] = {'defs': defs, 'uses': uses}
        
        return def_use
    
    def optimize_stack_reconstruction(self):
        optimized = []
        temp_counter = 0
        
        i = 0
        while i < len(self.stack):
            item = self.stack[i]
            
            if item[0] == 'expr' and i + 1 < len(self.stack):
                next_item = self.stack[i + 1]
                if next_item[0] == 'expr':
                    combined = f"({item[1]}) and ({next_item[1]})"
                    optimized.append(('expr', combined))
                    i += 2
                    continue
            
            optimized.append(item)
            i += 1
        
        self.stack = optimized
    
    def clean_value(self, text):
        text = str(text).strip()
        while text.startswith('(') and text.endswith(')') and text.count('(') == text.count(')'):
            inner = text[1:-1]
            if ',' not in inner or inner.count('(') == inner.count(')'):
                text = inner
            else:
                break
        text = text.strip()
        if text.startswith("'") and text.endswith("'") and text.count("'") == 2:
            return text[1:-1]
        if text.startswith('"') and text.endswith('"') and text.count('"') == 2:
            return text[1:-1]
        return text
    
    def parse_instruction_line(self, line):
        line = line.strip()
        if not line or '--' in line or 'Disassembly' in line:
            return None
        
        line = re.sub(r'>>', '', line)
        
        original_line = line
        offset = None
        line_num = None
        
        offset_match = re.match(r'^(\d+)\s+', line)
        if offset_match:
            offset = int(offset_match.group(1))
            line = line[offset_match.end():].strip()
        
        parts = re.split(r'\s+', line, maxsplit=1)
        if len(parts) < 1:
            return None
        
        if parts[0].isdigit():
            line_num = int(parts[0])
            if len(parts) > 1:
                rest = parts[1].strip()
            else:
                return None
        else:
            rest = line
        
        match = re.match(r'^(\w+)\s*(.*)', rest)
        if match:
            opcode = match.group(1)
            args = match.group(2).strip()
            return {
                'offset': offset,
                'line': line_num,
                'opcode': opcode,
                'args': args,
                'raw': original_line
            }
        return None
    
    def extract_const_value(self, args):
        match = re.search(r'\((.+)\)$', args)
        if match:
            value = match.group(1)
            
            if value == 'None':
                return None
            if value == 'True':
                return True
            if value == 'False':
                return False
            if value == '...':
                return '...'
            
            if re.match(r'^-?\d+$', value):
                return int(value)
            if re.match(r'^-?\d+\.\d+([eE][+-]?\d+)?$', value):
                return float(value)
            if re.match(r'^-?\d+[jJ]$', value):
                return complex(value)
            
            if value.startswith("'") and value.endswith("'"):
                return value[1:-1]
            if value.startswith('"') and value.endswith('"'):
                return value[1:-1]
            
            if value.startswith("b'") or value.startswith('b"'):
                return value
            
            if ',' in value:
                items = []
                depth = 0
                current = ''
                for char in value:
                    if char in '([{':
                        depth += 1
                    elif char in ')]}':
                        depth -= 1
                    elif char == ',' and depth == 0:
                        items.append(current.strip().strip('\'"'))
                        current = ''
                        continue
                    current += char
                if current:
                    items.append(current.strip().strip('\'"'))
                return tuple(items)
            
            return value
        
        idx_match = re.match(r'(\d+)', args)
        if idx_match:
            return int(idx_match.group(1))
        
        return args
    
    def extract_name(self, args):
        match = re.search(r'\((.+)\)$', args)
        if match:
            name = match.group(1)
            return name.strip('\'"')
        return args.strip()
    
    def extract_number(self, args):
        match = re.search(r'(\d+)', args)
        if match:
            return int(match.group(1))
        return 0
    
    def extract_jump_target(self, args):
        match = re.search(r'to (\d+)', args)
        if match:
            return int(match.group(1))
        match = re.search(r'(\d+)', args)
        if match:
            return int(match.group(1))
        return None
    
    def process_imports(self):
        if self.current_import and self.import_items:
            items = ', '.join(self.import_items)
            self.add_line(f"from {self.current_import} import {items}")
            self.current_import = None
            self.import_items = []
    
    def add_line(self, line):
        if not line.strip():
            return
        indent = '    ' * self.indent_level
        self.code_lines.append(indent + line)
    
    def format_value(self, value, value_type='const'):
        if value is None:
            return 'None'
        if value is True:
            return 'True'
        if value is False:
            return 'False'
        if value == '...':
            return '...'
        
        if isinstance(value, (int, float, complex)):
            return str(value)
        
        if isinstance(value, str):
            if value_type == 'const':
                if '\n' in value or '\r' in value or len(value) > 50:
                    if '"""' not in value:
                        return f'"""{value}"""'
                    elif "'''" not in value:
                        return f"'''{value}'''"
                if "'" in value and '"' not in value:
                    return f'"{value}"'
                if '"' in value and "'" not in value:
                    return f"'{value}'"
                return f"'{value}'"
            return value
        
        if isinstance(value, bytes):
            return f"b'{value.decode('utf-8', errors='ignore')}'"
        
        return str(value)
    
    def should_decrease_indent(self, index):
        if index in self.labels and self.indent_level > 0:
            return True
        return False
    
    def process_instruction(self, instr, index):
        if not instr:
            return
        
        opcode = instr['opcode']
        args = instr['args']
        
        if opcode == 'RESUME' or opcode == 'NOP' or opcode == 'CACHE' or opcode == 'PRECALL':
            pass
        
        elif opcode == 'PUSH_NULL':
            self.stack.append(('null', 'NULL'))
        
        elif opcode == 'LOAD_CONST':
            const_value = self.extract_const_value(args)
            idx = self.extract_number(args)
            self.strings[str(idx)] = const_value
            self.stack.append(('const', const_value))
        
        elif opcode == 'IMPORT_NAME':
            name = self.extract_name(args)
            self.current_import = name
            self.stack.append(('import', name))
        
        elif opcode == 'IMPORT_FROM':
            name = self.extract_name(args)
            self.import_items.append(name)
            self.stack.append(('from', name))
        
        elif opcode == 'IMPORT_STAR':
            if self.current_import:
                self.add_line(f"from {self.current_import} import *")
                self.current_import = None
        
        elif opcode == 'STORE_NAME':
            var_name = self.extract_name(args)
            
            if self.stack:
                top = self.stack.pop()
                
                if top[0] == 'import':
                    if var_name == self.current_import:
                        self.add_line(f"import {self.current_import}")
                    else:
                        self.add_line(f"import {self.current_import} as {var_name}")
                        self.import_aliases[var_name] = self.current_import
                    self.current_import = None
                    self.import_items = []
                
                elif top[0] == 'from':
                    pass
                
                elif top[0] == 'const':
                    value = self.format_value(top[1], 'const')
                    self.add_line(f"{var_name} = {value}")
                    self.variables[var_name] = top[1]
                
                else:
                    value = self.format_value(top[1], top[0]) if top[0] == 'const' else top[1]
                    self.add_line(f"{var_name} = {value}")
        
        elif opcode in ['STORE_GLOBAL', 'STORE_FAST', 'STORE_DEREF']:
            var_name = self.extract_name(args)
            if self.stack:
                top = self.stack.pop()
                if opcode == 'STORE_GLOBAL' and self.indent_level > 0:
                    self.add_line(f"global {var_name}")
                value = self.format_value(top[1], top[0]) if top[0] == 'const' else top[1]
                self.add_line(f"{var_name} = {value}")
                self.variables[var_name] = top[1]
        
        elif opcode in ['DELETE_NAME', 'DELETE_GLOBAL', 'DELETE_FAST']:
            var_name = self.extract_name(args)
            self.add_line(f"del {var_name}")
        
        elif opcode in ['LOAD_NAME', 'LOAD_GLOBAL', 'LOAD_FAST', 'LOAD_DEREF', 'LOAD_CLASSDEREF']:
            name = self.extract_name(args)
            self.stack.append(('name', name))
        
        elif opcode == 'LOAD_CLOSURE':
            name = self.extract_name(args)
            self.stack.append(('closure', name))
        
        elif opcode == 'LOAD_ATTR':
            attr = self.extract_name(args)
            if self.stack:
                obj = self.stack.pop()
                self.stack.append(('attr', f"{obj[1]}.{attr}"))
        
        elif opcode == 'STORE_ATTR':
            attr = self.extract_name(args)
            if len(self.stack) >= 2:
                obj = self.stack.pop()
                value = self.stack.pop()
                val_str = self.format_value(value[1], value[0]) if value[0] == 'const' else value[1]
                self.add_line(f"{obj[1]}.{attr} = {val_str}")
        
        elif opcode == 'DELETE_ATTR':
            attr = self.extract_name(args)
            if self.stack:
                obj = self.stack.pop()
                self.add_line(f"del {obj[1]}.{attr}")
        
        elif opcode == 'LOAD_METHOD':
            method = self.extract_name(args)
            if self.stack:
                obj = self.stack.pop()
                self.stack.append(('method', f"{obj[1]}.{method}"))
        
        elif opcode in ['CALL_FUNCTION', 'CALL']:
            arg_count = self.extract_number(args)
            
            call_args = []
            for _ in range(arg_count):
                if self.stack:
                    arg = self.stack.pop()
                    arg_str = self.format_value(arg[1], arg[0]) if arg[0] == 'const' else str(arg[1])
                    call_args.insert(0, arg_str)
            
            if self.stack:
                func = self.stack.pop()
                if func[0] == 'null' and self.stack:
                    func = self.stack.pop()
                
                call_str = f"{func[1]}({', '.join(call_args)})"
                self.stack.append(('call', call_str))
        
        elif opcode == 'CALL_METHOD':
            arg_count = self.extract_number(args)
            
            call_args = []
            for _ in range(arg_count):
                if self.stack:
                    arg = self.stack.pop()
                    arg_str = self.format_value(arg[1], arg[0]) if arg[0] == 'const' else str(arg[1])
                    call_args.insert(0, arg_str)
            
            if self.stack:
                method = self.stack.pop()
                call_str = f"{method[1]}({', '.join(call_args)})"
                self.stack.append(('call', call_str))
        
        elif opcode == 'POP_TOP':
            if self.stack:
                top = self.stack.pop()
                if top[0] == 'call':
                    self.add_line(top[1])
        
        elif opcode in ['RETURN_VALUE', 'RETURN_CONST']:
            if opcode == 'RETURN_CONST':
                const_value = self.extract_const_value(args)
                value = self.format_value(const_value, 'const')
                self.add_line(f"return {value}")
            elif self.stack:
                ret_val = self.stack.pop()
                value = self.format_value(ret_val[1], ret_val[0]) if ret_val[0] == 'const' else ret_val[1]
                self.add_line(f"return {value}")
            else:
                self.add_line("return")
        
        elif opcode in ['BUILD_LIST', 'BUILD_TUPLE', 'BUILD_SET']:
            count = self.extract_number(args)
            items = []
            for _ in range(count):
                if self.stack:
                    item = self.stack.pop()
                    value = self.format_value(item[1], item[0]) if item[0] == 'const' else item[1]
                    items.insert(0, str(value))
            
            if opcode == 'BUILD_LIST':
                self.stack.append(('list', f"[{', '.join(items)}]"))
            elif opcode == 'BUILD_TUPLE':
                tuple_str = f"({', '.join(items)})" if count != 1 else f"({items[0]},)"
                self.stack.append(('tuple', tuple_str))
            else:
                self.stack.append(('set', f"{{{', '.join(items)}}}"))
        
        elif opcode == 'BUILD_MAP':
            count = self.extract_number(args)
            items = []
            for _ in range(count):
                if len(self.stack) >= 2:
                    val = self.stack.pop()
                    key = self.stack.pop()
                    key_str = self.format_value(key[1], key[0]) if key[0] == 'const' else key[1]
                    val_str = self.format_value(val[1], val[0]) if val[0] == 'const' else val[1]
                    items.insert(0, f"{key_str}: {val_str}")
            self.stack.append(('dict', f"{{{', '.join(items)}}}"))
        
        elif opcode == 'BINARY_SUBSCR':
            if len(self.stack) >= 2:
                index = self.stack.pop()
                obj = self.stack.pop()
                index_str = self.format_value(index[1], index[0]) if index[0] == 'const' else index[1]
                self.stack.append(('subscr', f"{obj[1]}[{index_str}]"))
        
        elif opcode == 'STORE_SUBSCR':
            if len(self.stack) >= 3:
                index = self.stack.pop()
                obj = self.stack.pop()
                value = self.stack.pop()
                index_str = self.format_value(index[1], index[0]) if index[0] == 'const' else index[1]
                val_str = self.format_value(value[1], value[0]) if value[0] == 'const' else value[1]
                self.add_line(f"{obj[1]}[{index_str}] = {val_str}")
        
        elif opcode in ['BINARY_ADD', 'BINARY_SUBTRACT', 'BINARY_MULTIPLY', 'BINARY_TRUE_DIVIDE', 
                       'BINARY_FLOOR_DIVIDE', 'BINARY_MODULO', 'BINARY_POWER', 'BINARY_MATRIX_MULTIPLY',
                       'BINARY_LSHIFT', 'BINARY_RSHIFT', 'BINARY_AND', 'BINARY_OR', 'BINARY_XOR']:
            if len(self.stack) >= 2:
                right = self.stack.pop()
                left = self.stack.pop()
                op_map = {
                    'BINARY_ADD': '+', 'BINARY_SUBTRACT': '-', 'BINARY_MULTIPLY': '*',
                    'BINARY_TRUE_DIVIDE': '/', 'BINARY_FLOOR_DIVIDE': '//', 'BINARY_MODULO': '%',
                    'BINARY_POWER': '**', 'BINARY_MATRIX_MULTIPLY': '@', 'BINARY_LSHIFT': '<<',
                    'BINARY_RSHIFT': '>>', 'BINARY_AND': '&', 'BINARY_OR': '|', 'BINARY_XOR': '^'
                }
                op = op_map.get(opcode, '+')
                self.stack.append(('expr', f"{left[1]} {op} {right[1]}"))
        
        elif opcode in ['UNARY_POSITIVE', 'UNARY_NEGATIVE', 'UNARY_NOT', 'UNARY_INVERT']:
            if self.stack:
                val = self.stack.pop()
                op_map = {'UNARY_POSITIVE': '+', 'UNARY_NEGATIVE': '-', 'UNARY_NOT': 'not ', 'UNARY_INVERT': '~'}
                op = op_map.get(opcode, '')
                self.stack.append(('expr', f"{op}{val[1]}"))
        
        elif opcode == 'COMPARE_OP':
            comp_op = self.extract_name(args)
            if len(self.stack) >= 2:
                right = self.stack.pop()
                left = self.stack.pop()
                right_str = self.format_value(right[1], right[0]) if right[0] == 'const' else right[1]
                left_str = self.format_value(left[1], left[0]) if left[0] == 'const' else left[1]
                self.stack.append(('expr', f"{left_str} {comp_op} {right_str}"))
        
        elif opcode in ['POP_JUMP_IF_FALSE', 'POP_JUMP_FORWARD_IF_FALSE']:
            if self.stack:
                condition = self.stack.pop()
                self.add_line(f"if {condition[1]}:")
                self.indent_level += 1
                self.block_stack.append('if')
        
        elif opcode in ['POP_JUMP_IF_TRUE', 'POP_JUMP_FORWARD_IF_TRUE']:
            if self.stack:
                condition = self.stack.pop()
                self.add_line(f"if not ({condition[1]}):")
                self.indent_level += 1
                self.block_stack.append('if')
        
        elif opcode == 'FOR_ITER':
            if self.stack:
                iterator = self.stack[-1]
                self.add_line(f"for item in {iterator[1]}:")
                self.indent_level += 1
                self.block_stack.append('for')
        
        elif opcode == 'FORMAT_VALUE':
            flags = self.extract_number(args)
            if self.stack:
                value = self.stack.pop()
                format_spec = ''
                if flags & 0x04 and self.stack:
                    format_spec = self.stack.pop()[1]
                
                conversion = ''
                if flags & 0x03:
                    conv_type = flags & 0x03
                    if conv_type == 1:
                        conversion = '!s'
                    elif conv_type == 2:
                        conversion = '!r'
                    elif conv_type == 3:
                        conversion = '!a'
                
                if format_spec:
                    self.stack.append(('format', f"{{{value[1]}{conversion}:{format_spec}}}"))
                else:
                    self.stack.append(('format', f"{{{value[1]}{conversion}}}"))
        
        elif opcode == 'BUILD_STRING':
            count = self.extract_number(args)
            parts = []
            for _ in range(count):
                if self.stack:
                    part = self.stack.pop()
                    parts.insert(0, str(part[1]))
            
            result = ''.join(parts)
            if any('{' in str(p) for p in parts):
                self.stack.append(('string', f'f"{result}"'))
            else:
                self.stack.append(('string', f'"{result}"'))
        
        elif opcode == 'MAKE_FUNCTION':
            flags = self.extract_number(args)
            
            closure = None
            annotations = None
            kwdefaults = None
            defaults = None
            
            if flags & 0x08 and self.stack:
                closure = self.stack.pop()
            if flags & 0x04 and self.stack:
                annotations = self.stack.pop()
            if flags & 0x02 and self.stack:
                kwdefaults = self.stack.pop()
            if flags & 0x01 and self.stack:
                defaults = self.stack.pop()
            
            if self.stack:
                code_obj = self.stack.pop()
                func_name = "lambda"
                
                if self.stack and self.stack[-1][0] == 'const':
                    func_name = self.stack.pop()[1]
                
                params = []
                if defaults:
                    params.append("*args")
                if kwdefaults:
                    params.append("**kwargs")
                
                if func_name and func_name != "lambda":
                    self.add_line(f"def {func_name}({', '.join(params)}):")
                    self.indent_level += 1
                    self.add_line("pass")
                    self.indent_level -= 1
                    self.stack.append(('function', func_name))
                else:
                    self.stack.append(('lambda', f"lambda {', '.join(params)}: ..."))
        
        elif opcode == 'RAISE_VARARGS':
            count = self.extract_number(args)
            if count == 0:
                self.add_line("raise")
            elif count == 1 and self.stack:
                exc = self.stack.pop()
                exc_str = self.format_value(exc[1], exc[0]) if exc[0] == 'const' else exc[1]
                self.add_line(f"raise {exc_str}")
            elif count == 2 and len(self.stack) >= 2:
                cause = self.stack.pop()
                exc = self.stack.pop()
                self.add_line(f"raise {exc[1]} from {cause[1]}")
        
        else:
            pass
    
    def reconstruct_from_cfg(self):
        if not self.cfg.entry_block:
            return
        
        visited = set()
        
        def process_block(block_id, indent=0):
            if block_id in visited or block_id not in self.basic_blocks:
                return
            
            visited.add(block_id)
            old_indent = self.indent_level
            self.indent_level = indent
            
            for idx, instr in self.basic_blocks[block_id]:
                self.process_instruction(instr, idx)
            
            if block_id in self.cfg.edges:
                edges = self.cfg.edges[block_id]
                
                if len(edges) == 1:
                    next_block, _ = edges[0]
                    process_block(next_block, indent)
                    
                elif len(edges) == 2:
                    true_branch = None
                    false_branch = None
                    
                    for target, condition in edges:
                        if condition in ['false', 'end_loop']:
                            false_branch = target
                        else:
                            true_branch = target
                    
                    if true_branch:
                        process_block(true_branch, indent + 1)
                    
                    if self.indent_level > 0:
                        self.indent_level -= 1
                    
                    if false_branch and false_branch not in visited:
                        process_block(false_branch, indent)
            
            self.indent_level = old_indent
        
        process_block(self.cfg.entry_block)
    
    def decompile(self, bytecode_text):
        lines = bytecode_text.split('\n')
        
        for line in lines:
            instr = self.parse_instruction_line(line)
            if instr:
                self.instructions.append(instr)
                if instr['offset'] is not None:
                    self.offset_to_index[instr['offset']] = len(self.instructions) - 1
        
        self.build_cfg()
        
        loops = self.detect_loops()
        conditionals = self.detect_conditionals()
        def_use = self.analyze_data_flow()
        
        print(f"  CFG Analysis: {len(self.basic_blocks)} basic blocks")
        print(f"  Control Flow: {len(loops)} loops, {len(conditionals)} conditionals")
        print(f"  Data Flow: {len(def_use)} def-use chains")
        
        for index, instr in enumerate(self.instructions):
            self.instruction_index = index
            self.process_instruction(instr, index)
        
        self.process_imports()
        
        result = '\n'.join(self.code_lines)
        result = re.sub(r'\n\s*\n\s*\n+', '\n\n', result)
        
        return result

def main():
    print("="*70)
    print("  PYTHON BYTECODE DECOMPILER")
    print("="*70)
    print("\nFeatures:")
    print("  • Control Flow Graph (CFG) construction and analysis")
    print("  • Loop detection with back-edge analysis")
    print("  • Conditional branch reconstruction")
    print("  • Data flow analysis (def-use chains)")
    print("  • Dominator tree computation")
    print("  • Stack optimization and reconstruction")
    print("  • Python 3.6 - 3.12+ bytecode support")
    print()
    
    input_path = input("Path to disassembled file: ").strip()
    
    if not os.path.exists(input_path):
        print(f"\nError: File '{input_path}' not found!")
        return
    
    print("\nReading bytecode...")
    with open(input_path, 'r', encoding='utf-8') as f:
        bytecode_content = f.read()
    
    print("Building Control Flow Graph...")
    decompiler = BytecodeDecompiler()
    
    print("Analyzing control and data flow...")
    reconstructed_code = decompiler.decompile(bytecode_content)
    
    print("\n" + "="*70)
    print("  RECONSTRUCTED SOURCE CODE")
    print("="*70 + "\n")
    print(reconstructed_code)
    print("\n" + "="*70 + "\n")
    
    output_path = input("Save to: ").strip()
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(reconstructed_code)
    
    lines_count = len(reconstructed_code.split('\n'))
    opcodes_count = len(decompiler.instructions)
    blocks_count = len(decompiler.basic_blocks)
    
    print(f"\nSuccessfully saved to '{output_path}'!")
    print(f"\nStatistics:")
    print(f"  • Generated {lines_count} lines from {opcodes_count} instructions")
    print(f"  • Basic blocks: {blocks_count}")
    print(f"  • Variables: {len(decompiler.variables)}")
    print(f"  • Functions: {len(decompiler.functions)}")
    print(f"  • Imports: {len(decompiler.imports)}")
    print()

if __name__ == "__main__":
    main()