from AST import * 
from Visitor import *
from Utils import *
from Emitter import Emitter
from Frame import Frame
from abc import ABC, abstractmethod
from functools import reduce
import operator


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
        initial_built_ins = o['env'][0]
        global_symbols_map = {}
        for sym in initial_built_ins: global_symbols_map[sym.name] = sym
        global_symbols_list = list(global_symbols_map.values())
        sym_build_env = {'env': [global_symbols_list]}

        for decl in ast.decl:
            if isinstance(decl, FuncDecl):
                param_types = [self.visit(p.parType, sym_build_env) for p in decl.params]
                ret_type = self.visit(decl.retType, sym_build_env)
                mtype = MType(param_types, ret_type)
                global_symbols_map[decl.name] = Symbol(decl.name, mtype, CName(self.className, True))

            elif isinstance(decl, MethodDecl):
                # maps to a separate class/interface file
                receiver_type_sym = global_symbols_map.get(decl.recType.name)
                method_mtype = MType(list(map(lambda x: x.parType, decl.fun.params)), decl.fun.retType)
                global_symbols_map[decl.fun.name] = Symbol(decl.fun.name, method_mtype, CName(receiver_type_sym.name, False))

            elif isinstance(decl, (StructType, InterfaceType)):
                # Type declaration -> maps to a separate class/interface file
                global_symbols_map[decl.name] = Symbol(decl.name, decl, CName(decl.name, True))

            elif isinstance(decl, VarDecl):
                # Global variable -> static field in MiniGoClass
                var_type = self.visit(decl.varType, sym_build_env) if decl.varType else None
                if var_type is None and decl.varInit:
                    var_type = self.visit(decl.varInit, o)[1]
                global_symbols_map[decl.varName] = Symbol(decl.varName, var_type, CName(self.className, True))

            elif isinstance(decl, ConstDecl):
                # Global constant -> static final field in MiniGoClass
                const_type = self.visit(decl.iniExpr, sym_build_env)[1]
                global_symbols_map[decl.conName] = Symbol(decl.conName, const_type, CName(self.className, True))

        # --- Code Generation Phase ---
        self.emit.printout(self.emit.emitPROLOG(self.className, "java.lang.Object"))

        items_needing_clinit = []
        for decl in ast.decl:
            sym = None
            is_const = False
            init_expr = None
            if isinstance(decl, (VarDecl, ConstDecl)):
                name = decl.varName if isinstance(decl, VarDecl) else decl.conName
                sym = global_symbols_map.get(name)
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
        self.generateStaticInitializer(items_needing_clinit, global_symbols_list, self.emit)

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
                    zero_value_code = self.emit.emitPUSHICONST(0, frame)
                elif isinstance(var_type, FloatType):
                    zero_value_code = self.emit.emitPUSHFCONST("0.0", frame)
                elif isinstance(var_type, StringType):
                    zero_value_code = self.emit.emitPUSHCONST("", StringType(), frame)
                elif isinstance(var_type, (ArrayType, StructType, InterfaceType)):
                    zero_value_code = self.emit.emitPUSHNULL(frame)
                emitter.printout(zero_value_code)

            emitter.printout(self.emit.emitWRITEVAR(ast.varName, var_type, index, frame))

        return o
    

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