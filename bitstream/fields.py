from bitstring import BitArray



class QueueBuffer(BitArray):

    def remove(self, size):
        if size > len(self):
            raise RuntimeError("Buffer too empty")

        bitstream = self[:size]
        remaining = self[size:]
        self.clear()
        self += remaining
        
        return bitstream

    def add(self, bitstream):
        self += bitstream



class Field:

    def __init__(self, size=0, *args, bytes=None, uint=None):
        self._bitarray = BitArray()
        self._size = size
        self._cursor = 0

        if bytes != None:
            self.bytes = bytes
        elif uint != None:
            self.uint = uint

    @property
    def size(self):
        return self._size

    @size.setter
    def size(self, size):
        if len(self._bitarray) > size:
            raise ValueError("Size too small for existing bitstream")
        
        self._size = size

    #### Methods for working with the bitstream in chunks

    def read(self, size):
        if self._cursor == self._size:
            return BitArray()
        
        end_position = min(self._cursor + size, self._size)

        if self._cursor >= len(self._bitarray):
            raise RuntimeError("Field too empty")
        
        if end_position == self._size and not self.is_full:
            raise RuntimeError("Field too empty")
        
        bitstream = self._bitarray[self._cursor:end_position]
        self._cursor = end_position
        
        return bitstream

    def write(self, bitstream):
        missing_size = self._size - len(self._bitarray)
        self._bitarray += bitstream[:missing_size]
        return bitstream[missing_size:]

    def rewind(self):
        self._cursor = 0

    def clear(self):
        self._bitarray.clear()

    @property
    def is_full(self):
        return len(self._bitarray) == self._size

    #### Methods for working with the entire bitstream as a single value

    @property
    def bitstream(self):
        if not self.is_full:
            raise RuntimeError("Field not full")

        self.rewind()
        bitstream = self.read(self._size)
        self.rewind()
        return bitstream

    @bitstream.setter
    def bitstream(self, bitstream):
        if len(bitstream) != self._size:
            raise ValueError("Size mismatch")
        
        self.clear()
        self.write(bitstream)

    @property
    def bytes(self):
        return self.bitstream.bytes

    @bytes.setter
    def bytes(self, bytes):
        bitstream = BitArray(bytes=bytes)
        if len(bitstream) != self._size:
            raise ValueError("Size mismatch")
        
        self.bitstream = bitstream

    @property
    def uint(self):
        return self.bitstream.uint

    @uint.setter
    def uint(self, uint):
        bitstream = BitArray(length=self._size, uint=uint)
        self.bitstream = bitstream

    def __lshift__(self, field):
        self.bitstream = field.bitstream

    def __str__(self):
        text = ""
        text += "Field (%i-bit)\n" % self.size
        text += "    %s" % self._bitarray.bin
        text += "x" * (self.size - len(self._bitarray))
        if self.size > 0 and self.is_full:
            text += "  (%s)  (%s)" % (hex(self.bitstream.uint), self.bitstream.uint)
        return text



class FieldGroup:

    def __init__(self):
        self._fields = []

    @property
    def size(self):
        return sum([field.size for field in self._fields])

    def _addField(self, field):
        self._fields.append(field)

    #### Methods for working with the bitstream in chunks

    def read(self, size):
        bitstream = BitArray()
        for field in self._fields:
            bitstream += field.read(size - len(bitstream))
            if len(bitstream) == size:
                break
        return bitstream

    def write(self, bitstream):
        for field in self._fields:
            bitstream = field.write(bitstream)
            if len(bitstream) == 0:
                break
        return bitstream

    def rewind(self):
        for field in self._fields:
            field.rewind()

    def clear(self):
        for field in self._fields:
            field.clear()

    #### Methods for working with the entire bitstream as a single value

    @property
    def bitstream(self):
        self.rewind()
        bitstream = self.read(self.size)
        self.rewind()
        
        return bitstream

    @bitstream.setter
    def bitstream(self, bitstream):
        if len(bitstream) != self.size:
            raise ValueError("Size mismatch")

        self.clear()
        self.write(bitstream)
    
    def __lshift__(self, field):
        self.bitstream = field.bitstream

    def __str__(self):
        text = ""
        text += "FieldGroup (%i fields)\n" % len(self._fields)
        for i, field in enumerate(self._fields):
            child_text = field.__str__()
            text += "    [ Field %i ]: " % i
            text += "\n".join(["    " + line for line in child_text.split("\n")][:-1])
            text += "\n"
        return text[-1]



class Frame(FieldGroup):
    
    def __init__(self):
        super().__init__()

        self._named_fields = {}

    def _addField(self, name, field):
        self._named_fields[name] = field

        super()._addField(field)

    def __getitem__(self, name):
        return self._named_fields[name]

    def __str__(self):
        text = ""
        text += "Frame\n"
        names, fields = zip(*self._named_fields.items())
        for field in self._fields:
            name = names[fields.index(field)]
            child_text = field.__str__()
            text += "    [ %s ]: " % name
            text += "\n".join(["    " + line for line in child_text.split("\n")])
            text += "\n"
        return text[:-1]
