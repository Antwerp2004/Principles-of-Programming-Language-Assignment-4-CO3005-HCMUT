from AST import * 
from Visitor import *
from Utils import *
from Emitter import Emitter
from Frame import Frame
from abc import ABC, abstractmethod
from functools import reduce
import operator


ops = {
    # Unary operators (right-to-left associativity)
    '!': operator.not_,      # logical NOT
    '-u': operator.neg,      # unary minus
    
    # Binary operators with precedence 3 (left-to-right)
    '*': operator.mul,
    '/': operator.truediv,
    '%': operator.mod,
    
    # Binary operators with precedence 4 (left-to-right)
    '+': operator.add,
    '-': operator.sub,
    
    # Binary comparison operators with precedence 5 (left-to-right)
    '==': operator.eq,
    '!=': operator.ne,
    '<': operator.lt,
    '<=': operator.le,
    '>': operator.gt,
    '>=': operator.ge,
    
    # Logical AND with precedence 6 (left-to-right)
    '&&': lambda a, b: a and b,
    
    # Logical OR with precedence 7 (left-to-right)
    '||': lambda a, b: a or b,
}


class MType:
    def __init__(self, partype, rettype):
        self.partype = partype
        self.rettype = rettype

    def __str__(self):
        return "MType([" + ",".join(str(x) for x in self.partype) + "]," + str(self.rettype) + ")"
    

class Symbol:
    def __init__(self, name, mtype, value=None):
        self.name = name
        self.mtype = mtype
        self.value = value
        self.const_value = None

    def __str__(self):
        return "Symbol(" + str(self.name) + "," + str(self.mtype) + ("" if self.value is None else "," + str(self.value)) + ("" if self.const_value is None else "," + str(self.const_value)) + ")"


class Val(ABC):
    pass


class Index(Val):
    def __init__(self, value):
        #value: Int
        self.value = value


class CName(Val):
    def __init__(self, value,isStatic=True):
        #value: String
        self.isStatic = isStatic
        self.value = value


class ClassType(Type):
    def __init__(self, name):
        #value: Id
        self.name = name


