from .cbuffer import CBuffer
from .cfield import CField

import numpy as np

_ctypes={'int64': 'long',
         'int32': 'int',
         'uint8': 'unsigned char',
         'float64': 'double'}

_cprintf={'int64': '%ld',
         'int32': '%d',
         'uint8': '%d',
         'float64': '%g'}

class CObject(object):
    def _to_cdecl(self,restrict=True, aligned=False):
        out=[]
        for  name, self._fnames in self._fields():
            field=getattr(self,name)
            if hasattr(field,'_to_cdecl'):
                out.append(field._to_cdecl())
        out.append("typedef struct {")
        for  name, field in self._fields():
            ftype=(self._ftypes[field.index])
            if hasattr(ftype,'_to_cdecl'):
                ftype=ftype.__name__
            else:
                ftype=str(self._ftypes[field.index])
            ftype=_ctypes.get(ftype,ftype)
            length=self._flength[field.index]
            if field.pointer:
                if restrict:
                   name=' restrict ' + name
                name='*'+name
            elif length is not None:
                name=f"{name}[{length}]"
            if field.alignment is not None and aligned is True:
                name=f"     {name} __attribute__((aligned ({field.alignment})))"
            out.append(f'{str(ftype):10} {name} ;')
        out.append("} %s;"%self.__class__.__name__ )
        return '\n'.join(out)

    def _to_cdebug(self,restrict=True):
        out=[self._to_cdecl(restrict=restrict,aligned=True)]
        cls=self.__class__.__name__
        out.append("#include <stdio.h>")
        out.append("void %s_print(%s *obj){"%(cls,cls))
        out.append(f'printf("{cls} at %zu \\n",(size_t) obj );')
        for  name, field in self._fields():
            ftype=str(self._ftypes[field.index])
            ftype=_cprintf.get(ftype,ftype)
            length=self._flength[field.index]
            if length is None:
                out.append(f'  printf("    %-15s= {ftype}\\n","{name}",obj->{name}); ')
            else:
                for ii in range(length):
                    out.append(f'  printf("    %-15s= {ftype}\\n","{name}[{ii}]",obj->{name}[{ii}]); ')
        out.append("};")
        return '\n'.join(out)

    def _cdebug(self):
        import cffi
        ffi = cffi.FFI()
        ffi.cdef(self._to_cdecl(restrict=False,aligned=False))
        cls=self.__class__.__name__
        ffi.cdef("void %s_print(%s *obj);"%(cls,cls))
        lib = ffi.verify(self._to_cdebug())
        cobj= ffi.cast(f"{cls} *",self._get_address())
        getattr(lib,"%s_print"%cls)(cobj)
        return ffi,lib,cobj

    @classmethod
    def get_fields(cls):
        for nn, vv in cls.__dict__.items():
            if isinstance(vv, CField):
                yield nn, vv

    @classmethod
    def get_itemsize(cls, nargs):
        return cls(**nargs)._size

    def _check_pointers(self):
        pfields=[ (name, field) for name, field in self._fields() if field.pointer is True]
        for offset,(name, field) in zip(self._pointer_list,pfields):
            pointer_offset= self._offset + offset
            data_offset=self._offsets[field.index]
            data_address=self._buffer.get_field(pointer_offset,'int64',64,None)
            print(f"field {name}: obj={self._offset} *={data_offset} off={data_offset-self._offset}")
            object_address=self._get_address()
            print(f"   obj={object_address} *={data_address} off={data_address-object_address}")

    def _get_address(self):
        return self._buffer.offset_to_address(self._offset)

    def _get_slot_buffer(self):
        return self._buffer._data[self._offset:self._offset+self._size].view('int64')

    def _fields(self):
        return self.__class__.get_fields()

    def __init__(self, cbuffer=None, _offset=None, copy_args=False,
                       **nargs):
        if cbuffer is None:
            cbuffer = CBuffer(template=CBuffer.c_types)
        self._buffer = cbuffer
        if _offset is None:
            new_object = True
            copy_args  = True
        else:
            new_object = False
            copy_args  = False
        self._setup_from_args(nargs, _offset, new_object, copy_args)

    def _setup_from_args(self, nargs, offset, new_object, copy_args):
        self._offsets = []
        self._ftypes = []
        self._fsizes = []
        self._fnames = []
        self._flength = []
        self._fconst = []
        curr_size = 0
        if new_object is True:
            curr_offset = 0
        else:
            curr_offset = offset
            self._offset = offset
        curr_pointers = 0
        pointer_list = [] #offset from beginning of the object to pointer
        pointer_data = [] #offset from beginning of the object to pointing data
        # first pass for normal fields
        for name, field in self._fields():
            ftype = self._buffer.resolve_type(field.ftype)
            if not (type(ftype) is type and issubclass(ftype,CObject)):
                ftype = np.dtype(ftype)
            length = field.get_length(nargs)
            self._flength.append(length)
            size = int(field.get_size(ftype, curr_offset, nargs))
            self._fconst.append(False)
            self._fnames.append(name)
            self._ftypes.append(ftype)
            self._fsizes.append(size)
            if field.pointer is False:
                if field.alignment is not None:
                    pad = field.alignment-curr_offset % field.alignment
                    pad = pad % field.alignment
                    curr_size += pad
                    curr_offset += pad
                self._offsets.append(curr_offset)
                pad = (8-size % 8) % 8
                curr_offset += size+pad
                curr_size += size+pad
            else:  # is pointer
                self._offsets.append(curr_offset)
                pointer_list.append(curr_offset)
                curr_offset += 8
                curr_size += 8
            if new_object is False:
                if field.const is True:
                    nargs[name] = getattr(self, name)
        self._pointer_list=pointer_list
        # second pass for pointer fields
        for name, field in self._fields():
            if field.pointer is True:
                if field.alignment is not None:
                    pad = field.alignment-curr_offset % field.alignment
                    pad = pad % field.alignment
                    curr_size += pad
                    curr_offset += pad
                offset = self._offsets[field.index]
                pointer_data.append([offset, curr_offset])
                self._offsets[field.index] = curr_offset
                size = self._fsizes[field.index]
                curr_size += size
                curr_offset += size
        if new_object is True:
            # allocate data
            _address = self._buffer.new_object(curr_size,
                                               self.__class__,
                                               pointer_list)
            self._offset = self._buffer.address_to_offset(_address)
            self._size = curr_size
            for index in range(len(self._offsets)):
                self._offsets[index] += self._offset
        if copy_args is True:
            # store pointer data
            for offset, address in pointer_data:
                doffset = offset+self._offset #location from buffer
                self._buffer.set_field(doffset, 'int64', 8, None, _address+address)
            # store data in fields
            for name, field in self._fields():
                if field.is_scalar():
                   setattr(self, name, nargs.get(name, field.default))
                if field.const is True:
                    self._fconst[field.index] = True

    def __repr__(self):
        out = [f"<{self.__class__.__name__} at {self._offset}"]
        for nn, ff in self._fields():
            out.append(f"  {nn}:{getattr(self,nn)}")
        out.append(">")
        return "\n".join(out)

    def to_dict(self):
        return {ll: getattr(self,ll) for ll in self._fnames}

