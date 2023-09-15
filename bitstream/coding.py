from bitstring import BitArray, Bits



class CRCCalculator:

    def __init__(self, size, polynomial):
        self.size = size
        self.polynomial = BitArray(uint=polynomial, length=size + 1)

    def calculate(self, bitstream):
        dividend = bitstream + BitArray(self.size)
        divisor = self.polynomial + BitArray(len(bitstream) - 1)
        for i in range(len(bitstream)):
            if dividend[i]:
                dividend ^= divisor
            divisor >>= 1
        return dividend[-self.size:]

    def validate(self, data, checksum):
        dividend = data + checksum
        divisor = self.polynomial + BitArray(len(data) - 1)
        for i in range(len(data)):
            if dividend[i]:
                dividend ^= divisor
            divisor >>= 1
        return dividend[-self.size:].uint == 0



class Puncturer:

    def __init__(self, size, pattern):
        self.pattern = BitArray(uint=pattern, length=size)

    def encode(self, bitstream):
        output = BitArray()
        for i in range(len(bitstream)):
            if self.pattern[i % len(self.pattern)]:
                output.append(BitArray(bool=bitstream[i]))
        return output

    def decode(self, bitstream):
        # TODO: Implement depuncturing
        pass



class ConvolutionalCoder:

    def __init__(self, generator_polynomial):
        constraint_length = len(generator_polynomial) - 1
        
        states = []
        for i in range(2 ** constraint_length):
            states.append(Bits(uint=i, length=constraint_length))

        self.trans = {}
        for state in states:
            xor0 = list(state & generator_polynomial[1:]).count(1) % 2 == True
            xor1 = xor0 ^ True
            state0 = state >> 1
            state1 = state0 | BitArray(bin="100000")
            self.trans[state] = {False: [state0, xor0], True: [state1, xor1]}

    def encode(self, data):
        out = BitArray()
        state = Bits(bin="000000")
        for bit in data:
            state, xor = self.trans[state][bit]
            out.append(Bits(bool=xor))
        return out

    def decode(self, encoded):
        out = BitArray()
        state = Bits(bin="000000")
        for xor in encoded:
            state, orig = [(self.trans[state][bit][0], bit) for bit in self.trans[state] if self.trans[state][bit][1] == xor][0]
            out.append(BitArray(bool=orig))
        return out