class CodeGenerator(BaseVisitor,Utils):

    def __init__(self):
        self.className = "MiniGoClass"
        self.astTree = None
        self.path = None
        self.emit = None
        self.main_emitter = None


    def init(self):
        mem = [
            Symbol("getInt",MType([],IntType()),CName("io",True)),
            Symbol("putInt",MType([IntType()],VoidType()),CName("io",True)),
            Symbol("putIntLn",MType([IntType()],VoidType()),CName("io",True)),
            Symbol("getFloat",MType([],IntType()),CName("io",True)),
            Symbol("putFloat",MType([FloatType()],VoidType()),CName("io",True)),
            Symbol("putFloatLn",MType([FloatType()],VoidType()),CName("io",True)),
            Symbol("getBool",MType([],BoolType()),CName("io",True)),
            Symbol("putBool",MType([BoolType()],VoidType()),CName("io",True)),
            Symbol("putBoolLn",MType([BoolType()],VoidType()),CName("io",True)),
            Symbol("getString",MType([],StringType()),CName("io",True)),
            Symbol("putString",MType([StringType()],VoidType()),CName("io",True)),
            Symbol("putStringLn",MType([StringType()],VoidType()),CName("io",True)),
            Symbol("putLn",MType([],VoidType()),CName("io",True)),
        ]
        return mem


    def gen(self, ast, dir_):
        gl = self.init()
        self.astTree = ast
        self.path = dir_
        # self.emit = Emitter(dir_ + "/" + self.className + ".j")
        self.visit(ast, gl)
    

    def cal_const(self, ast, o):
        if isinstance(ast, BinaryOp):
            if ast.op in ['+', '-', '*', '%', '==', '!=', '<', '>', '<=', '>=', '&&', '||']:
                return ops[ast.op](self.cal_const(ast.left, o), self.cal_const(ast.right, o))
            elif ast.op == '/':
                left_val = self.cal_const(ast.left, o)
                right_val = self.cal_const(ast.right, o)
                if isinstance(left_val, IntLiteral) and isinstance(right_val, IntLiteral):
                    return self.cal_const(ast.left, o) // self.cal_const(ast.right, o)
                else:
                    return self.cal_const(ast.left, o) / self.cal_const(ast.right, o)
        
        elif isinstance(ast, UnaryOp):
            if ast.op == '-':
                return ops['-u'](self.cal_const(ast.body, o))
            elif ast.op == '!':
                return ops['!'](self.cal_const(ast.body, o))
        
        elif isinstance(ast, (IntLiteral, FloatLiteral, StringLiteral, BooleanLiteral)):
            return ast.value
        
        elif isinstance(ast, Id):
            res = self.lookup(ast.name, o['env'], lambda x: x.name)
            return res.value
        
        else:
            return ast
       
               
    def generateStaticInitializer(self, global_vars_to_init_in_clinit, global_symbols_list):
        """Generates the <clinit> static initializer method."""
        frame = Frame("<clinit>", VoidType())  
        self.emit.printout(self.emit.emitMETHOD("<clinit>", MType([], VoidType()), True, frame))
        frame.enterScope(True) 
        self.emit.printout(self.emit.emitLABEL(frame.getStartLabel(), frame))
    
        # Generate code to initialize non-constant global variables and constants
        for decl in global_vars_to_init_in_clinit:
            if decl.varInit:
                sym = self.lookup(decl.varName, global_symbols_list, lambda x: x.name)
                init_code, _ = self.visit(decl.varInit, {'env': [global_symbols_list], 'frame': frame})
                self.emit.printout(init_code)
                self.emit.printout(self.emit.emitPUTSTATIC(f"{self.className}/{sym.name}", sym.mtype, frame))

        self.emit.printout(self.emit.emitLABEL(frame.getEndLabel(), frame))
        self.emit.printout(self.emit.emitRETURN(VoidType(), frame))  
        self.emit.printout(self.emit.emitENDMETHOD(frame))  
        frame.exitScope()
        

    def visitProgram(self, ast, o):
            global_symbols = o[:]
            # Build the global symbol table first, including information about target files/classes
            global_symbols_map = {}
            for sym in global_symbols: # Add built-ins to map
                global_symbols_map[sym.name] = sym

            # Process top-level declarations from the AST to populate the global symbol table
            for decl in ast.decl:
                if isinstance(decl, FuncDecl):
                    # Top-level function (non-receiver) -> static method in MiniGoClass
                    mtype = MType(list(map(lambda x: x.parType, decl.params)), decl.retType)
                    global_symbols_map[decl.name] = Symbol(decl.name, mtype, CName(self.className, True))

                elif isinstance(decl, MethodDecl):
                    receiver_type_sym = global_symbols_map.get(decl.recType.name)
                    # Method symbol: name, MType, CName(ReceiverClassName, isStatic=False)
                    method_mtype = MType(list(map(lambda x: x.parType, decl.fun.params)), decl.fun.retType)
                    global_symbols_map[decl.fun.name] = Symbol(decl.fun.name, method_mtype, CName(receiver_type_sym.name, False))

                elif isinstance(decl, (StructType, InterfaceType)):
                    # Type declaration -> maps to a separate class/interface file
                    global_symbols_map[decl.name] = Symbol(decl.name, decl, CName(decl.name, True)) # Value is the class name itself

                elif isinstance(decl, VarDecl):
                    # Global variable -> static field in MiniGoClass
                    global_symbols_map[decl.varName] = Symbol(decl.varName, decl.varType, CName(self.className, True))

                elif isinstance(decl, ConstDecl):
                    # Global constant -> static final field in MiniGoClass
                    const_value_evaluated = self.cal_const(decl.iniExpr, {'env': [list(global_symbols_map.values())]})
                    const_type = self.visit(decl.iniExpr, {'env': [list(global_symbols_map.values())]})[1]
                    global_symbols_map[decl.conName] = Symbol(decl.conName, const_type, const_value_evaluated)

            global_symbols_list = list(global_symbols_map.values())
            # --- Code Generation Phase ---
            self.main_emitter = Emitter(self.path + "/" + self.className + ".j")
            self.emit = self.main_emitter
            # Emit class directives for MiniGoClass.j
            self.main_emitter.printout(self.main_emitter.emitPROLOG(self.className, "java.lang.Object"))

            # Collect global variables/constants requiring .field directives in MiniGoClass
            global_fields_to_emit = []
            global_vars_to_init_in_clinit = [] # Subset of global vars needing explicit init

            for decl in ast.decl: # Iterate through original declarations to get initializers
                if isinstance(decl, VarDecl):
                    sym = self.lookup(decl.varName, global_symbols_list, lambda x: x.name)
                    if isinstance(sym.value, CName) and sym.value.value == self.className: # Only process globals in MiniGoClass
                        global_fields_to_emit.append((sym.name, sym.mtype, False, None)) # name, type, isFinal=False, value=None
                        if decl.varInit is not None:
                            global_vars_to_init_in_clinit.append(decl) # Add original declaration to list for <clinit>

                elif isinstance(decl, ConstDecl):
                    const_sym = self.lookup(decl.conName, global_symbols_list, lambda x: x.name)
                    global_fields_to_emit.append((const_sym.name, const_sym.mtype, True, const_sym.value)) # name, type, isFinal=True, value=const_value_evaluated

            # Emit static fields (.field directives) for global variables and constants in MiniGoClass
            for name, sym_type, is_final, value in global_fields_to_emit:
                self.main_emitter.printout(self.main_emitter.emitATTRIBUTE(name, sym_type, True, is_final, value))

            # Generate the static initializer <clinit> in MiniGoClass
            self.generateStaticInitializer(global_vars_to_init_in_clinit, global_symbols_list)

            # Generate code for functions, structs, interfaces, and methods
            for decl in ast.decl:
                if isinstance(decl, FuncDecl):
                    self.visitFuncDecl(decl, {'env': [global_symbols_list], 'frame': None, 'emitter': self.emit})

                elif isinstance(decl, StructType):
                    # Separate .j file for the struct
                    self.visitStructType(decl, {'env': [global_symbols_list]}) # Pass global symbols

                elif isinstance(decl, InterfaceType):
                    # Separate .j file for the interface
                    self.visitInterfaceType(decl, {'env': [global_symbols_list]}) # Pass global symbols

                # MethodDecl nodes are visited from visitStructType or visitInterfaceType, NOT directly here.

            self.main_emitter.printout(self.main_emitter.emitEPILOG())


    def visitVarDecl(self, ast, o):
        sym = self.lookup(ast.varName, [j for i in o['env'] for j in i], lambda x: x.name)
        location = sym.value
        var_type = sym.mtype

        if isinstance(location, Index):
            frame = o['frame']
            index = location.value
            if ast.varInit:
                init_code, _ = self.visit(ast.varInit, o)
                self.emit.printout(init_code)
                self.emit.printout(self.emit.emitWRITEVAR(var_name, var_type, index, frame))

            else:
                zero_value_code = ""
                if isinstance(var_type, (IntType, BoolType)):
                    zero_value_code = self.emit.emitPUSHICONST(0, frame)
                elif isinstance(var_type, FloatType):
                    zero_value_code = self.emit.emitPUSHFCONST("0.0", frame)
                elif isinstance(var_type, StringType):
                    zero_value_code = self.emit.emitPUSHCONST("", StringType(), frame)
                elif isinstance(var_type, (ArrayType, StructType, InterfaceType)):
                    zero_value_code = self.emit.emitPUSHNULL(frame)
                else:
                    print(f"Warning: Unknown type '{var_type}' for zero value initialization of variable '{ast.varName}'.")
                    zero_value_code = self.emit.emitPUSHNULL(frame)
                self.emit.printout(zero_value_code)
                self.emit.printout(self.emit.emitWRITEVAR(ast.varName, var_type, index, frame))

        return o
    

    def visitConstDecl(self, ast, o):
        sym = self.lookup(ast.conName, [j for i in o['env'] for j in i], lambda x: x.name)
        location = sym.value
        const_type = sym.mtype
        evaluated_value = sym.const_value

        if isinstance(location, Index):
            frame = o['frame']
            index = location.value
            code_to_push_value = ""
            if isinstance(const_type, (IntType, FloatType, BoolType, StringType)):
                code_to_push_value = self.emit.emitPUSHCONST(str(evaluated_value), const_type, frame)
            elif isinstance(const_type, (ArrayType, StructType)):
                code, _ = self.visit(evaluated_value, o)
                code_to_push_value = code
            elif evaluated_value is None:
                code_to_push_value = self.emit.emitPUSHNULL(frame)
            
        self.emit.printout(code_to_push_value)
        self.emit.printout(self.emit.emitWRITEVAR(ast.conName, const_type, index, frame))
        return o

    def visitFuncDecl(self, ast, o):
        emitter = o['emitter']
        frame = Frame(ast.name, ast.retType)
        frame.setCurrIndex(0)
        isMain = ast.name == "main"
        if isMain:
            mtype = MType([ArrayType([None],StringType())], VoidType())
        else:
            mtype = MType(list(map(lambda x: x.parType, ast.params)), ast.retType)
        
        emitter.printout(emitter.emitMETHOD(ast.name, mtype, True, frame))
        frame.enterScope(True)
        emitter.printout(emitter.emitLABEL(frame.getStartLabel(), frame))
        
        local_symbols = []
        env_for_body = {'env': [local_symbols] + o['env'], 'frame': frame, 'emitter': emitter} # New env for body

        if isMain:
            # Main has one parameter: args
            param_name = "args"
            param_type = ArrayType([None],StringType())
            param_index = frame.getNewIndex() # Index 0
            local_symbols.append(Symbol(param_name, param_type, Index(param_index)))
            emitter.printout(emitter.emitVAR(param_index, param_name, param_type, frame.getStartLabel(), frame.getEndLabel(), frame))
        else:
            # Other functions' parameters
            for param_decl in ast.params:
                param_name = param_decl.parName
                param_type = param_decl.parType
                param_index = frame.getNewIndex()
                local_symbols.append(Symbol(param_name, param_type, Index(param_index)))
                # Emit .var directive for the parameter
                emitter.printout(emitter.emitVAR(param_index, param_name, param_type, frame.getStartLabel(), frame.getEndLabel(), frame))

        self.visit(ast.body,env_for_body)
        emitter.printout(emitter.emitLABEL(frame.getEndLabel(), frame))
        emitter.printout(emitter.emitRETURN(ast.retType, frame))
        emitter.printout(emitter.emitENDMETHOD(frame))
        frame.exitScope()


    def visitIntType(self, ast, o):
        return IntType()
    

    def visitFloatType(self, ast, o):
        return FloatType()
    

    def visitStringType(self, ast, o):
        return StringType()
    

    def visitBoolType(self, ast, o):
        return BoolType()
    

    def visitVoidType(self, ast, o):
        return VoidType()
    

    def visitArrayType(self, ast, o):
        return ast
    

    def visitBlock(self, ast, o):
        frame = o['frame']
        emitter = o['emitter']
        local_symbols = []
        env_for_block = {'env': [local_symbols] + o['env'], 'frame': frame, 'emitter': emitter}
        frame.enterScope(True)
        emitter.printout(emitter.emitLABEL(frame.getStartLabel(), frame))

        statements_to_visit = []
        for member in ast.member:
            if isinstance(member, VarDecl):
                var_type = member.varType if member.varType else self.visit(member.varInit, env_for_block)[1]
                index = frame.getNewIndex()
                local_symbols.append(Symbol(member.varName, var_type, Index(index)))
                emitter.printout(emitter.emitVAR(index, member.varName, var_type, frame.getStartLabel(), frame.getEndLabel(), frame))

            if isinstance(member, ConstDecl):
                const_val_eval = self.cal_const(member.iniExpr, env_for_block)
                const_type = self.visit(member.iniExpr, env_for_block)[1]
                index = frame.getNewIndex()
                local_symbols.append(Symbol(member.conName, const_type, Index(index), const_val_eval))
                statements_to_visit.append(member)
                emitter.printout(emitter.emitVAR(index, member.conName, const_type, frame.getStartLabel(), frame.getEndLabel(), frame))
            

    def visitBreak(self, ast, o):
        frame = o['frame']
        emitter = o['emitter']
        emitter.printout(emitter.emitGOTO(frame.getEndLabel(), frame))


    def visitContinue(self, ast, o):
        frame = o['frame']
        emitter = o['emitter']
        emitter.printout(emitter.emitGOTO(frame.getContinueLabel(), frame))

    
    def visitReturn(self, ast, o):
        frame = o['frame']
        emitter = o['emitter']
        if ast.expr:
            expr_code, expr_type = self.visit(ast.expr, o)
            emitter.printout(expr_code)
            emitter.printout(emitter.emitRETURN(expr_type, frame))
        else:
            emitter.printout(emitter.emitRETURN(VoidType(), frame))


    def visitId(self, ast, o):
        sym = next(filter(lambda x: x.name == ast.name, [j for i in o['env'] for j in i]),None)
        if type(sym.value) is Index:
            return self.emit.emitREADVAR(ast.name, sym.mtype, sym.value.value, o['frame']),sym.mtype
        else:         
            return self.emit.emitGETSTATIC(f"{self.className}/{sym.name}",sym.mtype,o['frame']),sym.mtype
        
    
    def visitArrayCell(self, ast, o):
        frame = o['frame']
        emitter = o['emitter']
        result_code = []
        arr_code, arr_type = self.visit(ast.arr, o)
        result_code.append(arr_code)

        current_type = arr_type
        for i, idx_expr in enumerate(ast.idx):
            idx_code, _ = self.visit(idx_expr, o)
            result_code.append(idx_code)
            element_type_to_load = current_type.eleType
            result_code.append(emitter.emitALOAD(element_type_to_load, frame))
            current_type = element_type_to_load

        final_element_type = current_type
        return ''.join(result_code), final_element_type
    

    def visitFieldAccess(self, ast, o):
        frame = o['frame']
        emitter = o['emitter']
        result_code = []
        receiver_code, receiver_type = self.visit(ast.receiver, o)
        result_code.append(receiver_code)

        field_name = ast.field
        field_info = self.lookup(field_name, receiver_type.elements, lambda x: x[0])
        field_type = self.visit(field_info[1], o)

        struct_class_name = emitter.getFullType(receiver_type)
        qualified_field_name_for_jvm = f"{struct_class_name}/{field_name}"
        result_code.append(emitter.emitGETFIELD(qualified_field_name_for_jvm, field_type, frame))
        return ''.join(result_code), field_type


    # Leave for later
    # def visitFuncCall(self, ast, o):
    #     sym = next(filter(lambda x: x.name == ast.funName, o['env'][-1]),None)
    #     env = o.copy()
    #     env['isLeft'] = False
    #     [self.emit.printout(self.visit(x, env)[0]) for x in ast.args]
    #     self.emit.printout(self.emit.emitINVOKESTATIC(f"{sym.value.value}/{ast.funName}",sym.mtype, o['frame']))
    #     return o


    def visitIntLiteral(self, ast, o):
        return self.emit.emitPUSHICONST(ast.value, o['frame']), IntType()
    

    def visitFloatLiteral(self, ast, o):
        return self.emit.emitPUSHFCONST(str(ast.value), o['frame']), FloatType()
    

    def visitStringLiteral(self, ast, o):
        return self.emit.emitPUSHICONST(ast.value, o['frame']), StringType()    


    def visitBooleanLiteral(self, ast, o):
        return self.emit.emitPUSHICONST(str(ast.value), o['frame']), BoolType()
    

    def visitArrayLiteral(self, ast, o):
        frame = o['frame']
        emitter = o['emitter']
        result_code = []

        # Generate code to push all dimension sizes onto the stack
        dim_count = len(ast.dimens)
        for dim_expr in ast.dimens:
            dim_code, _ = self.visit(dim_expr, o)
            result_code.append(dim_code)

        # Allocate the array
        if dim_count == 1:
            result_code.append(emitter.emitNEWARRAY(ast.eleType))
        else:
            result_code.append(emitter.emitMULTIANEWARRAY(ArrayType(ast.dimens, ast.eleType), frame))
        
        # Initialize the innermost elements if ast.value is not empty
        if ast.value:
            temp_array_type = ArrayType(ast.dimens, ast.eleType)
            temp_array_index = frame.getNewIndex()
            result_code.append(emitter.emitWRITEVAR("temp_arr", temp_array_type, temp_array_index, frame))
            innermost_dim_size = len(ast.value)
            innermost_ele_type = ast.eleType

            for i in range(innermost_dim_size):
                result_code.append(emitter.emitREADVAR("temp_arr", temp_array_type, temp_array_index, frame))
                result_code.append(emitter.emitPUSHICONST(i, frame))
                element_code, _ = self.visit(ast.value[i], o)
                result_code.append(element_code)
                result_code.append(emitter.emitASTORE(innermost_ele_type, frame))
            
            result_code.append(emitter.emitREADVAR("temp_arr", temp_array_type, temp_array_index, frame))

        return ''.join(result_code), ArrayType(ast.dimens, ast.eleType)
    

    def visitStructLiteral(self, ast, o):
        frame = o['frame']
        emitter = o['emitter']
        result_code = []

        struct_type_symbol = self.lookup(ast.name, [j for i in o['env'] for j in i], lambda x: x.name)
        struct_type_ast = struct_type_symbol.mtype
        struct_jvm_class_name = emitter.getJVMType(struct_type_ast)

        # Allocate struct instance
        result_code.append(emitter.emitNEW(struct_jvm_class_name, frame))
        # Duplicate objectref for the constructor call
        result_code.append(emitter.emitDUP(frame))
        # Call the default constructor (<init>)
        constructor_descriptor = emitter.getJVMType(MType([], VoidType())) # ()V
        result_code.append(emitter.emitINVOKESPECIAL(frame, f"{struct_jvm_class_name}/<init>", MType([], VoidType())))

        # Initialize fields if ast.elements is not empty
        if ast.elements:
            temp_obj_index = frame.getNewIndex()
            result_code.append(emitter.emitWRITEVAR("temp_obj", struct_type_ast, temp_obj_index, frame))
            for field_name, field_value in ast.elements:
                result_code.append(emitter.emitREADVAR("temp_obj", struct_type_ast, temp_obj_index, frame))
                field_value_code, _ = self.visit(field_value, o)
                result_code.append(field_value_code)
                
                field_definition = self.lookup(field_name, struct_type_ast.elements, lambda x: x[0])
                field_type_ast = field_definition[1]
                qualified_field_name = f"{struct_jvm_class_name}/{field_name}"
                result_code.append(emitter.emitPUTFIELD(qualified_field_name, field_type_ast, frame))
            result_code.append(emitter.emitREADVAR("temp_obj", struct_type_ast, temp_obj_index, frame))
        
        return ''.join(result_code), struct_type_ast
    

    def visitNilLiteral(self, ast, o):
        return self.emit.emitPUSHNULL(o['frame']), None