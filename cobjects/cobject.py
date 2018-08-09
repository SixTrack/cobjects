from .cbuffer import CBuffer
from .cfield import CField


class CObject(object):
    @classmethod
    def get_fields(cls):
        for nn, vv in cls.__dict__.items():
            if isinstance(vv, CField):
                yield nn, vv

    @classmethod
    def get_itemsize(cls, offset, nargs):
        return cls(offset,**nargs)._size

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
            length = field.get_length(nargs)
            self._flength.append(length)
            size = field.get_size(ftype, curr_offset, nargs)
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
                setattr(self, name, nargs.get(name, field.default))
                if field.const is True:
                    self._const[field.index] = True

    def __repr__(self):
        out = [f"<{self.__class__.__name__} at {self._offset}"]
        for nn, ff in self._fields():
            out.append(f"  {nn}:{getattr(self,nn)}")
        out.append(">")
        return "\n".join(out)

