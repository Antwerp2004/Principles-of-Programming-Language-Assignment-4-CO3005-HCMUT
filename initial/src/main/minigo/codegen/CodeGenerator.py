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
    def __init__(self, name, mtype, value=None, const_value=None):
        self.name = name
        self.mtype = mtype
        self.value = value # Location (Index/CName) or None
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
    def __init__(self, value, isStatic=True):
        #value: String
        self.value = value
        self.isStatic = isStatic


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
        self.emit = Emitter(dir_ + "/" + self.className + ".j")
        self.visit(ast, {'env': [gl]})


    def cal_const(self, ast, env):
        if isinstance(ast, BinaryOp):
            left_val = self.cal_const(ast.left, param)
            right_val = self.cal_const(ast.right, param)
            op = ast.op
            if op == '/' and isinstance(ast.left, IntLiteral) and isinstance(ast.right, IntLiteral):
                return left_val // right_val
            return ops[op](left_val, right_val)
        
        elif isinstance(ast, UnaryOp):
            operand_val = self.cal_const(ast.body, param)
            op = ast.op
            if op == '-':
                return ops['-u'](operand_val)
            elif op == '!':
                return ops['!'](operand_val)
        
        elif isinstance(ast, (IntLiteral, FloatLiteral, StringLiteral, BooleanLiteral)):
            return ast.value
        
        elif isinstance(ast, NilLiteral):
            return None
        
        elif isinstance(ast, Id):
            res = self.lookup(ast.name, [j for i in env['env'] for j in i], lambda x: x.name)
            return res.const_value
        
        elif isinstance(ast, (ArrayLiteral, StructLiteral)):
            return ast
       
               
    def generateStaticInitializer(self, items_to_init, global_symbols_list, emitter):
        """Generates the <clinit> static initializer method."""
        frame = Frame("<clinit>", VoidType())  
        emitter.printout(emitter.emitMETHOD("<clinit>", MType([], VoidType()), True, frame))
        frame.enterScope(True) 
        emitter.printout(emitter.emitLABEL(frame.getStartLabel(), frame))
        init_env = {'env': [global_symbols_list], 'frame': frame, 'emitter': emitter}
    
        # Generate code to initialize non-constant global variables and constants
        for sym, decl_node in items_to_init:
            init_expr = None
            if isinstance(decl_node, VarDecl):
                init_expr = decl_node.varInit
            elif isinstance(decl_node, ConstDecl):
                init_expr = decl_node.iniExpr
            init_code, _ = self.visit(init_expr, init_env)
            emitter.printout(init_code)
            emitter.printout(self.emit.emitPUTSTATIC(f"{self.className}/{sym.name}", sym.mtype, frame))

        emitter.printout(emitter.emitLABEL(frame.getEndLabel(), frame))
        emitter.printout(emitter.emitRETURN(VoidType(), frame))  
        emitter.printout(emitter.emitENDMETHOD(frame))  
        frame.exitScope()
        

    def visitProgram(self, ast, o):
        env = o['env'][0]
        sym_build_env = {'env': [env]}

        for decl in ast.decl:
            if isinstance(decl, FuncDecl):
                param_types = [self.visit(p.parType, sym_build_env) for p in decl.params]
                ret_type = self.visit(decl.retType, sym_build_env)
                mtype = MType(param_types, ret_type)
                env.append(Symbol(decl.name, mtype, CName(self.className, True)))

            elif isinstance(decl, (StructType, InterfaceType)):
                # Type declaration -> maps to a separate class/interface file
                env.append(Symbol(decl.name, decl, CName(decl.name, True)))

            elif isinstance(decl, VarDecl):
                # Global variable -> static field in MiniGoClass
                var_type = self.visit(decl.varType, sym_build_env) if decl.varType else None
                if var_type is None and decl.varInit:
                    var_type = self.visit(decl.varInit, o)[1]
                env.append(Symbol(decl.varName, var_type, CName(self.className, True)))

            elif isinstance(decl, ConstDecl):
                # Global constant -> static final field in MiniGoClass
                const_value = self.cal_const(decl.iniExpr, sym_build_env)
                const_type = self.visit(decl.iniExpr, sym_build_env)[1]
                env.append(Symbol(decl.conName, const_type, CName(self.className, True), const_value))

        for decl in ast.decl:
            if isinstance(decl, MethodDecl):
                sym = self.lookup(decl.recType.name, env, lambda x: x.name)
                if isinstance(sym.mtype, StructType):
                    sym.methods.append(decl)
                elif isinstance(sym.mtype, InterfaceType):
                    prototype = Prototype(decl.fun.name, [x.parType for x in decl.fun.params], decl.fun.retType)
                    sym.methods.append(prototype)

        # --- Code Generation Phase ---
        self.emit.printout(self.emit.emitPROLOG(self.className, "java.lang.Object", False))

        items_needing_clinit = []
        for decl in ast.decl:
            sym = None
            is_const = False
            init_expr = None
            if isinstance(decl, (VarDecl, ConstDecl)):
                name = decl.varName if isinstance(decl, VarDecl) else decl.conName
                sym = self.lookup(name, [j for i in o['env'] for j in i], lambda x: x.name)
                is_const = isinstance(decl, ConstDecl)
                init_expr = decl.varInit if isinstance(decl, VarDecl) else decl.iniExpr

            if sym and isinstance(sym.value, CName) and sym.value.value == self.className:
                # This global belongs in MiniGoClass.j
                is_final = is_const
                # Emit static fields (.field directives) for global variables and constants in MiniGoClass
                self.emit.printout(self.emit.emitATTRIBUTE(name, sym.mtype, True, is_final, None))
                if init_expr:
                    items_needing_clinit.append((sym, decl))

        # Generate the static initializer <clinit> in MiniGoClass
        self.generateStaticInitializer(items_needing_clinit, env, self.emit)

        # Generate code for functions, structs, interfaces, and methods
        for decl in ast.decl:
            if isinstance(decl, FuncDecl):
                self.visit(decl, {**sym_build_env, 'emitter': self.emit})

            elif isinstance(decl, StructType):
                # Separate .j file for the struct
                self.visit(decl, {**sym_build_env})

            elif isinstance(decl, InterfaceType):
                # Separate .j file for the interface
                self.visit(decl, {**sym_build_env})

            # MethodDecl nodes are visited from visitStructType or visitInterfaceType, NOT directly here.

        self.emit.printout(self.emit.emitEPILOG())


    def visitVarDecl(self, ast, o):
        emitter = o['emitter']
        frame = o['frame']
        sym = self.lookup(ast.varName, [j for i in o['env'] for j in i], lambda x: x.name)
        location = sym.value
        var_type = sym.mtype

        if isinstance(location, Index):
            index = location.value
            if ast.varInit:
                init_code, _ = self.visit(ast.varInit, o)
                emitter.printout(init_code)

            else:
                zero_value_code = ""
                if isinstance(var_type, (IntType, BoolType)):
                    zero_value_code = emitter.emitPUSHICONST(0, frame)
                elif isinstance(var_type, FloatType):
                    zero_value_code = emitter.emitPUSHFCONST("0.0", frame)
                elif isinstance(var_type, StringType):
                    zero_value_code = emitter.emitPUSHCONST("", StringType(), frame)
                elif isinstance(var_type, (ArrayType, StructType, InterfaceType)):
                    zero_value_code = emitter.emitPUSHNULL(frame)
                emitter.printout(zero_value_code)

            emitter.printout(self.emit.emitWRITEVAR(ast.varName, var_type, index, frame))
    

    def visitConstDecl(self, ast, o):
        emitter = o['emitter']
        frame = o['frame']
        sym = self.lookup(ast.conName, [j for i in o['env'] for j in i], lambda x: x.name)
        location = sym.value
        const_type = sym.mtype

        index = location.value
        init_code, _ = self.visit(ast.iniExpr, o)
        emitter.printout(init_code)
        emitter.printout(self.emit.emitWRITEVAR(ast.conName, const_type, index, frame))
        

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


    def visitMethodDecl(self, ast, o):
        emitter = o['emitter']
        method_name = ast.fun.name
        ret_type = ast.fun.retType

        param_types = [p.parType for p in ast.fun.params]
        method_mtype = MType(param_types, ret_type)

        frame = Frame(method_name, ret_type)
        emitter.printout(emitter.emitMETHOD(method_name, method_mtype, False, frame))
        frame.enterScope(True)
        emitter.printout(emitter.emitLABEL(frame.getStartLabel(), frame))
        local_symbols = []
        env_for_body = {'env': [local_symbols] + o['env'],
                        'frame': frame,
                        'emitter': emitter}
        
        # Add 'this' parameter (index 0)
        this_index = frame.getNewIndex()
        local_symbols.append(Symbol(ast.receiver, ast.recType, Index(this_index)))
        emitter.printout(emitter.emitVAR(this_index, ast.receiver, ast.recType, frame.getStartLabel(), frame.getEndLabel(), frame))

        # Add method parameters (starting from index 1)
        for param_decl in ast.fun.params:
            param_name = param_decl.parName
            param_type = param_decl.parType
            param_index = frame.getNewIndex()
            local_symbols.append(Symbol(param_name, param_type, Index(param_index)))
            emitter.printout(emitter.emitVAR(param_index, param_name, param_type, frame.getStartLabel(), frame.getEndLabel(), frame))

        self.visit(ast.fun.body, env_for_body)

        emitter.printout(emitter.emitLABEL(frame.getEndLabel(), frame))
        emitter.printout(emitter.emitRETURN(ret_type, frame))
        emitter.printout(emitter.emitENDMETHOD(frame))
        frame.exitScope()


    def visitPrototype(self, ast, o):
        emitter = o['emitter']
        method_mtype = MType(ast.params, ast.retType)
        jvm_descriptor = emitter.getJVMType(method_mtype)
        # Manually construct the Jasmin directive string
        abstract_method_code = f".method public abstract {ast.name}{jvm_descriptor}\n"
        # Add .end method if required by Jasmin for abstract methods
        abstract_method_code += ".end method\n"
        emitter.printout(abstract_method_code)


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
    

    def visitInterfaceType(self, ast, o):
        interface_name = ast.name
        global_env = o['env']
        interface_emitter = Emitter(self.path + "/" + interface_name + ".j")
        interface_emitter.printout(interface_emitter.emitPROLOG(interface_name, "", True))

        env_for_methods = {'env': global_env, 'emitter': interface_emitter, 'is_interface_method': False}
        for prototype in ast.methods:
            self.visit(prototype, env_for_methods)
        interface_emitter.emitEPILOG()


    def visitStructType(self, ast, o):
        struct_name = ast.name
        global_env = o['env']
        struct_emitter = Emitter(self.path + "/" + struct_name + ".j")
        struct_emitter.printout(struct_emitter.emitPROLOG(struct_name, "java.lang.Object", False))
    
        for field_name, field_type_node in ast.elements:
            field_type = self.visit(field_type_node, o)
            struct_emitter.printout(struct_emitter.emitATTRIBUTE(field_name, field_type, False, False, None))
        
        init_frame = Frame("<init>", VoidType())
        init_mtype = MType([], VoidType())
        struct_emitter.printout(struct_emitter.emitMETHOD("<init>", init_mtype, False, init_frame))
        init_frame.enterScope(True)

        start_label = init_frame.getStartLabel()
        end_label = init_frame.getEndLabel()
        this_index = init_frame.getNewIndex()

        struct_emitter.printout(struct_emitter.emitVAR(this_index, "this", ast, start_label, end_label, init_frame))
        struct_emitter.printout(struct_emitter.emitLABEL(start_label, init_frame))
        struct_emitter.printout(struct_emitter.emitREADVAR("this", ast, this_index, init_frame))
        struct_emitter.printout(struct_emitter.emitINVOKESPECIAL(init_frame, "java/lang/Object/<init>", MType([], VoidType())))

        struct_emitter.printout(struct_emitter.emitLABEL(end_label, init_frame))
        struct_emitter.printout(struct_emitter.emitRETURN(VoidType(), init_frame))
        struct_emitter.printout(struct_emitter.emitENDMETHOD(init_frame))
        init_frame.exitScope()

        env_for_methods = {'env': global_env, 'emitter': struct_emitter, 'is_interface_method': False}
        for method_decl in ast.methods:
            self.visit(method_decl, env_for_methods)
        struct_emitter.emitEPILOG()


    def visitBlock(self, ast, o):
        emitter = o['emitter']
        frame = o['frame']
        local_symbols = []
        env_for_block = {'env': [local_symbols] + o['env'], 'frame': frame, 'emitter': emitter}
        frame.enterScope(False)
        emitter.printout(emitter.emitLABEL(frame.getStartLabel(), frame))

        for member in ast.member:
            if isinstance(member, VarDecl):
                var_type = self.visit(member.varType, env_for_block) if member.varType else self.visit(member.varInit, env_for_block)[1]
                index = frame.getNewIndex()
                local_symbols.append(Symbol(member.varName, var_type, Index(index)))
                emitter.printout(emitter.emitVAR(index, member.varName, var_type, frame.getStartLabel(), frame.getEndLabel(), frame))

            if isinstance(member, ConstDecl):
                const_value = self.cal_const(member.iniExpr, env_for_block)
                const_type = self.visit(member.iniExpr, env_for_block)[1]
                index = frame.getNewIndex()
                local_symbols.append(Symbol(member.conName, const_type, Index(index), const_value))
                emitter.printout(emitter.emitVAR(index, member.conName, const_type, frame.getStartLabel(), frame.getEndLabel(), frame))

            elif isinstance(member, Assign) and isinstance(member.lhs, Id):
                lhs_name = member.lhs.name
                sym = self.lookup(lhs_name, [j for i in o['env'] for j in i], lambda x: x.name)
                if not sym:
                    lhs_type = self.visit(member.rhs, env_for_block)[1]
                    index = frame.getNewIndex()
                    local_symbols.append(Symbol(lhs_name, lhs_type, Index(index)))
                emitter.printout(emitter.emitVAR(index, lhs_name, lhs_type, frame.getStartLabel(), frame.getEndLabel(), frame))

        for stmt in ast.member:
            self.visit(stmt, env_for_block)

        emitter.printout(emitter.emitLABEL(frame.getEndLabel(), frame))
        frame.exitScope()


    def visitAssign(self, ast, o):
        emitter = o['emitter']
        frame = o['frame']
        lhs_code, store_code = "", ""
        target_type = None

        if isinstance(ast.lhs, Id):
            lhs_name = ast.lhs.name
            target_sym = self.lookup(lhs_name, [j for i in o['env'] for j in i], lambda x: x.name)
            target_location = target_sym.value
            target_type = target_sym.mtype

            rhs_code, _ = self.visit(ast.rhs, o)
            emitter.printout(rhs_code)
            if isinstance(target_location, Index):
                store_code = emitter.emitWRITEVAR(lhs_name, target_type, target_location.value, frame)
            elif isinstance(target_location, CName):
                store_code = emitter.emitPUTSTATIC(f"{target_location.value}/{lhs_name}", target_type, frame)

        elif isinstance(ast.lhs, ArrayCell):
            arr_code, arr_type = self.visit(ast.lhs.arr, o)
            lhs_code += arr_code
            for idx_expr in ast.lhs.idx:
                idx_code, _ = self.visit(idx_expr, o)
                lhs_code += idx_code
            ele_type = self.visit(arr_type.eleType, o)
            store_code = emitter.emitASTORE(ele_type, frame)

            emitter.printout(lhs_code)
            rhs_code, _ = self.visit(ast.rhs, o)
            emitter.printout(rhs_code)

        elif isinstance(ast.lhs, FieldAccess):
            receiver_code, receiver_type = self.visit(ast.lhs.receiver, o)
            lhs_code += receiver_code
            field_name = ast.lhs.field
            field_info = self.lookup(field_name, receiver_type.elements, lambda x: x[0])
            field_type = self.visit(field_info[1], o)
            struct_class_name = emitter.getFullType(receiver_type)
            store_code = emitter.emitPUTFIELD(f"{struct_class_name}/{field_name}", field_type, frame)

            emitter.printout(lhs_code)
            rhs_code, _ = self.visit(ast.rhs, o)
            emitter.printout(rhs_code)

        emitter.printout(store_code)
            

    def visitIf(self, ast, o):
        emitter = o['emitter']
        frame = o['frame']

        cond_code, _ = self.visit(ast.expr, o)
        emitter.printout(cond_code)

        label_end = frame.getNewLabel() # Label after the entire if/else structure
        # Label to jump to else condition is false. If no else, jump directly to end.
        label_false_target = frame.getNewLabel() if ast.elseStmt else label_end
        emitter.printout(emitter.emitIFFALSE(label_false_target, frame))

        self.visit(ast.thenStmt, o)

        if ast.elseStmt:
            emitter.printout(emitter.emitGOTO(label_end, frame))
            emitter.printout(emitter.emitLABEL(label_false_target, frame))
            self.visit(ast.elseStmt, o)
        
        emitter.printout(emitter.emitLABEL(label_end, frame))

    
    def visitForBasic(self, ast, o):
        emitter = o['emitter']
        frame = o['frame']

        # Label for the start of the condition check (top of the loop)
        label_condition = frame.getNewLabel()
        # Label for the instruction immediately after the loop exits
        label_exit = frame.getNewLabel()

        frame.enterLoop(label_condition, label_exit)
        emitter.printout(emitter.emitLABEL(label_condition, frame))

        cond_code, _ = self.visit(ast.cond, o)
        emitter.printout(cond_code)

        emitter.printout(emitter.emitIFFALSE(label_exit, frame))
        self.visit(ast.loop, o)

        emitter.printout(emitter.emitGOTO(label_condition, frame))
        emitter.printout(emitter.emitLABEL(label_exit, frame))
        frame.exitLoop()

    
    def visitForStep(self, ast, o):
        emitter = o['emitter']
        frame = o['frame']

        # Condition check label
        label_condition = frame.getNewLabel()
        # Update label
        label_update = frame.getNewLabel()
        # Exit label
        label_exit = frame.getNewLabel()

        local_symbols_for_loop = []
        env_for_loop = {'env': [local_symbols_for_loop] + o['env'],
                        'frame': frame,
                        'emitter': emitter}

        self.visit(ast.init, env_for_loop)
        frame.enterLoop(label_update, label_exit)
        emitter.printout(emitter.emitLABEL(label_condition, frame))

        cond_code, _ = self.visit(ast.cond, env_for_loop)
        emitter.printout(cond_code)
        emitter.printout(emitter.emitIFFALSE(label_exit, frame))
        self.visit(ast.loop, env_for_loop)

        emitter.printout(emitter.emitLABEL(label_update, frame))
        self.visit(ast.upda, env_for_loop)
        emitter.printout(emitter.emitGOTO(label_condition, frame))
        emitter.printout(emitter.emitLABEL(label_exit, frame))
        frame.exitLoop()


    def visitForEach(self, ast, o):
        emitter = o['emitter']
        frame = o['frame']

        idx_sym = None
        idx_name = ast.idx.name
        if idx_name is not '_':
            idx_sym = self.lookup(idx_name, [j for i in o['env'] for j in i], lambda x: x.name)
        value_sym = self.lookup(ast.value.name, [j for i in o['env'] for j in i], lambda x: x.name)

        arr_code, arr_type = self.visit(ast.arr, o)
        emitter.printout(arr_code)
        element_type = arr_type.eleType

        # Store array reference and get length
        emitter.printout(emitter.emitDUP(frame))
        temp_array_ref_idx = frame.getNewIndex()
        emitter.printout(emitter.emitWRITEVAR("temp_arr_foreach", arr_type, temp_array_ref_idx, frame))
        emitter.printout(emitter.emitARRAYLENGTH(arr_type, frame))
        temp_length_idx = frame.getNewIndex()
        emitter.printout(emitter.emitWRITEVAR("temp_len_foreach", IntType(), temp_length_idx, frame))

        # Initialize hidden index counter to 0
        temp_counter_idx = frame.getNewIndex()
        emitter.printout(emitter.emitPUSHICONST(0, frame))
        emitter.printout(emitter.emitWRITEVAR("temp_idx_foreach", IntType(), temp_counter_idx, frame))

        # Labels
        label_condition = frame.getNewLabel()
        label_continue = frame.getNewLabel()
        label_exit = frame.getNewLabel()

        frame.enterLoop(label_continue, label_exit)
        emitter.printout(emitter.emitLABEL(label_condition, frame))
        # Check if index < length
        emitter.printout(emitter.emitREADVAR("temp_idx_foreach", IntType(), temp_counter_idx, frame))
        emitter.printout(emitter.emitREADVAR("temp_len_foreach", IntType(), temp_length_idx, frame))
        emitter.printout(emitter.emitIF_ICMPGE(label_exit, frame))

        # Assign current counter value to 'idx' variable (IF NOT BLANK)
        if idx_sym:
            emitter.printout(emitter.emitREADVAR("temp_idx_foreach", IntType(), temp_counter_idx, frame))
            if isinstance(idx_sym.value, Index):
                emitter.printout(emitter.emitWRITEVAR(idx_name, IntType(), idx_sym.value.value, frame))
            elif isinstance(idx_sym.value, CName):
                emitter.printout(emitter.emitPUTSTATIC(f"{idx_sym.value.value}/{idx_name}", IntType(), frame))

        # Assign current element value to the pre-declared 'value' variable
        emitter.printout(emitter.emitREADVAR("temp_arr_foreach", arr_type, temp_array_ref_idx, frame))
        emitter.printout(emitter.emitREADVAR("temp_idx_foreach", IntType(), temp_counter_idx, frame))
        emitter.printout(emitter.emitALOAD(element_type, frame))
        if isinstance(value_sym.value, Index):
            emitter.printout(emitter.emitWRITEVAR(value_sym.name, element_type, value_sym.value.value, frame))
        elif isinstance(value_sym.value, CName):
            emitter.printout(emitter.emitPUTSTATIC(f"{value_sym.value.value}/{value_sym.name}", element_type, frame))

        # Body
        self.visit(ast.loop, o)
        emitter.printout(emitter.emitLABEL(label_continue, frame))
        # Increment hidden counter
        emitter.printout(emitter.emitIINC(temp_counter_idx, 1, frame))
        emitter.printout(emitter.emitGOTO(label_condition, frame))
        emitter.printout(emitter.emitLABEL(label_exit, frame))
        frame.exitLoop()


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
        emitter = o['emitter']
        frame = o['frame']

        sym = self.lookup(ast.name, [j for i in o['env'] for j in i], lambda x: x.name)
        sym_type = sym.mtype
        location = sym.value

        if isinstance(location, Index):
            read_code = emitter.emitREADVAR(ast.name, sym_type, location.value, frame)
            return read_code, sym_type
        elif isinstance(location, CName) and location.value == self.className:
            read_code = emitter.emitGETSTATIC(f"{location.value}/{ast.name}", sym_type, frame)
            return read_code, sym_type

    
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


    def visitBinaryOp(self, ast, o):
        emitter = o['emitter']
        frame = o['frame']
        op = ast.op
        left_code, left_type = self.visit(ast.left, o)
        right_code, right_type = self.visit(ast.right, o)
        result_code = []
        result_type = None

        if op in ['+', '-', '*', '/', '%']:
            if isinstance(left_type, FloatType) or isinstance(right_type, FloatType):
                if isinstance(left_type, IntType):
                    result_code.append(left_code)
                    result_code.append(emitter.emitI2F(frame))
                    result_code.append(right_code)
                elif isinstance(right_type, IntType):
                    result_code.append(left_code)
                    result_code.append(right_code)
                    result_code.append(emitter.emitI2F(frame))
                else:
                    result_code.append(left_code)
                    result_code.append(right_code)
            
            elif op == '+' and isinstance(left_type, StringType) and isinstance(right_type, StringType):
                result_code.append(left_code)
                result_code.append(right_code)
                result_type = StringType()

            elif isinstance(left_type, IntType) and isinstance(right_type, IntType):
                result_code.append(left_code)
                result_code.append(right_code)
                result_type = IntType()
            
            if op == '%':
                result_code.append(emitter.emitMOD(frame))
            elif op in ['+', '-']:
                result_code.append(emitter.emitADDOP(op, result_type, frame))
            elif op in ['*', '/']:
                result_code.append(emitter.emitMULOP(op, result_type, frame))

        elif op in ['==', '!=', '<', '<=', '>', '>=']:
            result_type = BoolType()
            result_code.append(left_code)
            result_code.append(right_code)
            result_code.append(emitter.emitREOP(op, left_type, frame))

        elif op in ['&&', '||']:
            result_type = BoolType()
            result_code.append(left_code)
            result_code.append(right_code)
            if op == '&&':
                result_code.append(emitter.emitANDOP(frame))
            elif op == '||':
                result_code.append(emitter.emitOROP(frame))
        
        return ''.join(result_code), result_type
    

    def visitUnaryOp(self, ast, o):
        emitter = o['emitter']
        frame = o['frame']
        op = ast.op
        body_code, body_type = self.visit(ast.body, o)
        result_code = []
        result_type = None

        if op == '-':
            result_type = body_type
            result_code.append(body_code)
            emitter.append(emitter.emitNEGOP(body_type, frame))

        elif op == '!':
            result_type = BoolType()
            result_code.append(body_code)
            emitter.append(emitter.emitNOT(body_type, frame))

        return ''.join(result_code), result_type


    def visitFuncCall(self, ast, o):
        emitter = o['emitter']
        frame = o['frame']
        result_code = []

        sym = self.lookup(ast.funName, [j for i in o['env'] for j in i], lambda x: x.name)
        func_mtype = sym.mtype
        location = sym.value

        for arg_expr in ast.args:
            arg_code, _ = self.visit(arg_expr, o)
            result_code.append(arg_code)

        class_name = location.value
        invoke_code = emitter.emitINVOKESTATIC(f"{class_name}/{ast.funName}", func_mtype, frame)
        result_code.append(invoke_code)

        return ''.join(result_code), func_mtype.rettype
    

    def visitMethCall(self, ast, o):
        emitter = o['emitter']
        frame = o['frame']
        result_code = []

        receiver_code, receiver_type = self.visit(ast.receiver, o)
        result_code.append(receiver_code)
        for arg_expr in ast.args:
            arg_code, _ = self.visit(arg_expr, o)
            result_code.append(arg_code)

        method_sym = self.lookup(ast.metName, [symbol for scope in o['env'] for symbol in scope], lambda x: x.name)
        method_location = method_sym.value
        expected_receiver_name = receiver_type.name
        if not isinstance(method_location, CName) or method_location.isStatic or method_location.value != expected_receiver_name:
            raise Exception(f"CodeGen Error: Method '{ast.metName}' not found for receiver type '{expected_receiver_name}' or is static.")
        
        method_mtype = method_sym.mtype
        if isinstance(receiver_type, StructType):
            invoke_code = emitter.emitINVOKEVIRTUAL(f"{receiver_type.name}/{ast.metName}", method_mtype, frame)
        elif isinstance(receiver_type, InterfaceType):
            invoke_code = emitter.emitINVOKEINTERFACE(f"{receiver_type.name}/{ast.metName}", method_mtype, frame)

        result_code.append(invoke_code)
        return ''.join(result_code), method_mtype.rettype


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
            result_code.append(emitter.emitNEWARRAY(ast.eleType, frame))
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