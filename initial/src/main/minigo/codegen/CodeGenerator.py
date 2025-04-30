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

    def __str__(self):
        return "Symbol(" + str(self.name) + "," + str(self.mtype) + ("" if self.value is None else "," + str(self.value)) + ")"


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
        var_name = ast.varName
        sym = self.lookup(var_name, [j for i in o['env'] for j in i], lambda x: x.name)
        location = sym.value
        var_type = sym.mtype

        if isinstance(location, Index):
            frame = o['frame']
            index = location.value
            if ast.varInit:
                init_code, _ = self.visit(ast.varInit, o)
                self.emit.printout(init_code)
                self.emit.printout(self.emit.emitWRITEVAR(var_name, var_type, index, frame))



    def visitFuncDecl(self, ast, o):
        emitter = o['emitter']
        frame = Frame(ast.name, ast.retType)
        frame.setCurrIndex(0)
        isMain = ast.name == "main"
        if isMain:
            mtype = MType([ArrayType([None],StringType())], VoidType())
        else:
            mtype = MType(list(map(lambda x: x.parType, ast.params)), ast.retType)
        
        global_symbols_list = o['env'][0]
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
    

    def visitFuncCall(self, ast, o):
        sym = next(filter(lambda x: x.name == ast.funName, o['env'][-1]),None)
        env = o.copy()
        env['isLeft'] = False
        [self.emit.printout(self.visit(x, env)[0]) for x in ast.args]
        self.emit.printout(self.emit.emitINVOKESTATIC(f"{sym.value.value}/{ast.funName}",sym.mtype, o['frame']))
        return o
    

    def visitBlock(self, ast, o):
        env = o.copy()
        env['env'] = [[]] + env['env']
        env['frame'].enterScope(False)
        self.emit.printout(self.emit.emitLABEL(env['frame'].getStartLabel(), env['frame']))
        env = reduce(lambda acc,e: self.visit(e,acc),ast.member,env)
        self.emit.printout(self.emit.emitLABEL(env['frame'].getEndLabel(), env['frame']))
        env['frame'].exitScope()
        return o
    

    def visitId(self, ast, o):
        sym = next(filter(lambda x: x.name == ast.name, [j for i in o['env'] for j in i]),None)
        if type(sym.value) is Index:
            return self.emit.emitREADVAR(ast.name, sym.mtype, sym.value.value, o['frame']),sym.mtype
        else:         
            return self.emit.emitGETSTATIC(f"{self.className}/{sym.name}",sym.mtype,o['frame']),sym.mtype
        

    def visitIntLiteral(self, ast, o):
        return self.emit.emitPUSHICONST(ast.value, o['frame']), IntType()
    

    def visitFloatLiteral(self, ast, o):
        return self.emit.emitPUSHFCONST(str(ast.value), o['frame']), FloatType()
    

    def visitBooleanLiteral(self, ast, o):
        return self.emit.emitPUSHICONST(str(ast.value), o['frame']), BoolType()
    

    def visitStringLiteral(self, ast, o):
        return self.emit.emitPUSHICONST(ast.value, o['frame']), StringType()