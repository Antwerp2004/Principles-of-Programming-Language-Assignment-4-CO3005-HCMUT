from AST import *
from Utils import *
from StaticCheck import *
from StaticError import *
import CodeGenerator as cgen
from MachineCode import JasminCode
from CodeGenError import *


class Emitter():
    def __init__(self, filename):
        self.filename = filename
        self.buff = list()
        self.jvm = JasminCode()


    def getJVMType(self, inType):
        if isinstance(inType, IntType):
            return "I"
        elif isinstance(inType, FloatType):
            return "F"
        elif isinstance(inType, BoolType):
            return "Z"
        elif isinstance(inType, StringType):
            return "Ljava/lang/String;"
        elif isinstance(inType, VoidType):
            return "V"
        elif isinstance(inType, ArrayType):
            return "[" * len(inType.dimens) + self.getJVMType(inType.eleType)
        elif isinstance(inType, cgen.MType):
            return "(" + "".join(list(map(lambda x: self.getJVMType(x), inType.partype))) + ")" + self.getJVMType(inType.rettype)
        elif isinstance(inType, (StructType, InterfaceType)):
            return "L" + inType.name + ";"
        else:
            return str(inType)


    def getFullType(self, inType):
        typeIn = type(inType)
        if isinstance(inType, IntType):
            return "int"
        elif isinstance(inType, FloatType):
            return "float"
        elif isinstance(inType, BoolType):
            return "boolean"
        elif isinstance(inType, StringType):
            return "java/lang/String"
        elif isinstance(inType, VoidType):
            return "void"
        elif isinstance(inType, ArrayType):
            return "[" * len(inType.dimens) + self.getFullType(inType.eleType)
        elif isinstance(inType, (StructType, InterfaceType)):
            return inType.name
        else:
            # fallback—shouldn’t really happen if you’ve covered all your types
            raise AssertionError(f"getFullType: unexpected type {inType}")


    def emitPUSHICONST(self, in_, frame):
        #in: Int or String
        #frame: Frame
        
        frame.push()
        if isinstance(in_, int):
            i = in_
            if -1 <= i <= 5:
                return self.jvm.emitICONST(i)
            elif -128 <= i <= 127:
                return self.jvm.emitBIPUSH(i)
            elif -32768 <= i <= 32767:
                return self.jvm.emitSIPUSH(i)
            else:
                return self.jvm.emitLDC(str(i))
        elif isinstance(in_, str):
            if in_ == "true":
                return self.emitPUSHICONST(1, frame)
            elif in_ == "false":
                return self.emitPUSHICONST(0, frame)
            else:
                return self.emitPUSHICONST(int(in_), frame)


    def emitPUSHFCONST(self, in_, frame):
        #in_: String
        #frame: Frame
        
        f = float(in_)
        frame.push()
        rst = "{0:.4f}".format(f)
        if rst in ["0.0", "1.0", "2.0"]:
            return self.jvm.emitFCONST(rst)
        else:
            return self.jvm.emitLDC(in_)           


    ''' 
    *    generate code to push a constant onto the operand stack.
    *    @param in the lexeme of the constant
    *    @param typ the type of the constant
    '''
    def emitPUSHCONST(self, in_, typ, frame):
        #in_: String
        #typ: Type
        #frame: Frame
        
        if isinstance(typ, IntType):
            return self.emitPUSHICONST(in_, frame)
        elif isinstance(typ, FloatType):
            return self.emitPUSHFCONST(in_, frame)
        elif isinstance(typ, BoolType):
            frame.push()
            if in_:
                return self.jvm.emitICONST(1)
            else:
                return self.jvm.emitICONST(0)
        elif isinstance(typ, StringType):
            frame.push()
            return self.jvm.emitLDC(in_)
        else:
            raise IllegalOperandException(in_)

    ##############################################################

    def emitALOAD(self, in_, frame):
        #in_: Type
        #frame: Frame
        # before: ..., arrayref, index -> ...
        # consume arrayref and index
        frame.pop()
        frame.pop()
        # push result
        frame.push()
        if isinstance(in_, (IntType, BoolType)):
            return self.jvm.emitIALOAD()
        elif isinstance(in_, FloatType):
            return self.jvm.emitFALOAD()
        elif isinstance(in_, (ArrayType, StringType, StructType, InterfaceType)):
            return self.jvm.emitAALOAD()
        else:
            raise IllegalOperandException(str(in_))


    def emitASTORE(self, in_, frame):
        #in_: Type
        #frame: Frame
        # before: ..., arrayref, index, value -> ...
        # consume value, index, arrayref
        frame.pop()
        frame.pop()
        frame.pop()
        if isinstance(in_, (IntType, BoolType)):
            return self.jvm.emitIASTORE()
        elif isinstance(in_, FloatType):
            return self.jvm.emitFASTORE()
        elif isinstance(in_, (ArrayType, StringType, StructType, InterfaceType)):
            return self.jvm.emitAASTORE()
        else:
            raise IllegalOperandException(str(in_))


    '''    generate the var directive for a local variable.
    *   @param in the index of the local variable.
    *   @param varName the name of the local variable.
    *   @param inType the type of the local variable.
    *   @param fromLabel the starting label of the scope where the variable is active.
    *   @param toLabel the ending label  of the scope where the variable is active.
    '''
    def emitVAR(self, in_, varName, inType, fromLabel, toLabel, frame):
        #in_: Int
        #varName: String
        #inType: Type
        #fromLabel: Int
        #toLabel: Int
        #frame: Frame
        
        return self.jvm.emitVAR(in_, varName, self.getJVMType(inType), fromLabel, toLabel)


    def emitREADVAR(self, name, inType, index, frame):
        #name: String
        #inType: Type
        #index: Int
        #frame: Frame
        #... -> ..., value
        
        frame.push()
        if name == "this":
            return self.jvm.emitALOAD(index)
        elif isinstance(inType, (IntType, BoolType)):
            return self.jvm.emitILOAD(index)
        elif isinstance(inType, FloatType):
            return self.jvm.emitFLOAD(index)
        elif isinstance(inType, (ArrayType, StringType, StructType, InterfaceType)):
            return self.jvm.emitALOAD(index)
        else:
            raise IllegalOperandException(f"Cannot READVAR {name} of type {inType}")


    ''' generate the second instruction for array cell access
    *
    '''
    # def emitREADVAR2(self, name, typ, frame):
    #     #name: String
    #     #typ: Type
    #     #frame: Frame
    #     """
    #     After pushing arrayref and index, load the element:
    #     ..., arrayref, index -> ..., value
    #     """
    #     # consume arrayref and index
    #     frame.pop()
    #     frame.pop()
    #     # now push the loaded element
    #     frame.push()

    #     # dispatch on the element type
    #     if isinstance(typ, (IntType, BoolType)):
    #         return self.jvm.emitIALOAD()
    #     elif isinstance(typ, FloatType):
    #         return self.jvm.emitFALOAD()
    #     elif isinstance(typ, (StringType, ArrayType, StructType, InterfaceType)):
    #         return self.jvm.emitAALOAD()
    #     else:
    #         raise IllegalOperandException(f"Cannot READVAR2 {name} of element type {typ}")


    '''
    *   generate code to pop a value on top of the operand stack and store it to a block-scoped variable.
    *   @param name the symbol entry of the variable.
    '''
    def emitWRITEVAR(self, name, inType, index, frame):
        #name: String
        #inType: Type
        #index: Int
        #frame: Frame
        #..., value -> ...
        
        frame.pop()
        if isinstance(inType, (IntType, BoolType)):
            return self.jvm.emitISTORE(index)
        elif isinstance(inType, FloatType):
            return self.jvm.emitFSTORE(index)
        elif isinstance(inType, (ArrayType, StringType, StructType, InterfaceType)):
            return self.jvm.emitASTORE(index)
        else:
            raise IllegalOperandException(f"Cannot WRITEVAR {name} of type {inType}")


    ''' generate the second instruction for array cell access
    *
    '''
    # def emitWRITEVAR2(self, name, typ, frame):
    #     #name: String
    #     #typ: Type
    #     #frame: Frame

    #     # pop value, index, and arrayref
    #     frame.pop()
    #     frame.pop()
    #     frame.pop()
        
    #     if isinstance(typ, (IntType, BoolType)):
    #         return self.jvm.emitIASTORE()
    #     elif isinstance(typ, FloatType):
    #         return self.jvm.emitFASTORE()
    #     elif isinstance(typ, (StringType, ArrayType, StructType, InterfaceType)):
    #         return self.jvm.emitAASTORE()
    #     else:
    #         raise IllegalOperandException(f"Cannot WRITEVAR2 {name} of element type {typ}")


    ''' generate the field (static) directive for a class mutable or immutable attribute.
    *   @param lexeme the name of the attribute.
    *   @param in the type of the attribute.
    *   @param isFinal true in case of constant; false otherwise
    '''
    def emitATTRIBUTE(self, lexeme, in_, isStatic, isFinal, value):
        #lexeme: String
        #in_: Type
        #isFinal: Boolean
        #value: String
        if isStatic:
            return self.jvm.emitSTATICFIELD(lexeme, self.getJVMType(in_), isFinal, value)
        else:
            return self.jvm.emitINSTANCEFIELD(lexeme, self.getJVMType(in_), isFinal, value)


    def emitGETSTATIC(self, lexeme, in_, frame):
        #lexeme: String
        #in_: Type
        #frame: Frame

        frame.push()
        return self.jvm.emitGETSTATIC(lexeme, self.getJVMType(in_))


    def emitPUTSTATIC(self, lexeme, in_, frame):
        #lexeme: String
        #in_: Type
        #frame: Frame
        
        frame.pop()
        return self.jvm.emitPUTSTATIC(lexeme, self.getJVMType(in_))


    def emitGETFIELD(self, lexeme, in_, frame):
        #lexeme: String
        #in_: Type
        #frame: Frame
        # pop the objectref, then push the field’s contents
        frame.pop()
        frame.push()
        return self.jvm.emitGETFIELD(lexeme, self.getJVMType(in_))


    def emitPUTFIELD(self, lexeme, in_, frame):
        #lexeme: String
        #in_: Type
        #frame: Frame
        """
        .. pops value and objectref, stores value into that field
        """
        frame.pop()
        frame.pop()
        return self.jvm.emitPUTFIELD(lexeme, self.getJVMType(in_))


    ''' generate code to invoke a static method
    *   @param lexeme the qualified name of the method(i.e., class-name/method-name)
    *   @param in the type descriptor of the method.
    '''
    def emitINVOKESTATIC(self, lexeme, in_, frame):
        #lexeme: String
        #in_: Type
        #frame: Frame

        typ = in_
        # pop all arguments
        list(map(lambda x: frame.pop(), typ.partype))
        if not isinstance(typ.rettype, VoidType):
            frame.push()
        return self.jvm.emitINVOKESTATIC(lexeme, self.getJVMType(in_))


    ''' generate code to invoke a special method
    *   @param lexeme the qualified name of the method(i.e., class-name/method-name)
    *   @param in the type descriptor of the method.
    '''
    def emitINVOKESPECIAL(self, frame, lexeme=None, in_=None):
        #lexeme: String
        #in_: Type
        #frame: Frame

        if not lexeme is None and not in_ is None:
            typ = in_
            # pop all arguments
            list(map(lambda x: frame.pop(), typ.partype))
            # pop object reference
            frame.pop()
            if not isinstance(typ.rettype, VoidType):
                frame.push()
            return self.jvm.emitINVOKESPECIAL(lexeme, self.getJVMType(in_))
        elif lexeme is None and in_ is None:
            frame.pop()
            return self.jvm.emitINVOKESPECIAL()


    ''' generate code to invoke a virtual method
    * @param lexeme the qualified name of the method(i.e., class-name/method-name)
    * @param in the type descriptor of the method.
    '''
    def emitINVOKEVIRTUAL(self, lexeme, in_, frame):
        #lexeme: String
        #in_: Type
        #frame: Frame

        typ = in_
        # pop all arguments
        list(map(lambda x: frame.pop(), typ.partype))
        # pop object reference
        frame.pop()
        if not isinstance(typ.rettype, VoidType):
            frame.push()
        return self.jvm.emitINVOKEVIRTUAL(lexeme, self.getJVMType(in_))


    '''
    *   generate ineg, fneg.
    *   @param in the type of the operands.
    '''
    def emitNEGOP(self, in_, frame):
        #in_: Type
        #frame: Frame
        #..., value -> ..., result

        if isinstance(in_, IntType):
            return self.jvm.emitINEG()
        elif isinstance(in_, FloatType):
            return self.jvm.emitFNEG()
        else:
            raise IllegalOperandException(str(in_))


    def emitNOT(self, in_, frame):
        #in_: Type
        #frame: Frame

        label1 = frame.getNewLabel()
        label2 = frame.getNewLabel()
        result = list()

        result.append(self.emitIFTRUE(label1, frame))
        result.append(self.emitPUSHCONST("true", in_, frame))
        result.append(self.emitGOTO(label2, frame))
        result.append(self.emitLABEL(label1, frame))
        result.append(self.emitPUSHCONST("false", in_, frame))
        result.append(self.emitLABEL(label2, frame))

        return ''.join(result)


    '''
    *   generate iadd, isub, fadd or fsub.
    *   @param lexeme the lexeme of the operator.
    *   @param in the type of the operands.
    '''
    def emitADDOP(self, lexeme, in_, frame):
        #lexeme: String
        #in_: Type
        #frame: Frame
        #..., value1, value2 -> ..., result

        frame.pop()
        frame.pop()
        frame.push()
        if lexeme == "+":
            if isinstance(in_, IntType):
                return self.jvm.emitIADD()
            elif isinstance(in_, FloatType):
                return self.jvm.emitFADD()
            else:
                string_concat_descriptor = self.getJVMType(cgen.MType([StringType()], StringType()))
                return self.jvm.emitINVOKEVIRTUAL("java/lang/String/concat", string_concat_descriptor)
        else:
            if isinstance(in_, IntType):
                return self.jvm.emitISUB()
            else:
                return self.jvm.emitFSUB()


    '''
    *   generate imul, idiv, fmul or fdiv.
    *   @param lexeme the lexeme of the operator.
    *   @param in the type of the operands.
    '''
    def emitMULOP(self, lexeme, in_, frame):
        #lexeme: String
        #in_: Type
        #frame: Frame
        #..., value1, value2 -> ..., result

        frame.pop()
        frame.pop()
        frame.push()
        if lexeme == "*":
            if isinstance(in_, IntType):
                return self.jvm.emitIMUL()
            else:
                return self.jvm.emitFMUL()
        else:
            if isinstance(in_, IntType):
                return self.jvm.emitIDIV()
            else:
                return self.jvm.emitFDIV()


    # def emitDIV(self, frame):
    #     #frame: Frame

    #     frame.pop()
    #     frame.pop()
    #     frame.push()
    #     return self.jvm.emitIDIV()


    def emitMOD(self, frame):
        #frame: Frame

        frame.pop()
        frame.pop()
        frame.push()
        return self.jvm.emitIREM()


    '''
    *   generate iand
    '''
    def emitANDOP(self, frame):
        #frame: Frame

        frame.pop()
        frame.pop()
        frame.push()
        return self.jvm.emitIAND()


    '''
    *   generate ior
    '''
    def emitOROP(self, frame):
        #frame: Frame

        frame.pop()
        frame.pop()
        frame.push()
        return self.jvm.emitIOR()


    def emitREOP(self, op, in_, frame):
        #op: String
        #in_: Type
        #frame: Frame
        #..., value1, value2 -> ..., result

        result = list()
        labelF = frame.getNewLabel()
        labelO = frame.getNewLabel()

        if isinstance(in_, IntType):
            frame.pop()
            frame.pop()
            if op == ">":
                result.append(self.jvm.emitIFICMPLE(labelF))
            elif op == ">=":
                result.append(self.jvm.emitIFICMPLT(labelF))
            elif op == "<":
                result.append(self.jvm.emitIFICMPGE(labelF))
            elif op == "<=":
                result.append(self.jvm.emitIFICMPGT(labelF))
            elif op == "!=":
                result.append(self.jvm.emitIFICMPEQ(labelF))
            elif op == "==":
                result.append(self.jvm.emitIFICMPNE(labelF))

            result.append(self.emitPUSHCONST("1", BoolType(), frame))
            result.append(self.emitGOTO(labelO, frame))
            result.append(self.emitLABEL(labelF, frame))
            result.append(self.emitPUSHCONST("0", BoolType(), frame))
            result.append(self.emitLABEL(labelO, frame))

        elif isinstance(in_, FloatType):
            frame.pop()
            frame.pop()
            result.append(self.jvm.emitFCMPL())
            frame.push()
            if op == ">":
                result.append(self.jvm.emitIFLE(labelF))
            elif op == ">=":
                result.append(self.jvm.emitIFLT(labelF))
            elif op == "<":
                result.append(self.jvm.emitIFGE(labelF))
            elif op == "<=":
                result.append(self.jvm.emitIFGT(labelF))
            elif op == "!=":
                result.append(self.jvm.emitIFEQ(labelF))
            elif op == "==":
                result.append(self.jvm.emitIFNE(labelF))

            frame.pop()
            result.append(self.emitPUSHCONST("1", BoolType(), frame))
            result.append(self.emitGOTO(labelO, frame))
            result.append(self.emitLABEL(labelF, frame))
            result.append(self.emitPUSHCONST("0", BoolType(), frame))
            result.append(self.emitLABEL(labelO, frame))

        elif isinstance(in_, StringType):
            if op in ["==", "!="]:
                string_equals_descriptor = self.getJVMType(cgen.MType([cgen.ClassType("java/lang/Object")], BoolType()))
                result.append(self.jvm.emitINVOKEVIRTUAL("java/lang/String/equals", string_equals_descriptor))
                if op == "==":
                    result.append(self.jvm.emitIFEQ(labelF))
                elif op == "!=":
                    result.append(self.jvm.emitIFNE(labelF))
            elif op in ["<", "<=", ">", ">="]:
                string_compareTo_descriptor = self.getJVMType(cgen.MType([StringType()], IntType()))
                result.append(self.jvm.emitINVOKEVIRTUAL("java/lang/String/compareTo", string_compareTo_descriptor))
                if op == "<":
                    result.append(self.jvm.emitIFGE(labelF))
                elif op == "<=":
                    # Check if result <= 0. Inverse is result > 0.
                    result.append(self.jvm.emitIFGT(labelF)) # ifgt 0 jumps if result > 0
                elif op == ">":
                    # Check if result > 0. Inverse is result <= 0.
                    result.append(self.jvm.emitIFLE(labelF)) # ifle 0 jumps if result <= 0
                elif op == ">=":
                    # Check if result >= 0. Inverse is result < 0.
                    result.append(self.jvm.emitIFLT(labelF))
                
                result.append(self.emitPUSHCONST("1", BoolType(), frame))
                result.append(self.emitGOTO(labelO, frame))
                result.append(self.emitLABEL(labelF, frame))
                result.append(self.emitPUSHCONST("0", BoolType(), frame))
                result.append(self.emitLABEL(labelO, frame))

        return ''.join(result)


    def emitRELOP(self, op, in_, trueLabel, falseLabel, frame):
        #op: String
        #in_: Type
        #trueLabel: Int
        #falseLabel: Int
        #frame: Frame
        #..., value1, value2 -> ..., result

        result = list()

        if isinstance(in_, IntType):
            frame.pop()
            frame.pop()
            if op == ">":
                result.append(self.jvm.emitIFICMPLE(falseLabel))
            elif op == ">=":
                result.append(self.jvm.emitIFICMPLT(falseLabel))
            elif op == "<":
                result.append(self.jvm.emitIFICMPGE(falseLabel))
            elif op == "<=":
                result.append(self.jvm.emitIFICMPGT(falseLabel))
            elif op == "!=":
                result.append(self.jvm.emitIFICMPEQ(falseLabel))
            elif op == "==":
                result.append(self.jvm.emitIFICMPNE(falseLabel))

        elif isinstance(in_, FloatType):
            frame.pop()
            frame.pop()
            result.append(self.jvm.emitFCMPL())
            frame.push()
            if op == ">":
                result.append(self.jvm.emitIFLE(falseLabel))
            elif op == ">=":
                result.append(self.jvm.emitIFLT(falseLabel))
            elif op == "<":
                result.append(self.jvm.emitIFGE(falseLabel))
            elif op == "<=":
                result.append(self.jvm.emitIFGT(falseLabel))
            elif op == "!=":
                result.append(self.jvm.emitIFEQ(falseLabel))
            elif op == "==":
                result.append(self.jvm.emitIFNE(falseLabel))

        elif isinstance(in_, StringType):
            if op in ["==", "!="]:
                string_equals_descriptor = self.getJVMType(cgen.MType([cgen.ClassType("java/lang/Object")], BoolType()))
                result.append(self.jvm.emitINVOKEVIRTUAL("java/lang/String/equals", string_equals_descriptor))
                if op == "==":
                    result.append(self.jvm.emitIFEQ(falseLabel))
                elif op == "!=":
                    result.append(self.jvm.emitIFNE(falseLabel))
            elif op in ["<", "<=", ">", ">="]:
                string_compareTo_descriptor = self.getJVMType(cgen.MType([StringType()], IntType()))
                result.append(self.jvm.emitINVOKEVIRTUAL("java/lang/String/compareTo", string_compareTo_descriptor))
                if op == "<":
                    result.append(self.jvm.emitIFGE(falseLabel))
                elif op == "<=":
                    # Check if result <= 0. Inverse is result > 0.
                    result.append(self.jvm.emitIFGT(falseLabel)) # ifgt 0 jumps if result > 0
                elif op == ">":
                    # Check if result > 0. Inverse is result <= 0.
                    result.append(self.jvm.emitIFLE(falseLabel)) # ifle 0 jumps if result <= 0
                elif op == ">=":
                    # Check if result >= 0. Inverse is result < 0.
                    result.append(self.jvm.emitIFLT(falseLabel))
        else:
            raise IllegalOperandException(f"Relational operator '{op}' cannot be applied to type {in_}")
        
        result.append(self.emitGOTO(trueLabel, frame))
        return ''.join(result)


    '''   generate the method directive for a function.
    *   @param lexeme the qualified name of the method(i.e., class-name/method-name).
    *   @param in the type descriptor of the method.
    *   @param isStatic <code>true</code> if the method is static; <code>false</code> otherwise.
    '''
    def emitMETHOD(self, lexeme, in_, isStatic, frame):
        #lexeme: String
        #in_: Type
        #isStatic: Boolean
        #frame: Frame

        return self.jvm.emitMETHOD(lexeme, self.getJVMType(in_), isStatic)


    '''   generate the end directive for a function.
    '''
    def emitENDMETHOD(self, frame):
        #frame: Frame

        buffer = list()
        buffer.append(self.jvm.emitLIMITSTACK(frame.getMaxOpStackSize()))
        buffer.append(self.jvm.emitLIMITLOCAL(frame.getMaxIndex()))
        buffer.append(self.jvm.emitENDMETHOD())
        return ''.join(buffer)


    def getConst(self, ast):
        #ast: Literal
        if isinstance(ast, IntLiteral):
            return (str(ast.value), IntType())
        elif isinstance(ast, FloatLiteral):
            return (str(ast.value), FloatType())
        elif isinstance(ast, BooleanLiteral):
            return ("true" if ast.value else "false", BoolType())
        elif isinstance(ast, StringLiteral):
            return (ast.value, StringType())
        else:
            raise IllegalOperandException(str(ast))


    '''   generate code to initialize a local array variable.<p>
    *   @param index the index of the local variable.
    *   @param in the type of the local array variable.
    '''
    def emitNEWARRAY(self, elementType, frame):
        # elementType: Type (the AST Type node of the elements in the array dimension)
        # frame: Frame
        # Before stack: ..., size -> After stack: ..., arrayref (after allocation opcode)
        # Assumes integer size for this dimension is already on the stack BEFORE calling.

        if isinstance(elementType, IntType):
            return self.jvm.emitNEWARRAY("int")
        elif isinstance(elementType, FloatType):
            return self.jvm.emitNEWARRAY("float")
        elif isinstance(elementType, BoolType):
            return self.jvm.emitNEWARRAY("boolean")
        elif isinstance(elementType, (StringType, StructType, InterfaceType)):
            return self.jvm.emitANEWARRAY(self.getJVMType(elementType))
        else:
            raise IllegalOperandException(f"Cannot emitNEWARRAY for element type {elementType}")


    '''   generate code to initialize local array variables.
    *   @param in the list of symbol entries corresponding to local array variable.    
    '''
    def emitALLOCATE_AND_STORE_LOCAL_ARRAY(self, arrayType: ArrayType, slotIndex: int, frame):
        # arrayType: ArrayType (the AST node describing the full array type)
        # slotIndex: int (the local variable index to store the allocated array)
        # frame: Frame
        ''' Assumes the sizes for all dimensions (from leftmost to rightmost) are already
        pushed onto the operand stack BEFORE this method is called.
        '''
        # Before stack: ..., size_dim1, size_dim2, ..., size_dimN
        # After stack: ... (arrayref is consumed by astore)
        result = []
        num_dims = len(arrayType.dimens)
        jvm_array_descriptor = self.getJVMType(arrayType)
        # Simulate popping the size(s) from the stack before allocation
        for _ in range(num_dims):
            frame.pop()

        if num_dims == 1:
            result.append(self.emitNEWARRAY(arrayType.eleType, frame))
        elif num_dims > 1:
            result.append(self.jvm.emitMULTIANEWARRAY(jvm_array_descriptor, num_dims))
        else:
            raise Exception(f"Invalid array dimension count ({num_dims}) for type {arrayType}")
        
        frame.push()
        frame.pop()
        result.append(self.jvm.emitASTORE(slotIndex))
        return ''.join(result)


    '''   generate code to jump to label if the value on top of operand stack is true.<p>
    *   ifgt label
    *   @param label the label where the execution continues if the value on top of stack is true.
    '''
    def emitIFTRUE(self, label, frame):
        #label: Int
        #frame: Frame
        frame.pop()
        return self.jvm.emitIFGT(label)


    '''
    *   generate code to jump to label if the value on top of operand stack is false.<p>
    *   ifle label
    *   @param label the label where the execution continues if the value on top of stack is false.
    '''
    def emitIFFALSE(self, label, frame):
        #label: Int
        #frame: Frame
        frame.pop()
        return self.jvm.emitIFLE(label)


    def emitIFICMPGT(self, label, frame):
        #label: Int
        #frame: Frame

        frame.pop()
        frame.pop()
        return self.jvm.emitIFICMPGT(label)


    def emitIFICMPLT(self, label, frame):
        #label: Int
        #frame: Frame

        frame.pop()
        frame.pop()
        return self.jvm.emitIFICMPLT(label)    


    '''   generate code to duplicate the value on the top of the operand stack.<p>
    *   Stack:<p>
    *   Before: ...,value1<p>
    *   After:  ...,value1,value1<p>
    '''
    def emitDUP(self, frame):
        #frame: Frame
        frame.push()
        return self.jvm.emitDUP()


    def emitPOP(self, frame):
        #frame: Frame
        frame.pop()
        return self.jvm.emitPOP()


    '''   generate code to exchange an integer on top of stack to a floating-point number.
    '''
    def emitI2F(self, frame):
        #frame: Frame
        frame.pop()
        frame.push()
        return self.jvm.emitI2F()


    ''' generate code to return.
    *   <ul>
    *   <li>ireturn if the type is IntegerType or BooleanType
    *   <li>freturn if the type is RealType
    *   <li>return if the type is null
    *   </ul>
    *   @param in the type of the returned expression.
    '''
    def emitRETURN(self, in_, frame):
        #in_: Type
        #frame: Frame

        if isinstance(in_, (IntType, BoolType)):
            frame.pop()
            return self.jvm.emitIRETURN()
        elif isinstance(in_, FloatType):
            frame.pop()
            return self.jvm.emitFRETURN()
        elif isinstance(in_, StringType):
            frame.pop()
            return self.jvm.emitARETURN()
        elif type(in_) is VoidType:
            return self.jvm.emitRETURN()


    ''' generate code that represents a label	
    *   @param label the label
    *   @return code Label<label>:
    '''
    def emitLABEL(self, label, frame):
        #label: Int
        #frame: Frame
        return self.jvm.emitLABEL(label)


    ''' generate code to jump to a label	
    *   @param label the label
    *   @return code goto Label<label>
    '''
    def emitGOTO(self, label, frame):
        #label: Int
        #frame: Frame
        return self.jvm.emitGOTO(label)


    ''' generate some starting directives for a class.<p>
    *   .source MPC.CLASSNAME.java<p>
    *   .class public MPC.CLASSNAME<p>
    *   .super java/lang/Object<p>
    '''
    def emitPROLOG(self, name, parent):
        #name: String
        #parent: String

        result = list()
        result.append(self.jvm.emitSOURCE(name + ".java"))
        result.append(self.jvm.emitCLASS("public " + name))
        result.append(self.jvm.emitSUPER("java/lang/Object" if parent == "" else parent))
        return ''.join(result)


    def emitLIMITSTACK(self, num):
        #num: Int
        return self.jvm.emitLIMITSTACK(num)


    def emitLIMITLOCAL(self, num):
        #num: Int
        return self.jvm.emitLIMITLOCAL(num)


    def emitEPILOG(self):
        file = open(self.filename, "w")
        file.write(''.join(self.buff))
        file.close()


    ''' print out the code to screen
    *   @param in the code to be printed out
    '''
    def printout(self, in_):
        #in_: String
        self.buff.append(in_)


    def clearBuff(self):
        self.buff.clear()